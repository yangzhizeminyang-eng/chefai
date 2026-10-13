"""AI 菜品创新子图模块（模块 O，subgraph_innovation）。

职责：
    装配创新子图（阶段二模块 O）：

        START → innovation_precheck → innovation_property_match
              → innovation_pairing_check → innovation_generate → END

    - innovation_precheck：安全前置（🔴 红线节点）——食材逐个过 RiskEngine input
      闸门（高危 → 拦截 + risk_log 留痕）；用户档案过敏原 ∩ 食材致敏原非空 →
      直接拒绝（比过滤更严，rule_code=INNOVATION_ALLERGEN）；特殊人群（孕妇/
      婴幼儿等）+ 高危食材组合 → 拒绝（INNOVATION_SPECIAL_POP）。
    - innovation_property_match：查 ingredient_property 表逐食材取五属性
      （texture/moisture/flavor/heat_tolerance/oil_absorption），缺属性食材标注
      「性质数据待补充」，不阻断流程。
    - innovation_pairing_check：查 flavor_pairing_rule 表对食材两两组合——
      🔴 红线：搭配结论必须查表，LLM 无权决定搭配。taboo 命中 → 直接拒绝；
      conflict 命中 → 记入依据并要求 generate 避开；recommend 命中 → 正向依据；
      技法建议须在 technique_library 白名单（in_whitelist=true）内才允许进 prompt。
    - innovation_generate：受约束生成——LLM 输出 JSON（技法白名单约束 + 用量
      100% 量化（禁「适量/少许/若干」）+ 步骤含 duration_sec）；LLM 表达调用带
      25s 硬超时（_chat_with_hard_timeout，P1 DEF-01：前端创新生成请求专用超时
      60s，后端必须在其内给出确定性响应）；LLM 超时/失败/量化违例重试后再违例
      均降级本地规则模板生成器（沿用配比模板量化用量 + 技法白名单 + 搭配依据，
      无 LLM 环境演示可用，输出 100% 量化）；生成来源落 basis.generated_by
      （成功 LLM="llm"、降级="template"）；生成后过 RiskEngine output 闸门；
      落库 innovation_recipe（status='generated'、is_ai_innovated=True（模型默认
      恒真）、visibility='private'、basis 引用搭配规则与性质可追溯）。

接线说明：
    本子图暂由 API 层（app/api/v1/innovation.py）经 run_innovation_generate /
    run_innovation_precheck 直接调用，不依赖主图意图路由；主控后续统一接线
    （本模块【不调用 register()】，避免孤立节点破坏主图装配——主图 INTENT_ROUTES
    接入 innovation 意图后由主图任务补注册）。
"""

from __future__ import annotations

import concurrent.futures
import json
import operator
import re
import uuid
from typing import Annotated, TypedDict

from langgraph.graph import END, START, StateGraph
from sqlalchemy import select
from sqlalchemy.orm import aliased

from app.ability.llm import LLMError, get_llm_client
from app.core.db import SessionLocal
from app.core.logging import get_logger
from app.graph.nodes.common import TXT_G06, make_span, now_ms, persist_trace
from app.graph.runner import load_profile_from_db
from app.models import (
    FlavorPairingRule,
    Ingredient,
    IngredientAlias,
    IngredientNutrition,
    IngredientProperty,
    InnovationRecipe,
    RiskLog,
    TechniqueLibrary,
)
from app.safety.engine import get_risk_engine
from app.schemas.innovation import DISCLAIMER_TEXT

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# 量化校验白名单（🔴 用量必须量化：CT-6 口径在生成层的延伸）
# ---------------------------------------------------------------------------
# 合法用量单位（生成结果 unit 必须命中，否则视为未量化）
_UNIT_WHITELIST = frozenset({
    "g", "克", "千克", "kg", "ml", "毫升", "升", "l", "个", "只", "根", "片",
    "颗", "瓣", "勺", "大勺", "小勺", "茶匙", "汤匙", "滴", "包", "盒", "袋",
    "块", "朵", "把", "张", "杯", "碗", "段", "条", "枚", "粒",
})

# 模糊用量违禁词（生成文本中出现即视为未量化，触发重试/本地模板替换）
_VAGUE_WORDS: tuple[str, ...] = ("适量", "少许", "若干", "随意")

# 本地模板主料量化兜底序列（按食材顺序取用，保证 100% 量化）
_LOCAL_MAIN_AMOUNTS: tuple[tuple[float, str], ...] = (
    (250.0, "g"), (150.0, "g"), (100.0, "g"), (80.0, "g"), (60.0, "g"),
)

# 本地模板固定调味料（同样 100% 量化）
_LOCAL_SEASONINGS: tuple[dict, ...] = (
    {"name": "食用油", "amount": 15.0, "unit": "ml"},
    {"name": "盐", "amount": 2.0, "unit": "g"},
    {"name": "生抽", "amount": 10.0, "unit": "ml"},
)

# ---------------------------------------------------------------------------
# LLM 表达硬超时（P1 DEF-01）：LLM 表达实测可达 30s+，openai SDK 内部还带网络
# 重试，仅靠客户端 timeout 挡不住；前端创新生成请求专用超时 60s，后端必须在其
# 内给出确定性响应 → LLM 调用超过 LLM_HARD_TIMEOUT_SECONDS 即放弃并降级规则模板。
# 阶段二调整 25.0 → 80.0：DeepSeek 长结构化输出（创新菜谱 JSON）实测单次 60s+（本地
# 日志 09:00:36→09:01:44→09:02:55 三连间隔），25/55s 均频繁触发模板降级（"X炒Y"式
# 直出，用户感知为"没有智能体思考"）；80s 仍在小程序 100s 轮询窗口内（web 端专用
# 请求超时 60s 的旧约束已被异步 job 化取代，generate 同步接口保留 60s 供兼容），
# 超时仍有模板兜底，不影响确定性响应承诺。
# ---------------------------------------------------------------------------
LLM_HARD_TIMEOUT_SECONDS = 80.0

# LLM 硬超时执行器（进程级线程池复用）。刻意不用 with 上下文：with 退出会 join
# 尚未返回的 LLM 线程，令超时失效；超时后线程在后台继续跑完（LLM 客户端自带
# 请求超时，线程最终必然终止），其结果被丢弃。
_LLM_EXECUTOR = concurrent.futures.ThreadPoolExecutor(max_workers=2, thread_name_prefix="innovation_llm")


def _chat_with_hard_timeout(client, system: str, user: str, temperature: float):
    """带硬超时的 LLM 表达调用（函数，P1 DEF-01 降级路径入口）。

    说明：
        将 client.chat 提交到进程级线程池并以 future.result(timeout=...) 等待；
        超过 LLM_HARD_TIMEOUT_SECONDS 抛 LLMError（调用方据此走规则模板降级），
        不再阻塞请求线程。测试可通过 monkeypatch 模块属性 LLM_HARD_TIMEOUT_SECONDS
        调小以模拟超时。

    参数：
        client：LLM 客户端（app.ability.llm.LLMClient 或同签名替身）。
        system：系统提示词。
        user：用户消息。
        temperature：采样温度。

    返回值：
        LLMResult：补全结果（与 client.chat 同口径）。

    异常：
        LLMError：等待超时（concurrent.futures.TimeoutError 归一包装）或线程内
        chat 抛出的 LLMError 原样透传。
    """
    future = _LLM_EXECUTOR.submit(client.chat, system, user, temperature)
    try:
        return future.result(timeout=LLM_HARD_TIMEOUT_SECONDS)
    except concurrent.futures.TimeoutError as exc:
        future.cancel()  # 运行中的 future 无法取消，仅尽力标记；结果由 GC 丢弃
        raise LLMError(f"LLM hard timeout after {LLM_HARD_TIMEOUT_SECONDS}s") from exc


class InnovationState(TypedDict, total=False):
    """创新子图内部状态（模型类）。

    说明：
        独立于主图 CookingState（trace 字段名为 sub_trace，operator.add reducer），
        与 recommend 子图同惯例：避免与主图同名 trace channel 互相继承导致 span
        重复累加；本子图由 API 层直接 invoke（初态只注入请求上下文）。

    字段：
        request_id / trace_id / user_id_hash：请求元信息（取证与 trace 落库）。
        user_db_id：用户数据库 ID（precheck 读档案、generate 落库归属，🔴 必填）。
        ingredients：用户原始食材名列表（字符串）。
        blocked：是否被安全前置拦截（拦截后后续节点短路跳过）。
        issues：拦截原因列表（[{type, message}]）。
        risk_log_written：precheck 是否写入了 risk_log 留痕。
        resolved_ingredients：食材解析结果（[{name, ingredient_id|None}]，保序）。
        resolved_ingredient_ids / resolved_ingredient_names：解析出的 ID 与名称。
        properties：食材五属性列表（缺失项 missing=true 标注）。
        pairings：搭配规则命中列表（recommend+conflict，含 rule_id 供回流）。
        techniques_whitelist：technique_library 白名单技法名列表。
        generated_by：生成来源（llm = LLM 表达成功 / template = LLM 硬超时或失败后
          的规则模板降级）。
        result：最终创新菜响应 dict（generate 落库后产出）。
        sub_trace：子图内 trace span 列表（operator.add 累加）。
    """

    request_id: str
    trace_id: str
    user_id_hash: str
    user_db_id: int
    ingredients: list
    blocked: bool
    issues: list
    risk_log_written: bool
    resolved_ingredients: list
    resolved_ingredient_ids: list
    resolved_ingredient_names: list
    properties: list
    pairings: list
    techniques_whitelist: list
    generated_by: str
    result: dict
    sub_trace: Annotated[list[dict], operator.add]


# ---------------------------------------------------------------------------
# 内部工具：食材解析 / 搭配查表 / risk_log 留痕
# ---------------------------------------------------------------------------
def _lookup_ingredient(session, name: str) -> tuple[int, str] | None:
    """按名称/别名查询单个食材（函数）。

    说明：
        食材名精确命中优先，别名次之（与推荐子图 assemble_context 同口径）。

    参数：
        session：数据库会话。
        name：食材名称或别名。

    返回值：
        tuple[int, str] | None：(ingredient_id, 展示名)；未命中返回 None。

    异常：
        查询异常向上抛出（由调用方统一捕获降级）。
    """
    ing_id = session.execute(
        select(Ingredient.id).where(Ingredient.name == name)
    ).scalar_one_or_none()
    if ing_id is not None:
        return int(ing_id), name
    row = session.execute(
        select(IngredientAlias.ingredient_id, IngredientAlias.alias)
        .where(IngredientAlias.alias == name)
        .limit(1)
    ).first()
    if row:
        return int(row[0]), str(row[1])
    return None


def _query_pairings(session, ids: list[int], relations: tuple[str, ...] = ("recommend", "conflict")) -> list[dict]:
    """按食材 ID 集合查询搭配规则命中（函数）。

    说明：
        🔴 搭配结论必须查表（LLM 无权决定搭配）：条件为 ingredient_a 与
        ingredient_b 均在用户食材 ID 集合中（无向语义，方向由表行决定）。

    参数：
        session：数据库会话。
        ids：解析出的食材 ID 列表。
        relations：要查询的 relation 集合（recommend/conflict/taboo 子集）。

    返回值：
        list[dict]：[{rule_id, ingredient_a, ingredient_b, relation, technique,
        rationale, weight}]（technique 未经白名单过滤，由调用方处理）。

    异常：
        查询异常向上抛出（由调用方统一捕获降级）。
    """
    a = aliased(Ingredient)
    b = aliased(Ingredient)
    rows = session.execute(
        select(FlavorPairingRule, a.name, b.name)
        .join(a, a.id == FlavorPairingRule.ingredient_a_id)
        .join(b, b.id == FlavorPairingRule.ingredient_b_id)
        .where(FlavorPairingRule.relation.in_(list(relations)))
        .where(a.id.in_(ids), b.id.in_(ids))
    ).all()
    return [
        {
            "rule_id": int(rule.id),
            "ingredient_a": str(a_name),
            "ingredient_b": str(b_name),
            "relation": str(rule.relation),
            "technique": (str(rule.technique_suggestion) if rule.technique_suggestion else None),
            "rationale": str(rule.rationale),
            "weight": float(rule.weight),
        }
        for rule, a_name, b_name in rows
    ]


def _query_whitelist_techniques(session) -> list[str]:
    """查询技法白名单（函数）。

    说明：
        仅 in_whitelist=true 的技法允许进生成 prompt（🔴 白名单约束）。

    参数：
        session：数据库会话。

    返回值：
        list[str]：白名单技法名列表。

    异常：
        查询异常向上抛出（由调用方统一捕获降级）。
    """
    rows = session.execute(
        select(TechniqueLibrary.name).where(TechniqueLibrary.in_whitelist.is_(True))
    ).scalars().all()
    return [str(n) for n in rows]


def _write_risk_log(
    request_id: str,
    user_id: int | None,
    rule_code: str | None,
    category: str | None,
    risk_level: str | None,
    input_digest: str,
    message_id: str | None,
    action: str = "blocked",
) -> bool:
    """写创新域风控留痕 risk_log（函数）。

    说明：
        拦截/保守时留痕取证；rule_code 使用自定义创新域规则 ID
        （INNOVATION_ALLERGEN / INNOVATION_SPECIAL_POP / INNOVATION_TABOO）或
        RiskEngine 命中的既有 rule_code（如 FS-003）。

    参数：
        request_id：请求唯一标识。
        user_id：用户数据库 ID（可 None）。
        rule_code：规则编码（可 None 表示引擎 UNKNOWN 保守）。
        category：风险类别（可 None）。
        risk_level：风险等级（可 None）。
        input_digest：脱敏输入摘要（食材名拼接，截断 200 字符）。
        message_id：命中话术模板 ID（可 None）。
        action：动作（blocked / safe_mode）。

    返回值：
        bool：写入成功返回 True（失败仅告警，不阻断拦截语义）。

    异常：
        不抛出（内部全捕获）。
    """
    try:
        with SessionLocal() as session:
            session.add(
                RiskLog(
                    request_id=str(request_id)[:40],
                    user_id=user_id,
                    stage="input",
                    rule_code=(str(rule_code)[:30] if rule_code else None),
                    category=(str(category)[:30] if category else None),
                    risk_level=(str(risk_level)[:10] if risk_level else None),
                    input_digest=(input_digest or "")[:200],
                    action=action,
                    message_id=(str(message_id)[:40] if message_id else None),
                )
            )
            session.commit()
        return True
    except Exception as exc:  # noqa: BLE001 —— 留痕失败不影响拦截语义
        logger.error("write innovation risk_log failed (request_id=%s): %s", request_id, exc)
        return False


def _risk_message_text(message_id: str | None) -> str | None:
    """按话术模板 ID 取拦截话术（函数）。

    参数：
        message_id：risk_message.message_id（可 None）。

    返回值：
        str | None：话术 body；未命中/异常返回 None（调用方用默认话术兜底）。

    异常：
        不抛出（get_message 内部全捕获）。
    """
    body = get_risk_engine().get_message(message_id)
    if body and body.get("body"):
        return str(body["body"])
    return None


# ---------------------------------------------------------------------------
# precheck 核心逻辑（precheck 接口与子图 precheck 节点复用同一函数）
# ---------------------------------------------------------------------------
def run_precheck_core(user_db_id: int | None, ingredients: list[str], request_id: str | None = None) -> dict:
    """创新预检核心逻辑（函数，🔴 红线集中实现）。

    说明：
        顺序执行四道拦截（任一命中即短路返回 blocked）：
        1. 食材逐个过 RiskEngine input 闸门（高危 → 拦截，risk_log 留痕）；
        2. 用户档案过敏原 ∩ 食材致敏原非空 → 直接拒绝（比过滤更严）；
        3. 特殊人群 + 高危食材组合（存在任何 input 规则命中）→ 拒绝；
        4. flavor_pairing_rule taboo 查表命中 → 拒绝。
        任何数据库/引擎异常均按「宁拦不放」保守处理（UNKNOWN → 拦截）。

    参数：
        user_db_id：用户数据库 ID（None 时不做过敏原/特殊人群检查）。
        ingredients：用户食材名列表（字符串）。
        request_id：请求唯一标识（缺省自动生成）。

    返回值：
        dict：{ok, blocked, issues, risk_log_written, resolved_ingredients,
        resolved_ingredient_ids, resolved_ingredient_names, pairings}
        （pairings 为命中的 recommend 依据，供预检展示与生成复用）。

    异常：
        不抛出（内部全捕获，异常按拦截处理）。
    """
    request_id = request_id or f"inn_{uuid.uuid4().hex[:12]}"
    digest = " ".join(str(i) for i in ingredients)[:200]
    empty = {
        "resolved_ingredients": [],
        "resolved_ingredient_ids": [],
        "resolved_ingredient_names": [],
        "pairings": [],
    }

    # ---- 1) 解析食材（名称/别名 → ingredient_id，保序）----
    resolved: list[dict] = []
    allergen_by_id: dict[int, list] = {}
    try:
        with SessionLocal() as session:
            for raw in ingredients:
                name = str(raw).strip()
                if not name:
                    continue
                hit = _lookup_ingredient(session, name)
                resolved.append(
                    {
                        "name": hit[1] if hit else name,
                        "ingredient_id": int(hit[0]) if hit else None,
                    }
                )
            ids = [r["ingredient_id"] for r in resolved if r["ingredient_id"] is not None]
            if ids:
                rows = session.execute(
                    select(Ingredient.id, Ingredient.allergen_codes).where(Ingredient.id.in_(ids))
                ).all()
                allergen_by_id = {int(i): list(c or []) for i, c in rows}
    except Exception as exc:  # noqa: BLE001 —— 🔴 解析失败按「校验不可用」保守拦截
        logger.error("innovation precheck resolve failed: %s", exc)
        return {
            "ok": False,
            "blocked": True,
            "issues": [{"type": "high_risk", "message": TXT_G06}],
            "risk_log_written": False,
            **empty,
        }

    names = [r["name"] for r in resolved]
    ids = [r["ingredient_id"] for r in resolved if r["ingredient_id"] is not None]

    # ---- 2) 高危闸门：食材逐个过 RiskEngine input（逐个扫描，避免安全食材拼接误伤组合规则）----
    engine = get_risk_engine()
    any_hit = False
    for item in resolved:
        verdict = engine.scan("input", item["name"])
        if verdict.status == "UNKNOWN":
            # 🔴 风控不可用 → 保守模式，绝不放行
            written = _write_risk_log(request_id, user_db_id, None, None, None, digest, None, action="safe_mode")
            return {
                "ok": False,
                "blocked": True,
                "issues": [{"type": "high_risk", "message": TXT_G06}],
                "risk_log_written": written,
                **empty,
            }
        if verdict.hit:
            any_hit = True
            if verdict.block:
                message = _risk_message_text(verdict.message_id) or "您选择的食材存在高风险，AI 创新功能已停止"
                written = _write_risk_log(
                    request_id, user_db_id, verdict.rule_code, verdict.category,
                    verdict.risk_level, digest, verdict.message_id,
                )
                return {
                    "ok": False,
                    "blocked": True,
                    "issues": [{"type": "high_risk", "message": message}],
                    "risk_log_written": written,
                    **empty,
                }

    # ---- 3) 用户档案（过敏原 / 特殊人群）----
    profile: dict = {}
    if user_db_id:
        try:
            with SessionLocal() as session:
                profile = load_profile_from_db(session, int(user_db_id))
        except Exception as exc:  # noqa: BLE001 —— 档案读取失败按空档案（与 runner 同口径）
            logger.warning("innovation precheck load profile failed: %s", exc)
            profile = {}

    # ---- 4) 🔴 过敏原直接拒绝（比过滤更严：非空交集即停）----
    user_allergens = {str(c).strip() for c in (profile.get("allergen_codes") or []) if str(c).strip()}
    if user_allergens:
        allergen_hits: list[tuple[str, list[str]]] = []
        for item in resolved:
            ing_allergens = set(allergen_by_id.get(item["ingredient_id"] or -1) or [])
            inter = sorted(user_allergens & {str(c).strip() for c in ing_allergens})
            if inter:
                allergen_hits.append((item["name"], inter))
        if allergen_hits:
            detail = "、".join(f"{name}（{'/'.join(codes)}）" for name, codes in allergen_hits[:3])
            written = _write_risk_log(
                request_id, user_db_id, "INNOVATION_ALLERGEN", "allergen", "high", digest, None
            )
            return {
                "ok": False,
                "blocked": True,
                "issues": [{
                    "type": "allergen",
                    "message": f"您选择的食材中含有您的过敏原（{detail}），AI 创新功能已停止",
                }],
                "risk_log_written": written,
                **empty,
            }

    # ---- 5) 特殊人群 + 高危食材组合 → 拒绝 ----
    special = {str(c).strip() for c in (profile.get("special_population") or []) if str(c).strip()}
    if special and any_hit:
        written = _write_risk_log(
            request_id, user_db_id, "INNOVATION_SPECIAL_POP", "special_population", "high", digest, None
        )
        return {
            "ok": False,
            "blocked": True,
            "issues": [{
                "type": "special_population",
                "message": "特殊人群（孕妇、婴幼儿等）不建议尝试高风险食材组合，AI 创新功能已停止",
            }],
            "risk_log_written": written,
            **empty,
        }

    # ---- 6) 🔴 taboo 查表（结论必须查表，LLM 无权决定搭配）----
    taboo_hits: list[dict] = []
    recommend_hits: list[dict] = []
    try:
        with SessionLocal() as session:
            if len(ids) >= 2:
                taboo_hits = _query_pairings(session, ids, relations=("taboo",))
                recommend_hits = _query_pairings(session, ids, relations=("recommend",))
    except Exception as exc:  # noqa: BLE001 —— 🔴 查表失败保守拦截（搭配结论宁缺勿错）
        logger.error("innovation precheck pairing query failed: %s", exc)
        return {
            "ok": False,
            "blocked": True,
            "issues": [{"type": "taboo", "message": TXT_G06}],
            "risk_log_written": False,
            **empty,
        }
    if taboo_hits:
        detail = "、".join(f"{t['ingredient_a']}与{t['ingredient_b']}" for t in taboo_hits[:3])
        written = _write_risk_log(
            request_id, user_db_id, "INNOVATION_TABOO", "pairing_taboo", "high", digest, None
        )
        return {
            "ok": False,
            "blocked": True,
            "issues": [{"type": "taboo", "message": f"{detail}的组合不适合同烹，已停止创新"}],
            "risk_log_written": written,
            **empty,
        }

    return {
        "ok": True,
        "blocked": False,
        "issues": [],
        "risk_log_written": False,
        "resolved_ingredients": resolved,
        "resolved_ingredient_ids": ids,
        "resolved_ingredient_names": names,
        "pairings": recommend_hits,
    }


# ---------------------------------------------------------------------------
# 生成层：prompt 构建 / JSON 解析 / 量化校验 / 本地模板降级 / 营养估算
# ---------------------------------------------------------------------------
def _build_prompts(
    names: list[str],
    properties: list[dict],
    pairings: list[dict],
    techniques: list[str],
) -> tuple[str, str]:
    """构建受约束生成的系统/用户提示词（函数）。

    说明：
        🔴 系统提示硬性约束：技法白名单 + 用量必须量化（禁「适量/少许/若干」，
        给克/个/勺）+ 步骤可执行（含时长秒）+ 输出 JSON 结构 + 引用查表依据；
        conflict 项要求生成时避开同锅。

    参数：
        names：食材名列表。
        properties：食材五属性列表。
        pairings：搭配规则命中列表（recommend+conflict）。
        techniques：技法白名单名列表。

    返回值：
        tuple[str, str]：(system, user) 提示词。

    异常：
        无。
    """
    recommends = [p for p in pairings if p.get("relation") == "recommend"]
    conflicts = [p for p in pairings if p.get("relation") == "conflict"]
    system = (
        "你是受约束的 AI 菜品创新引擎，只能输出一个 JSON 对象，不得输出任何其他文字。\n"
        "硬性约束：\n"
        f"1. 烹饪技法只能从以下白名单中选择：{'、'.join(techniques) if techniques else '炒、蒸、煮、拌'}。\n"
        "2. 每种食材用量必须量化：amount 为正数，unit 只能取 g/ml/个/勺/片/根/颗/瓣 等计量单位；"
        "严禁使用「适量、少许、若干、随意」等模糊表述。\n"
        "3. 每个步骤必须给出 duration_sec（正整数秒）与可执行的具体描述。\n"
        "4. 搭配结论以下方查表依据为准，不得引入给定食材之外的主料；"
        "标注为 conflict 的组合不得同锅烹制。\n"
        '5. 输出 JSON 结构：{"name": 菜名, "ingredients": [{"name": 食材, "amount": 数值, "unit": 单位}], '
        '"steps": [{"no": 序号, "description": 步骤描述, "duration_sec": 秒数, "tips": 要点}]}'
    )
    prop_lines = [
        (
            f"- {p['name']}：质地 {p.get('texture') or '待补充'}，含水量 {p.get('moisture') or '待补充'}，"
            f"风味 {p.get('flavor') or '待补充'}，耐热 {p.get('heat_tolerance') or '待补充'}，"
            f"吸油 {p.get('oil_absorption') or '待补充'}"
        )
        for p in properties
    ]
    rec_lines = [
        f"- {p['ingredient_a']} × {p['ingredient_b']}：推荐搭配（建议技法 {p.get('technique') or '不限'}），"
        f"依据：{p['rationale']}"
        for p in recommends
    ]
    con_lines = [f"- {p['ingredient_a']} × {p['ingredient_b']}：风味冲突，不可同锅，依据：{p['rationale']}" for p in conflicts]
    user = (
        f"请用以下食材创新一道家常菜：{'、'.join(names)}。\n"
        "食材性质（查表依据）：\n" + ("\n".join(prop_lines) if prop_lines else "- 暂无性质数据") + "\n"
        "搭配规则（查表依据）：\n" + ("\n".join(rec_lines) if rec_lines else "- 无推荐搭配命中") + "\n"
        + (("风味冲突（必须避开）：\n" + "\n".join(con_lines) + "\n") if con_lines else "")
        + "请输出 JSON。"
    )
    return system, user


def _strip_json_fence(text: str) -> str:
    """剥离 LLM 输出中的 Markdown 代码围栏（函数）。

    参数：
        text：模型原始输出文本。

    返回值：
        str：去掉 ```json ... ``` 围栏后的文本。

    异常：
        无。
    """
    stripped = (text or "").strip()
    if stripped.startswith("```"):
        stripped = re.sub(r"^```(?:json)?\s*", "", stripped)
        stripped = re.sub(r"\s*```$", "", stripped)
    return stripped.strip()


def _parse_llm_recipe(content: str) -> dict | None:
    """解析 LLM 输出为创新菜草稿（函数）。

    说明：
        剥离代码围栏后 json.loads；结构不完整（缺 name/ingredients/steps 或元素
        非法）返回 None（由调用方触发重试或本地模板降级）。

    参数：
        content：模型输出文本。

    返回值：
        dict | None：{name, ingredients: [{name, amount, unit}], steps: [{no,
        description, duration_sec, tips}]}；解析失败返回 None。

    异常：
        不抛出（内部全捕获返回 None）。
    """
    try:
        data = json.loads(_strip_json_fence(content))
    except Exception:  # noqa: BLE001
        return None
    if not isinstance(data, dict):
        return None
    name = str(data.get("name") or "").strip()
    raw_ingredients = data.get("ingredients")
    raw_steps = data.get("steps")
    if not name or not isinstance(raw_ingredients, list) or not raw_ingredients:
        return None
    if not isinstance(raw_steps, list) or not raw_steps:
        return None
    ingredients: list[dict] = []
    for item in raw_ingredients:
        if not isinstance(item, dict):
            return None
        ing_name = str(item.get("name") or "").strip()
        if not ing_name:
            return None
        ingredients.append({"name": ing_name, "amount": item.get("amount"), "unit": item.get("unit")})
    steps: list[dict] = []
    for index, item in enumerate(raw_steps, start=1):
        if not isinstance(item, dict):
            return None
        description = str(item.get("description") or "").strip()
        if not description:
            return None
        tips = str(item.get("tips") or "").strip()
        steps.append({
            "no": index,
            "description": description,
            "duration_sec": item.get("duration_sec"),
            "tips": tips or None,
        })
    return {"name": name[:128], "ingredients": ingredients, "steps": steps}


def _is_quantified(draft: dict | None) -> bool:
    """量化校验（函数，🔴 代码强制红线）。

    说明：
        生成结果逐项检查：amount 非空正数值且 unit 在白名单、步骤 duration_sec
        为正数、全文不含模糊用量词（适量/少许/若干/随意）——保证输出 100% 量化。

    参数：
        draft：生成草稿（可 None）。

    返回值：
        bool：全部通过返回 True。

    异常：
        不抛出（结构异常按未量化处理）。
    """
    if not draft or not draft.get("ingredients") or not draft.get("steps"):
        return False
    try:
        for item in draft["ingredients"]:
            amount = item.get("amount")
            if isinstance(amount, bool) or not isinstance(amount, (int, float)) or amount <= 0:
                return False
            if str(item.get("unit") or "").strip() not in _UNIT_WHITELIST:
                return False
        for step in draft["steps"]:
            duration = step.get("duration_sec")
            if isinstance(duration, bool) or not isinstance(duration, (int, float)) or duration <= 0:
                return False
        joined = json.dumps(draft, ensure_ascii=False)
        return not any(word in joined for word in _VAGUE_WORDS)
    except Exception:  # noqa: BLE001
        return False


def _local_template_recipe(names: list[str], pairings: list[dict], techniques: list[str]) -> dict:
    """规则模板生成器（函数，LLM 失败/硬超时降级路径）。

    说明：
        基于搭配规则 recommend 对的建议技法（须在白名单内）+ 常规三步结构拼一道
        简单菜谱，用量 100% 量化（与现有问答兜底同模式），保证无 LLM 环境或
        LLM 硬超时（P1 DEF-01）时主链路仍完整（D7：模型不可用时主链路仍完整）。
        降级时 basis.generated_by 标注 "template"（由调用方写入）。

    参数：
        names：食材名列表。
        pairings：搭配规则命中列表（取 recommend 的 technique_suggestion）。
        techniques：技法白名单名列表。

    返回值：
        dict：{name, ingredients, steps}（全部量化）。

    异常：
        不抛出（空输入兜底为通用菜谱）。
    """
    technique: str | None = None
    for pairing in pairings:
        if (
            pairing.get("relation") == "recommend"
            and pairing.get("technique")
            and (not techniques or pairing["technique"] in techniques)
        ):
            technique = str(pairing["technique"])
            break
    if not technique:
        if techniques:
            technique = "炒" if "炒" in techniques else str(techniques[0])
        else:
            technique = "炒"

    safe_names = [str(n).strip() for n in names if str(n).strip()] or ["食材"]
    if len(safe_names) >= 2:
        name = f"{safe_names[0]}{technique}{safe_names[1]}"
    else:
        name = f"{technique}{safe_names[0]}"

    ingredients: list[dict] = []
    for index, item_name in enumerate(safe_names):
        if "蛋" in item_name:
            amount, unit = 3.0, "个"
        else:
            amount, unit = _LOCAL_MAIN_AMOUNTS[min(index, len(_LOCAL_MAIN_AMOUNTS) - 1)]
        ingredients.append({"name": item_name, "amount": amount, "unit": unit})
    ingredients.extend(dict(seasoning) for seasoning in _LOCAL_SEASONINGS)

    main_text = "、".join(safe_names[:2])
    steps = [
        {
            "no": 1,
            "description": f"预处理：将{main_text}洗净沥干，按标注用量切配成均匀大小，控水备用。",
            "duration_sec": 90,
            "tips": "提前完成切配与控水，受热更均匀。",
        },
        {
            "no": 2,
            "description": (
                f"{technique}制：热锅倒入食用油15ml，油温六成热时下{main_text}，"
                f"{technique}240秒至断生入味。"
            ),
            "duration_sec": 240,
            "tips": f"全程保持{technique}的节奏，避免局部过热糊底。",
        },
        {
            "no": 3,
            "description": "调味出锅：加入盐2g、生抽10ml，翻拌30秒使味道均匀，装盘即可。",
            "duration_sec": 30,
            "tips": "调味料沿锅边淋入更易拌匀。",
        },
    ]
    return {"name": name[:60], "ingredients": ingredients, "steps": steps}


def _estimate_innovation_nutrition(session, ingredients: list[dict], servings: int = 2) -> dict:
    """按 estimate_recipe_nutrition 同口径估算创新菜营养（函数）。

    说明：
        复用 app.ability.nutrition 的克数换算与聚合口径：营养（每 100g）× 克数 / 100；
        无营养数据/无法换算的食材列入 excluded_items（「XX 未纳入统计」，🔴 不按 0 计）。

    参数：
        session：数据库会话。
        ingredients：量化食材列表（[{name, amount, unit}]）。
        servings：份数（默认 2）。

    返回值：
        dict：{servings, total, per_serving, excluded_items, estimate_note}。

    异常：
        不抛出（查询异常按全量 excluded 降级）。
    """
    from app.ability.nutrition import _NUTRIENT_FIELDS, ESTIMATE_NOTE, _resolve_grams  # 口径复用（局部导入）

    total = {field: 0.0 for field in _NUTRIENT_FIELDS}
    excluded: list[str] = []
    nut_by_id: dict[int, IngredientNutrition] = {}
    id_by_name: dict[str, int] = {}
    names = [str(i.get("name") or "").strip() for i in ingredients if str(i.get("name") or "").strip()]
    try:
        if names:
            rows = session.execute(
                select(Ingredient.id, Ingredient.name).where(Ingredient.name.in_(names))
            ).all()
            id_by_name = {str(name): int(iid) for iid, name in rows}
            if id_by_name:
                nut_rows = session.execute(
                    select(IngredientNutrition).where(
                        IngredientNutrition.ingredient_id.in_(list(id_by_name.values()))
                    )
                ).scalars().all()
                nut_by_id = {int(n.ingredient_id): n for n in nut_rows}
    except Exception as exc:  # noqa: BLE001 —— 估算降级为全量 excluded，不阻断落库
        logger.warning("innovation nutrition lookup failed: %s", exc)

    for item in ingredients:
        name = str(item.get("name") or "").strip()
        if not name:
            continue
        grams = _resolve_grams(item.get("amount"), None, None, item.get("unit"), name)
        nutrition = nut_by_id.get(id_by_name.get(name, -1))
        if nutrition is None or nutrition.kcal_100g is None or grams is None:
            reason = "未纳入统计" if (nutrition is None or nutrition.kcal_100g is None) else "用量无法换算"
            excluded.append(f"{name} {reason}")
            continue
        factor = grams / 100.0
        total["kcal"] += float(nutrition.kcal_100g) * factor
        if nutrition.protein_g is not None:
            total["protein_g"] += float(nutrition.protein_g) * factor
        if nutrition.fat_g is not None:
            total["fat_g"] += float(nutrition.fat_g) * factor
        if nutrition.carbs_g is not None:
            total["carbs_g"] += float(nutrition.carbs_g) * factor
        if nutrition.sodium_mg is not None:
            total["sodium_mg"] += float(nutrition.sodium_mg) * factor

    if not any(value > 0 for value in total.values()) and not excluded:
        excluded.append("全部食材 未纳入统计")
    rounded_total = {field: round(value, 1) for field, value in total.items()}
    per_serving = {field: round(value / servings, 1) for field, value in total.items()}
    return {
        "servings": servings,
        "total": rounded_total,
        "per_serving": per_serving,
        "excluded_items": excluded,
        "estimate_note": ESTIMATE_NOTE,
    }


# ---------------------------------------------------------------------------
# 子图节点（工厂模式，与 recommend 子图一致）
# ---------------------------------------------------------------------------
def make_innovation_precheck_node():
    """innovation_precheck 节点工厂（函数）。

    返回值：
        Callable：节点函数。

    异常：
        无。
    """

    def innovation_precheck(state: InnovationState) -> dict:
        """安全前置节点（函数，🔴 红线）。

        说明：
            复用 run_precheck_core（与 precheck 接口同口径）：高危闸门 / 过敏原
            直接拒绝 / 特殊人群 / taboo 查表，任一命中即置 blocked，后续节点短路。

        参数：
            state：子图状态（ingredients / user_db_id / request_id）。

        返回值：
            dict：{blocked, issues, risk_log_written, resolved_ingredients,
            resolved_ingredient_ids, resolved_ingredient_names, pairings, sub_trace}。

        异常：
            不抛出（run_precheck_core 内部全捕获，异常按拦截处理）。
        """
        start = now_ms()
        pre = run_precheck_core(
            user_db_id=state.get("user_db_id"),
            ingredients=[str(i) for i in (state.get("ingredients") or [])],
            request_id=state.get("request_id"),
        )
        status = "blocked" if pre["blocked"] else "ok"
        span = make_span("innovation_precheck", status, now_ms() - start)
        return {
            "blocked": pre["blocked"],
            "issues": pre["issues"],
            "risk_log_written": pre["risk_log_written"],
            "resolved_ingredients": pre["resolved_ingredients"],
            "resolved_ingredient_ids": pre["resolved_ingredient_ids"],
            "resolved_ingredient_names": pre["resolved_ingredient_names"],
            "pairings": pre["pairings"],
            "sub_trace": [span],
        }

    return innovation_precheck


def make_innovation_property_match_node():
    """innovation_property_match 节点工厂（函数）。

    返回值：
        Callable：节点函数。

    异常：
        无。
    """

    def innovation_property_match(state: InnovationState) -> dict:
        """食材五属性匹配节点（函数）。

        说明：
            查 ingredient_property 表（≥150 条种子）逐食材取五属性；缺属性食材
            标注「性质数据待补充」（missing=true），不阻断流程。

        参数：
            state：子图状态（resolved_ingredients 已就绪）。

        返回值：
            dict：{"properties": [...], "sub_trace": [span]}。

        异常：
            不抛出（查询失败按全量缺失降级）。
        """
        start = now_ms()
        if state.get("blocked"):
            return {"sub_trace": [make_span("innovation_property_match", "skipped", None)]}
        resolved = list(state.get("resolved_ingredients") or [])
        prop_by_id: dict[int, IngredientProperty] = {}
        try:
            ids = [int(r["ingredient_id"]) for r in resolved if r.get("ingredient_id") is not None]
            if ids:
                with SessionLocal() as session:
                    rows = session.execute(
                        select(IngredientProperty).where(IngredientProperty.ingredient_id.in_(ids))
                    ).scalars().all()
                    prop_by_id = {int(p.ingredient_id): p for p in rows}
        except Exception as exc:  # noqa: BLE001 —— 性质查询失败按全量缺失，不阻断
            logger.warning("innovation property query failed: %s", exc)

        properties: list[dict] = []
        for item in resolved:
            ing_id = item.get("ingredient_id")
            row = prop_by_id.get(int(ing_id)) if ing_id is not None else None
            if row is None:
                properties.append({
                    "name": item["name"],
                    "ingredient_id": ing_id,
                    "texture": None,
                    "moisture": None,
                    "flavor": None,
                    "heat_tolerance": None,
                    "oil_absorption": None,
                    "missing": True,
                    "missing_note": "性质数据待补充",
                })
            else:
                properties.append({
                    "name": item["name"],
                    "ingredient_id": int(ing_id),
                    "texture": row.texture,
                    "moisture": row.moisture,
                    "flavor": row.flavor,
                    "heat_tolerance": row.heat_tolerance,
                    "oil_absorption": row.oil_absorption,
                    "missing": False,
                    "missing_note": None,
                })
        span = make_span("innovation_property_match", "ok", now_ms() - start)
        return {"properties": properties, "sub_trace": [span]}

    return innovation_property_match


def make_innovation_pairing_check_node():
    """innovation_pairing_check 节点工厂（函数）。

    返回值：
        Callable：节点函数。

    异常：
        无。
    """

    def innovation_pairing_check(state: InnovationState) -> dict:
        """搭配规则查表节点（函数，🔴 结论必须查表）。

        说明：
            查 flavor_pairing_rule 对食材两两组合：taboo → 直接拒绝（子图独立入口
            的保险闸，precheck 已拦一次）；conflict → 记入依据要求生成避开；
            recommend → 正向依据。技法建议仅在 technique_library 白名单内才透出。

        参数：
            state：子图状态（resolved_ingredient_ids 已就绪）。

        返回值：
            dict：{"pairings": recommend+conflict 合并列表, "techniques_whitelist":
            [...], "sub_trace": [span]}；taboo 命中时返回 blocked + issue。

        异常：
            不抛出（查询失败按空依据降级；查表失败保守拦截 taboo 检查不可用时
            由 precheck 层负责，此处降级为空依据继续生成）。
        """
        start = now_ms()
        if state.get("blocked"):
            return {"sub_trace": [make_span("innovation_pairing_check", "skipped", None)]}
        ids = [int(i) for i in (state.get("resolved_ingredient_ids") or [])]
        pairings: list[dict] = []
        techniques: list[str] = []
        taboo_hits: list[dict] = []
        query_ok = True
        try:
            with SessionLocal() as session:
                if len(ids) >= 2:
                    taboo_hits = _query_pairings(session, ids, relations=("taboo",))
                    pairings = _query_pairings(session, ids, relations=("recommend", "conflict"))
                techniques = _query_whitelist_techniques(session)
        except Exception as exc:  # noqa: BLE001 —— 查表失败降级为空依据（precheck 层已兜底拦截语义）
            logger.warning("innovation pairing query failed: %s", exc)
            query_ok = False

        if taboo_hits:
            detail = "、".join(f"{t['ingredient_a']}与{t['ingredient_b']}" for t in taboo_hits[:3])
            span = make_span("innovation_pairing_check", "blocked", now_ms() - start, rule_hit="INNOVATION_TABOO")
            return {
                "blocked": True,
                "issues": [{"type": "taboo", "message": f"{detail}的组合不适合同烹，已停止创新"}],
                "sub_trace": [span],
            }

        # 🔴 技法白名单过滤：未进白名单的建议技法置 None，不允许进生成 prompt
        whitelist = set(techniques)
        for pairing in pairings:
            if pairing.get("technique") and whitelist and pairing["technique"] not in whitelist:
                pairing["technique"] = None

        status = "ok" if query_ok else "degraded"
        span = make_span("innovation_pairing_check", status, now_ms() - start)
        return {
            "pairings": pairings,
            "techniques_whitelist": techniques,
            "sub_trace": [span],
        }

    return innovation_pairing_check


def make_innovation_generate_node():
    """innovation_generate 节点工厂（函数）。

    返回值：
        Callable：节点函数。

    异常：
        无。
    """

    def innovation_generate(state: InnovationState) -> dict:
        """受约束生成节点（函数）。

        说明：
            LLM 生成（技法白名单 + 用量 100% 量化 + 步骤含时长；每次调用带 25s
            硬超时，见 _chat_with_hard_timeout / LLM_HARD_TIMEOUT_SECONDS）→
            量化校验违例重试一次、再违例本地模板替换；LLM 硬超时/异常同样直接
            降级规则模板 → output 闸门 → 落库 innovation_recipe（status='generated'、
            is_ai_innovated=True、visibility='private'、basis 可追溯，generated_by
            标注生成来源："llm"=LLM 成功 / "template"=规则模板降级）→ 产出 result。

        参数：
            state：子图状态（names/properties/pairings/techniques 已就绪）。

        返回值：
            dict：{"result": 创新菜响应 dict, "generated_by": str, "sub_trace": [span]}；
            output 闸门拦截时返回 {"blocked": True, "issues": [...], "sub_trace": [span]}。

        异常：
            不抛出（LLM 硬超时/失败降级规则模板；落库异常返回 blocked 保守响应）。
        """
        start = now_ms()
        if state.get("blocked"):
            return {"sub_trace": [make_span("innovation_generate", "skipped", None)]}
        names = list(state.get("resolved_ingredient_names") or [])
        properties = list(state.get("properties") or [])
        pairings = list(state.get("pairings") or [])
        techniques = list(state.get("techniques_whitelist") or [])
        user_db_id = state.get("user_db_id")

        span_extra: dict = {}
        draft: dict | None = None
        generated_by = "template"
        try:
            client = get_llm_client()
            system, user = _build_prompts(names, properties, pairings, techniques)
            res = _chat_with_hard_timeout(client, system, user, 0.4)
            draft = _parse_llm_recipe(res.content)
            span_extra = {
                "model_name": res.model,
                "prompt_tokens": res.prompt_tokens,
                "completion_tokens": res.completion_tokens,
                "cost_cents": res.cost_cents,
            }
            if draft is None or not _is_quantified(draft):
                # 量化违例 → 重试一次（prompt 强化量化要求；重试同样受 25s 硬超时约束）
                retry_system = (
                    "上一轮输出未通过量化校验。所有用量必须给出数值与单位（g/ml/个/勺等），"
                    "所有步骤必须给出正整数 duration_sec，严禁「适量/少许/若干」。\n"
                )
                try:
                    res2 = _chat_with_hard_timeout(client, retry_system + system, user, 0.1)
                    draft2 = _parse_llm_recipe(res2.content)
                    span_extra["prompt_tokens"] = int(span_extra.get("prompt_tokens") or 0) + res2.prompt_tokens
                    span_extra["completion_tokens"] = (
                        int(span_extra.get("completion_tokens") or 0) + res2.completion_tokens
                    )
                    span_extra["cost_cents"] = round(
                        float(span_extra.get("cost_cents") or 0.0) + res2.cost_cents, 4
                    )
                    if _is_quantified(draft2):
                        draft = draft2
                    else:
                        draft = None
                except LLMError:
                    draft = None
        except LLMError as exc:
            # LLM 硬超时或不可用（网络级失败）：不重试，直接规则模板降级（P1 DEF-01：前端 60s 内必回响应）
            logger.warning("innovation llm unavailable/hard-timeout, fallback to template: %s", exc)
            draft = None

        if _is_quantified(draft):
            generated_by = "llm"
        else:
            # 🔴 硬超时/再违例/不可用 → 规则模板替换，保证输出 100% 量化（generated_by="template"）
            draft = _local_template_recipe(names, pairings, techniques)
            generated_by = "template"

        # ---- output 闸门（生成内容过 RiskEngine output 扫描，命中替换/拦截）----
        output_text = draft["name"] + " " + " ".join(
            str(step.get("description") or "") for step in draft["steps"]
        )
        verdict = get_risk_engine().scan("output", output_text)
        if verdict.status == "UNKNOWN" or (verdict.hit and verdict.block):
            span = make_span(
                "innovation_generate", "degraded", now_ms() - start, rule_hit=verdict.rule_code, **span_extra
            )
            return {
                "blocked": True,
                "issues": [{
                    "type": "high_risk",
                    "message": "AI 创新生成内容未通过安全校验，本次创新已停止。",
                }],
                "sub_trace": [span],
            }
        if verdict.hit:
            span_extra.setdefault("rule_hit", verdict.rule_code)

        # ---- 落库 innovation_recipe ----
        if not user_db_id:
            # 防御：无归属用户时无法落库（API 层保证存在；理论上不可达）
            span = make_span("innovation_generate", "failed", now_ms() - start, **span_extra)
            return {
                "blocked": True,
                "issues": [{"type": "high_risk", "message": TXT_G06}],
                "sub_trace": [span],
            }
        try:
            with SessionLocal() as session:
                nutrition = _estimate_innovation_nutrition(session, draft["ingredients"])
                basis = {
                    "pairings": pairings,
                    "properties": properties,
                    "techniques_whitelist": techniques,
                    "generated_by": generated_by,
                }
                rule_ids = [
                    int(p["rule_id"]) for p in pairings
                    if p.get("rule_id") is not None and p.get("relation") in ("recommend", "conflict")
                ]
                row = InnovationRecipe(
                    user_id=int(user_db_id),
                    name=str(draft["name"])[:128],
                    ingredients=draft["ingredients"],
                    steps=draft["steps"],
                    nutrition=nutrition,
                    basis=basis,
                    status="generated",
                    is_ai_innovated=True,
                    visibility="private",
                    source_pairing_rule_ids=rule_ids,
                )
                session.add(row)
                session.commit()
                recipe_id = int(row.id)
                created_at = row.created_at.isoformat() if row.created_at else None
        except Exception as exc:  # noqa: BLE001 —— 落库失败按保守拦截（不返回无主数据）
            logger.error("innovation recipe persist failed: %s", exc)
            span = make_span("innovation_generate", "failed", now_ms() - start, **span_extra)
            return {
                "blocked": True,
                "issues": [{"type": "high_risk", "message": TXT_G06}],
                "sub_trace": [span],
            }

        result = {
            "id": recipe_id,
            "name": draft["name"],
            "ingredients": draft["ingredients"],
            "steps": draft["steps"],
            "basis": {
                "pairings": pairings,
                "properties": properties,
                "techniques_whitelist": techniques,
                "generated_by": generated_by,
            },
            "nutrition": nutrition,
            "status": "generated",
            "is_ai_innovated": True,
            "visibility": "private",
            "disclaimer": DISCLAIMER_TEXT,
            "rating": None,
            "created_at": created_at,
        }
        status = "ok" if generated_by == "llm" else "degraded"
        span = make_span("innovation_generate", status, now_ms() - start, **span_extra)
        return {"result": result, "generated_by": generated_by, "sub_trace": [span]}

    return innovation_generate


# ---------------------------------------------------------------------------
# 子图装配与运行入口
# ---------------------------------------------------------------------------
def build_innovation_subgraph():
    """装配并编译创新子图（函数）。

    说明：
        拓扑：START → innovation_precheck → innovation_property_match →
        innovation_pairing_check → innovation_generate → END（线性链；generate
        后即 END，采纳走 API 状态机，不做 interrupt）。

    参数：
        无。

    返回值：
        CompiledStateGraph：编译后的创新子图。

    异常：
        LangGraph 装配异常向上抛出（首次调用即暴露）。
    """
    builder = StateGraph(InnovationState)
    builder.add_node("innovation_precheck", make_innovation_precheck_node())
    builder.add_node("innovation_property_match", make_innovation_property_match_node())
    builder.add_node("innovation_pairing_check", make_innovation_pairing_check_node())
    builder.add_node("innovation_generate", make_innovation_generate_node())
    builder.add_edge(START, "innovation_precheck")
    builder.add_edge("innovation_precheck", "innovation_property_match")
    builder.add_edge("innovation_property_match", "innovation_pairing_check")
    builder.add_edge("innovation_pairing_check", "innovation_generate")
    builder.add_edge("innovation_generate", END)
    return builder.compile()


# 编译后子图进程级缓存（LangGraph 编译结果线程安全，可复用）
_compiled_innovation = None


def get_compiled_innovation_subgraph():
    """获取编译后的创新子图单例（函数）。

    返回值：
        CompiledStateGraph：编译后的创新子图。

    异常：
        装配异常向上抛出（首次调用即暴露）。
    """
    global _compiled_innovation
    if _compiled_innovation is None:
        _compiled_innovation = build_innovation_subgraph()
    return _compiled_innovation


def run_innovation_precheck(user_db_id: int | None, ingredients: list[str], request_id: str | None = None) -> dict:
    """创新预检入口（函数，供 precheck 接口调用）。

    说明：
        直接执行 run_precheck_core（无 LLM、无生成），返回拦截语义结构；
        precheck 与 generate 复用同一核心函数，保证拦截口径一致。

    参数：
        user_db_id：用户数据库 ID（None 时不做档案类检查）。
        ingredients：食材名列表。
        request_id：请求唯一标识（缺省自动生成）。

    返回值：
        dict：run_precheck_core 返回结构（{ok, blocked, issues, risk_log_written,
        resolved_*, pairings}）。

    异常：
        不抛出（核心函数内部全捕获）。
    """
    return run_precheck_core(user_db_id, [str(i) for i in ingredients], request_id)


def run_innovation_generate(
    user_db_id: int,
    ingredients: list[str],
    request_id: str | None = None,
    user_id_hash: str | None = None,
) -> dict:
    """创新生成入口（函数，供 generate 接口调用）。

    说明：
        生成前自动先跑 precheck 逻辑（复用 run_precheck_core 同一函数，拦截即
        短路返回）；通过后 invoke 创新子图（precheck 节点复查 + 性质匹配 +
        搭配查表 + 受约束生成落库），结束时将子图 sub_trace 落库 agent_trace。

    参数：
        user_db_id：用户数据库 ID（🔴 必填，创新菜归属）。
        ingredients：食材名列表。
        request_id：请求唯一标识（缺省自动生成）。
        user_id_hash：用户标识哈希（sha256 前 12 位，trace 落库脱敏）。

    返回值：
        dict：{ok, blocked, issues, risk_log_written, result, request_id, trace_id}
        （result 为创新菜响应 dict，拦截/失败时为 None）。

    异常：
        不抛出（子图执行异常兜底为保守拦截响应）。
    """
    request_id = request_id or f"inn_{uuid.uuid4().hex[:12]}"
    trace_id = f"tr_{uuid.uuid4().hex[:8]}"
    pre = run_precheck_core(user_db_id, [str(i) for i in ingredients], request_id)
    if pre["blocked"]:
        return {
            "ok": False,
            "blocked": True,
            "issues": pre["issues"],
            "risk_log_written": pre["risk_log_written"],
            "result": None,
            "request_id": request_id,
            "trace_id": trace_id,
        }

    state = {
        "request_id": request_id,
        "trace_id": trace_id,
        "user_id_hash": user_id_hash,
        "user_db_id": int(user_db_id),
        "ingredients": [str(i) for i in ingredients],
    }
    try:
        final = get_compiled_innovation_subgraph().invoke(state, config={"recursion_limit": 30})
    except Exception as exc:  # noqa: BLE001 —— 子图异常兜底为保守响应（响应永不 500）
        logger.error("innovation subgraph invoke failed (request_id=%s): %s", request_id, exc)
        return {
            "ok": False,
            "blocked": False,
            "issues": [{"type": "high_risk", "message": TXT_G06}],
            "risk_log_written": False,
            "result": None,
            "request_id": request_id,
            "trace_id": trace_id,
        }

    # 子图全量 span 落库 agent_trace（失败仅告警，不阻断响应）
    persist_trace(
        {"request_id": request_id, "trace_id": trace_id, "user_id_hash": user_id_hash},
        list(final.get("sub_trace") or []),
    )

    result = final.get("result")
    if final.get("blocked") or not result:
        return {
            "ok": False,
            "blocked": bool(final.get("blocked")),
            "issues": list(final.get("issues") or [{"type": "high_risk", "message": TXT_G06}]),
            "risk_log_written": bool(final.get("risk_log_written")),
            "result": None,
            "request_id": request_id,
            "trace_id": trace_id,
        }
    return {
        "ok": True,
        "blocked": False,
        "issues": [],
        "risk_log_written": bool(final.get("risk_log_written")),
        "result": result,
        "request_id": request_id,
        "trace_id": trace_id,
    }
