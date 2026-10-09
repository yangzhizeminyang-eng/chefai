"""AI 菜品创新主图入口节点模块（模块 O 主图接线）。

职责：
    node_innovation_entry：主图 intent='innovation' 的专用处理节点——
    从编排状态解析食材与用户身份，调用创新子图入口
    （run_innovation_precheck / run_innovation_generate，T7 实现），把结果
    模板化为 qa_answer（经 compose → output_guard 既有出口链路复核）。

红线（与子图口径一致）：
    - 搭配结论查表（flavor_pairing_rule），LLM 无权决定搭配（由子图保证）；
    - 含过敏原食材直接拒绝（precheck 内置，risk_log 留痕）；
    - 本节点为模板拼接 + 子图结果透传，不额外生成任何内容（RL-11）；
    - 节点内部全捕获异常，降级为固定引导话术（M.5 部分输出，绝不中断主图）。

说明：
    本节点位于 supervisor 之后、compose 之前（无绕闸路径）；
    已录入 BUSINESS_NODE_NAMES（一票否决时补 not_executed 取证）。
"""

from __future__ import annotations

from sqlalchemy import select

from app.core.db import SessionLocal
from app.core.logging import get_logger
from app.graph.nodes.common import BUSINESS_NODE_NAMES, make_span, now_ms
from app.graph.nodes.intent_ops import _coerce_user_id
from app.graph.registry import register
from app.models import Ingredient

logger = get_logger(__name__)

# ---- 话术模板（RL-11：固定话术不由模型生成）----
INNO_DEGRADED_TEXT = (
    "AI 创新暂时不可用，请稍后再试。你也可以直接从推荐结果中挑选菜谱，"
    "或在「AI 创新」页使用食材组合创新功能。"
)
INNO_NO_INGREDIENTS_TEXT = (
    "请告诉我想用哪些食材创新（或先在「AI 创新」页选择食材），"
    "我会基于食材性质与搭配规则为你生成一道创新菜。"
)
INNO_NO_IDENTITY_TEXT = "请先进入任意页面获取匿名身份后，再使用 AI 创新功能。"
INNO_DISCLAIMER = "AI 创新·未经人工审核，仅供参考，请勿用于特殊人群。"


def _resolve_ingredient_names(state: dict) -> list[str]:
    """从编排状态解析创新食材名列表（函数）。

    说明：
        优先取 payload 注入的 ingredients（字符串/字典两种形态归一化）；
        为空时对 input_text 做 ILIKE 最佳努力匹配（限 5 个，匹配不到返回空列表）。

    参数：
        state：编排状态（ingredients/input_text 可缺省）。

    返回值：
        list[str]：食材名列表（可能为空）。

    异常：
        不抛出（查库异常返回空列表）。
    """
    names: list[str] = []
    for item in state.get("ingredients") or []:
        if isinstance(item, str) and item.strip():
            names.append(item.strip())
        elif isinstance(item, dict) and item.get("name"):
            names.append(str(item["name"]).strip())
    if names:
        return names
    text = str(state.get("input_text") or "").strip()
    if not text:
        return []
    try:
        with SessionLocal() as session:
            candidates = session.execute(select(Ingredient.name).limit(300)).scalars().all()
        matched = [str(c) for c in candidates if str(c) and str(c) in text]
        return matched[:5]
    except Exception as exc:  # noqa: BLE001 —— 解析失败返回空列表走引导话术
        logger.warning("innovation_entry resolve ingredients failed: %s", exc)
        return []


def _render_recipe_text(result: dict) -> str:
    """把创新菜结果 dict 渲染为面向用户的模板文本（函数）。

    参数：
        result：创新子图返回的 result 结构（name/ingredients/steps/basis/...）。

    返回值：
        str：模板化介绍文本（含用量/步骤/依据/免责声明）。

    异常：
        不抛出（字段缺失按空串处理）。
    """
    lines: list[str] = [f"已为你创新一道菜：《{result.get('name') or '未命名创新菜'}》"]
    ingredients = result.get("ingredients") or []
    if ingredients:
        parts = []
        for ing in ingredients[:8]:
            name = ing.get("name") if isinstance(ing, dict) else str(ing)
            amount = ing.get("amount") if isinstance(ing, dict) else ""
            unit = ing.get("unit") if isinstance(ing, dict) else ""
            parts.append(f"{name} {amount}{unit}".strip())
        lines.append("食材用量：" + "；".join(parts))
    steps = result.get("steps") or []
    if steps:
        first = steps[0] if isinstance(steps[0], dict) else {}
        lines.append(f"共 {len(steps)} 步，第一步：{str(first.get('description') or '')[:60]}")
    basis = result.get("basis") or {}
    pairings = basis.get("pairings") or []
    if pairings:
        p0 = pairings[0]
        if isinstance(p0, dict):
            lines.append(
                f"创新依据：{p0.get('a')} 与 {p0.get('b')} 为推荐搭配（{p0.get('rationale') or '风味亲和'}）"
            )
    lines.append(INNO_DISCLAIMER)
    return "\n".join(lines)


def make_node_innovation_entry():
    """AI 创新主图入口节点工厂（函数）。

    说明：
        创新子图入口函数在工厂内延迟导入——规避
        runner → nodes/__init__ → 本模块 → subgraphs.innovation → runner
        的循环导入（runner 初始化早于 nodes 包）。

    返回值：
        Callable：节点函数。

    异常：
        无。
    """
    # 延迟导入（见 docstring：规避循环导入）
    from app.graph.subgraphs.innovation import run_innovation_generate, run_innovation_precheck

    def node_innovation_entry(state: dict) -> dict:
        """AI 创新主图入口节点（函数）。

        说明：
            - 食材为空 → 引导话术（ok span）；
            - 无数字 user_id → 身份引导话术（degraded span）；
            - 先跑 precheck：blocked → qa_answer=拦截话术 + notice 标记；
            - 通过 → run_innovation_generate（子图内含性质/搭配/生成/落库）：
              成功渲染菜谱文本；失败/异常降级固定话术。

        参数：
            state：编排状态（user_id/ingredients/input_text/request_id 等）。

        返回值：
            dict：{"qa_answer": 文本, "notice": 提示, "trace": [span]}。

        异常：
            不抛出（内部全捕获，降级话术兜底）。
        """
        start = now_ms()
        uid = _coerce_user_id(state)
        names = _resolve_ingredient_names(state)
        request_id = str(state.get("request_id") or "") or None
        user_id_hash = state.get("user_id_hash")

        if not names:
            span = make_span("node_innovation_entry", "ok", now_ms() - start)
            return {"qa_answer": INNO_NO_INGREDIENTS_TEXT, "trace": [span]}
        if uid is None:
            span = make_span("node_innovation_entry", "degraded", now_ms() - start)
            return {"qa_answer": INNO_NO_IDENTITY_TEXT, "trace": [span]}

        try:
            pre = run_innovation_precheck(uid, names, request_id)
            if pre.get("blocked"):
                issues = pre.get("issues") or []
                message = str(issues[0].get("message")) if issues and isinstance(issues[0], dict) else "该组合未通过安全前置校验。"
                span = make_span("node_innovation_entry", "ok", now_ms() - start, rule_hit="innovation_precheck")
                return {"qa_answer": message, "notice": "innovation_blocked", "trace": [span]}

            gen = run_innovation_generate(uid, names, request_id, user_id_hash)
            if gen.get("ok") and gen.get("result"):
                span = make_span("node_innovation_entry", "ok", now_ms() - start)
                return {
                    "qa_answer": _render_recipe_text(gen["result"]),
                    "notice": "innovation_generated",
                    "trace": [span],
                }
            issues = gen.get("issues") or []
            message = str(issues[0].get("message")) if issues and isinstance(issues[0], dict) else INNO_DEGRADED_TEXT
            span = make_span("node_innovation_entry", "degraded", now_ms() - start)
            return {"qa_answer": message, "trace": [span]}
        except Exception as exc:  # noqa: BLE001 —— 全捕获降级（M.5 部分输出）
            logger.warning("node_innovation_entry degraded: %s", exc)
            span = make_span("node_innovation_entry", "degraded", now_ms() - start)
            return {"qa_answer": INNO_DEGRADED_TEXT, "trace": [span]}

    return node_innovation_entry


# ---- 注册（主图 INTENT_ROUTES 'innovation' → node_innovation_entry）----
register(
    "node_innovation_entry",
    make_node_innovation_entry,
    forms="subgraph",
    timeout_ms=8000,
    description="AI 创新主图入口：precheck→generate 透传（拦截/降级均模板化）",
)

# 录入业务节点清单（一票否决时补 not_executed 取证）
if "node_innovation_entry" not in BUSINESS_NODE_NAMES:
    BUSINESS_NODE_NAMES = (*BUSINESS_NODE_NAMES, "node_innovation_entry")
