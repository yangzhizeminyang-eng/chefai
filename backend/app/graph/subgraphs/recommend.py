"""推荐子图模块。

职责：
    装配 recommend 子图（架构文档 §4.1/§4.5）：
    assemble_context → recipe_retrieve → hard_filter → (recipe_rank ∥ node_nutrition) → END

    LangGraph 1.x 并行实现：hard_filter 以 fan-out 两条边同时连 recipe_rank 与
    node_nutrition，两分支各自连 END；同一 superstep 内并行执行，子图内 trace 依赖
    operator.add reducer 正确合并；两分支全部结束后才返回主图（进入 compose）。

状态转换（🔴 重要）：
    子图使用独立内部 schema（RecommendSubgraphState，trace 字段名为 sub_trace），
    主图通过包装节点 subgraph_recommend_node 调用子图并手动转换状态——
    若子图直接复用主图 CookingState（同名 trace channel），子图会把继承自主图的
    span 原样写回，再经主图 operator.add 累加导致 trace 重复（已实测踩坑）。

节点说明：
    - assemble_context：解析食材（名称/别名/ID → ingredient_id），文本无显式食材时
      从输入文本确定性匹配（match_ingredients_in_text）；
    - recipe_retrieve：混合召回（食材覆盖数降序 + 菜名 ILIKE/别名，向量召回阶段二接入）；
    - hard_filter：布尔过滤（过敏原/忌口/难度 SQL WHERE + 设备差集，禁止降权）；
    - recipe_rank：7 因子加权 + rank_reasons + 三档 match_level，Top 8；
      E.9 反馈接线：state 带数字 user_id 时加载 feedback_penalty（dislike 菜谱 -0.5）
      传入 weighted_rank（state 无 user_id 时跳过，空惩罚不影响排序）。
"""

from __future__ import annotations

import operator
import os
from collections.abc import Callable
from typing import Annotated, TypedDict

from langgraph.graph import END, START, StateGraph

from app.ability import hard_filter, load_weights, retrieve_candidates
from app.ability.retrieval import match_ingredients_in_text
from app.core.db import SessionLocal
from app.core.logging import get_logger
from app.graph.nodes.common import make_span, now_ms
from app.graph.nodes.nutrition_node import make_node_nutrition
from app.graph.registry import register
from app.safety import SafetyProfile

logger = get_logger(__name__)


class RecommendSubgraphState(TypedDict, total=False):
    """推荐子图内部状态（模型类）。

    说明：
        trace 字段命名为 sub_trace（operator.add reducer）：与主图 CookingState.trace
        不同名，避免子图继承父图 span 导致主图 reducer 重复累加；
        父子图状态转换由包装节点 subgraph_recommend_node 完成。

    字段：
        request_id/trace_id/input_text/ingredients/safety_profile：请求上下文（只读）。
        user_id：数字用户 ID（E.9 反馈惩罚用；runner 注入，缺省时排序不施加惩罚）。
        resolved_ingredient_ids / resolved_ingredient_names：assemble_context 解析结果。
        candidates：召回候选。
        filtered_candidates：硬过滤后候选。
        filtered_by：硬过滤计数。
        results：排序后结果（Top 8）。
        nutrition：{recipe_id: 营养估算结果}。
        partial_failures：部分失败说明。
        sub_trace：子图内 trace span 列表（operator.add 累加）。
    """

    request_id: str
    trace_id: str
    input_text: str
    ingredients: list
    safety_profile: dict
    user_id: int
    resolved_ingredient_ids: list
    resolved_ingredient_names: list
    candidates: list
    filtered_candidates: list
    filtered_by: dict
    results: list
    nutrition: dict
    partial_failures: list
    sub_trace: Annotated[list[dict], operator.add]


def _rename_trace(node: Callable) -> Callable:
    """把节点返回的 trace 键改名为 sub_trace 的包装器（函数）。

    说明：
        供复用主图节点工厂（如 node_nutrition）接入子图内部 schema 使用。

    参数：
        node：原节点函数（返回 dict 含 "trace" 键）。

    返回值：
        Callable：包装后的节点函数（返回 dict 含 "sub_trace" 键）。

    异常：
        不抛出（原节点已自行兜底）。
    """

    def wrapped(state: dict) -> dict:
        out = dict(node(state))
        if "trace" in out:
            out["sub_trace"] = out.pop("trace")
        return out

    return wrapped


def _lookup_ingredient(session, name: str) -> tuple[int, str] | None:
    """按名称/别名查询单个食材（函数）。

    说明：
        食材名精确命中优先，别名次之；阶段一 N+1 查询规模可控（用户食材数有限）。

    参数：
        session：数据库会话。
        name：食材名称或别名。

    返回值：
        tuple[int, str] | None：(ingredient_id, 展示名)；未命中返回 None。

    异常：
        查询异常向上抛出（由 assemble_context 统一捕获）。
    """
    from sqlalchemy import select

    from app.models import Ingredient, IngredientAlias

    ing_id = session.execute(
        select(Ingredient.id).where(Ingredient.name == name)
    ).scalar_one_or_none()
    if ing_id is not None:
        return int(ing_id), name
    row = session.execute(
        select(IngredientAlias.ingredient_id, IngredientAlias.alias).where(IngredientAlias.alias == name)
    ).first()
    if row:
        return int(row[0]), str(row[1])
    return None


def make_assemble_context():
    """assemble_context 节点工厂（函数）。

    返回值：
        Callable：节点函数。

    异常：
        无。
    """

    def assemble_context(state: RecommendSubgraphState) -> dict:
        """上下文装配节点：解析用户食材为 ingredient_id（函数）。

        说明：
            支持三种输入形态：名称字符串 / {ingredient_id} 字典 / {name} 字典；
            显式食材为空且输入文本非空时，用确定性子串匹配从文本提取食材。

        参数：
            state：子图状态。

        返回值：
            dict：{"resolved_ingredient_ids": [...], "resolved_ingredient_names": [...],
            "sub_trace": [span]}。

        异常：
            不抛出（数据库异常时返回空解析结果，交由下游空候选兜底）。
        """
        start = now_ms()
        ids: list[int] = []
        names: list[str] = []
        try:
            with SessionLocal() as session:
                for item in state.get("ingredients") or []:
                    if isinstance(item, dict):
                        if item.get("ingredient_id"):
                            ids.append(int(item["ingredient_id"]))
                            continue
                        name = str(item.get("name") or "")
                    else:
                        name = str(item)
                    if not name:
                        continue
                    resolved = _lookup_ingredient(session, name)
                    if resolved:
                        ing_id, display = resolved
                        if ing_id not in ids:
                            ids.append(ing_id)
                            names.append(display)
                    else:
                        names.append(name)  # 未在库中命中的名称（供前端提示）
                # 无显式食材时从输入文本确定性匹配（如 run_ask「用土豆和青椒做点什么」）
                if not ids and state.get("input_text"):
                    text_ids, text_names = match_ingredients_in_text(session, state["input_text"])
                    ids, names = text_ids, text_names
        except Exception as exc:  # noqa: BLE001 —— 解析失败走空集，交由下游空候选兜底
            logger.warning("assemble_context failed: %s", exc)

        span = make_span("assemble_context", "ok", now_ms() - start)
        return {
            "resolved_ingredient_ids": ids,
            "resolved_ingredient_names": names,
            "sub_trace": [span],
        }

    return assemble_context


def make_recipe_retrieve():
    """recipe_retrieve 节点工厂（函数）。

    返回值：
        Callable：节点函数。

    异常：
        无。
    """

    def recipe_retrieve(state: RecommendSubgraphState) -> dict:
        """混合召回节点（函数）。

        说明：
            向量路径开关：环境变量 RETRIEVAL_VECTOR（'on' 缺省 | 'off'），off 时
            走纯关键词路径；on 时 retrieve_candidates 内部自动双分支（pgvector
            raw SQL / embedding_json Python 点积）并全程兜底降级，绝不抛错。

        参数：
            state：子图状态（resolved_ingredient_ids 已就绪）。

        返回值：
            dict：{"candidates": 候选列表, "sub_trace": [span]}（召回失败时 candidates=[]）。

        异常：
            不抛出（retrieve_candidates 内部全捕获）。
        """
        start = now_ms()
        ids = list(state.get("resolved_ingredient_ids") or [])
        text = state.get("input_text") or None
        use_vector = os.environ.get("RETRIEVAL_VECTOR", "on").strip().lower() in ("on", "true", "1")
        with SessionLocal() as session:
            candidates = retrieve_candidates(
                session, ids, query_text=text, limit=200, use_vector=use_vector
            )
        # 召回为空且确有输入 → degraded（下游 compose 如实说明）
        status = "degraded" if not candidates else "ok"
        span = make_span("recipe_retrieve", status, now_ms() - start)
        return {"candidates": candidates, "sub_trace": [span]}

    return recipe_retrieve


def make_hard_filter_node():
    """hard_filter 节点工厂（函数）。

    返回值：
        Callable：节点函数。

    异常：
        无。
    """

    def hard_filter_node(state: RecommendSubgraphState) -> dict:
        """布尔硬过滤节点（SQL WHERE，非打分）（函数）。

        参数：
            state：子图状态（candidates / safety_profile 已就绪）。

        返回值：
            dict：{"filtered_candidates": [...], "filtered_by": {...},
            "sub_trace": [span]}（过滤失败按「宁少不错」返回空集）。

        异常：
            不抛出（hard_filter 内部全捕获）。
        """
        start = now_ms()
        profile = SafetyProfile(**(state.get("safety_profile") or {}))
        with SessionLocal() as session:
            filtered, counts = hard_filter(session, state.get("candidates") or [], profile)
        # 过滤后有候选 → ok；无候选 → degraded（compose 如实说明）
        status = "ok" if filtered else "degraded"
        span = make_span("hard_filter", status, now_ms() - start)
        return {"filtered_candidates": filtered, "filtered_by": counts, "sub_trace": [span]}

    return hard_filter_node


def make_recipe_rank():
    """recipe_rank 节点工厂（函数）。

    返回值：
        Callable：节点函数。

    异常：
        无。
    """

    def recipe_rank(state: RecommendSubgraphState) -> dict:
        """7 因子排序节点（函数）。

        说明：
            输入集 = hard_filter 输出集（结构上无法给被过滤项打分）；
            权重来自 remote_config rank.weights（缺失回退默认）。
            E.9 反馈立即生效：state 带数字 user_id 时加载该用户 dislike 反馈惩罚
            （load_feedback_penalty，dislike → -0.5），传入 weighted_rank 的
            feedback_penalty 参数；无 user_id（阶段一 runner 未注入数字 ID，
            仅 user_id_hash，无法反解）或查询失败时为空惩罚，排序行为不变。

        参数：
            state：子图状态（filtered_candidates 已就绪；user_id 可缺省）。

        返回值：
            dict：{"results": Top 8 排序结果, "sub_trace": [span]}。

        异常：
            不抛出（weighted_rank 内部单条捕获；惩罚加载失败回退空映射）。
        """
        start = now_ms()
        profile = SafetyProfile(**(state.get("safety_profile") or {}))
        # E.9 反馈接线：解析数字 user_id（缺省/非数字一律跳过，空惩罚）
        raw_uid = state.get("user_id")
        try:
            user_id = int(raw_uid) if raw_uid is not None else None
        except (TypeError, ValueError):
            user_id = None
        with SessionLocal() as session:
            weights = load_weights(session)
            penalty_map: dict[int, float] = {}
            if user_id is not None:
                from app.ability.ranking import load_feedback_penalty

                penalty_map = load_feedback_penalty(session, user_id)
        results: list[dict] = []
        try:
            from app.ability import weighted_rank

            results = weighted_rank(
                state.get("filtered_candidates") or [], profile, weights, feedback_penalty=penalty_map
            )
        except Exception as exc:  # noqa: BLE001 —— 排序失败返回空，由 compose 如实说明
            logger.error("weighted_rank failed: %s", exc)
        status = "ok" if results else "degraded"
        span = make_span("recipe_rank", status, now_ms() - start)
        return {"results": results, "sub_trace": [span]}

    return recipe_rank


def build_recommend_subgraph():
    """装配并编译推荐子图（函数）。

    说明：
        拓扑：START → assemble_context → recipe_retrieve → hard_filter →
        fan-out {recipe_rank, node_nutrition} → END。

    参数：
        无。

    返回值：
        CompiledStateGraph：编译后的推荐子图。

    异常：
        LangGraph 装配异常向上抛出（应用启动期即暴露）。
    """
    builder = StateGraph(RecommendSubgraphState)
    builder.add_node("assemble_context", make_assemble_context())
    builder.add_node("recipe_retrieve", make_recipe_retrieve())
    builder.add_node("hard_filter", make_hard_filter_node())
    builder.add_node("recipe_rank", make_recipe_rank())
    builder.add_node("node_nutrition", _rename_trace(make_node_nutrition()))
    builder.add_edge(START, "assemble_context")
    builder.add_edge("assemble_context", "recipe_retrieve")
    builder.add_edge("recipe_retrieve", "hard_filter")
    # fan-out：硬过滤后并行执行排序与营养估算（trace 由 operator.add 合并）
    builder.add_edge("hard_filter", "recipe_rank")
    builder.add_edge("hard_filter", "node_nutrition")
    builder.add_edge("recipe_rank", END)
    builder.add_edge("node_nutrition", END)
    return builder.compile()


def make_recommend_subgraph_node():
    """主图「subgraph_recommend」包装节点工厂（函数）。

    说明：
        负责父子图状态转换：只向子图传请求上下文（不含主图 trace，防 span 重复累加），
        子图结束后把业务键与 sub_trace 映射回主图 state 键；
        子图执行异常时兜底返回空结果 + partial_failures（不中断主图）。

    参数：
        无。

    返回值：
        Callable：包装节点函数（state → state 更新 dict）。

    异常：
        不抛出（内部全捕获兜底）。
    """
    compiled = build_recommend_subgraph()

    def subgraph_recommend_node(state: dict) -> dict:
        """推荐子图包装节点（函数）。

        参数：
            state：主图编排状态。

        返回值：
            dict：{"candidates", "filtered_candidates", "filtered_by", "results",
            "nutrition", "partial_failures", "resolved_ingredient_ids",
            "resolved_ingredient_names", "trace": [子图全部 span + 自身 span]}。

        异常：
            不抛出。
        """
        start = now_ms()
        sub_input = {
            "request_id": state.get("request_id"),
            "trace_id": state.get("trace_id"),
            "input_text": state.get("input_text") or "",
            "ingredients": state.get("ingredients") or [],
            "safety_profile": state.get("safety_profile") or {},
            # E.9 反馈接线：透传数字 user_id（runner 未注入时为 None，rank 节点空惩罚）
            "user_id": state.get("user_id"),
        }
        try:
            sub_out = compiled.invoke(sub_input, config={"recursion_limit": 40})
        except Exception as exc:  # noqa: BLE001 —— 子图失败不中断主图，compose 如实标注
            logger.error("recommend subgraph failed: %s", exc)
            own = make_span("subgraph_recommend", "failed", now_ms() - start)
            return {
                "results": [],
                "partial_failures": ["推荐子图执行失败，已降级为空结果"],
                "trace": [own],
            }
        own = make_span("subgraph_recommend", "ok", now_ms() - start)
        # 主图 trace 键合并子图全部 span（operator.add；子图 schema 隔离保证无重复）
        return {
            "resolved_ingredient_ids": sub_out.get("resolved_ingredient_ids") or [],
            "resolved_ingredient_names": sub_out.get("resolved_ingredient_names") or [],
            "candidates": sub_out.get("candidates") or [],
            "filtered_candidates": sub_out.get("filtered_candidates") or [],
            "filtered_by": sub_out.get("filtered_by") or {},
            "results": sub_out.get("results") or [],
            "nutrition": sub_out.get("nutrition") or {},
            "partial_failures": sub_out.get("partial_failures") or [],
            "trace": list(sub_out.get("sub_trace") or []) + [own],
        }

    return subgraph_recommend_node


# ---- 注册（子图以包装节点形式作为一个主图节点；内部节点由子图 builder 装配）----
register("subgraph_recommend", make_recommend_subgraph_node, forms="subgraph", timeout_ms=5000, description="推荐子图：召回 → 布尔硬过滤 → 排序 ∥ 营养并行")
