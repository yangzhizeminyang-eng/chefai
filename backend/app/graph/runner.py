"""编排入口（Runner）模块。

职责：
    run_recommend / run_ask：构建初态 → invoke 编译后的主图 → 返回响应 dict。
    - 自管 DB Session（节点内各自短会话，runner 不持长事务）；
    - SafetyProfile 构建（R-2）：payload 显式非空字段 > 用户档案（R-2 优先级，见
      _merge_profile_field）；档案经 load_profile_from_db 从 family/family_member
      合并读取（全成员并集，最严格口径），设备清单另取 user_skill_profile.equipment
      （一人一份，供 hard_filter 设备维度差集判定）；payload 未传 user_id 或无档案时行为
      与既有链路完全一致（向后兼容）；
    - 正常响应结构对齐架构文档 §9.2 正常示例（request_id/safe_mode/results/filtered_by/
      disclaimer_id/trace_id）；
    - 一票否决短路响应结构对齐 §9.2 否决示例：仅 request_id/blocked/overrides_all/
      risk{...}/disclaimer_id/trace_id，🔴 绝不含 results/candidates/nutrition；
    - trace 落库在 finalize / emit_safety_response / safe_mode_handler 内完成
      （短路时业务节点 trace 行由 emit_safety_response 生成 not_executed 标注）。
"""

from __future__ import annotations

import hashlib
import uuid

from sqlalchemy import select

from app.core.db import SessionLocal
from app.core.logging import get_logger, new_request_id
from app.graph.main_graph import build_main_graph
from app.graph.nodes.common import DISCLAIMER_ID, TXT_G06
from app.models import Family, FamilyMember, UserSkillProfile
from app.safety import SafetyProfile

logger = get_logger(__name__)

# 编译后的主图进程级缓存（LangGraph 编译结果线程安全，可复用）
_compiled_graph = None


def get_compiled_main_graph():
    """获取编译后的主图单例（函数）。

    返回值：
        CompiledStateGraph：编译后的主图。

    异常：
        装配异常向上抛出（首次调用即暴露图结构问题）。
    """
    global _compiled_graph
    if _compiled_graph is None:
        _compiled_graph = build_main_graph()
    return _compiled_graph


def load_profile_from_db(session, user_id: int) -> dict:
    """从数据库加载用户家庭档案并合并为安全档案字段（函数）。

    说明：
        R-2 核心：查用户默认家庭（第一个未删除家庭）下全部未删除成员，
        按「最严格口径取并集」合并 allergen_codes / dietary_restrictions /
        special_population 三段（多成员任一过敏原即整户规避）；
        设备清单 equipment 取自 user_skill_profile（一人一份，本人灶具口径，
        不随家庭成员并集）。任何数据库异常降级为空档案（不阻断编排主链路）。

    参数：
        session：数据库会话（由调用方提供并管理生命周期）。
        user_id：用户数据库 ID。

    返回值：
        dict：{"allergen_codes": [...], "dietary_restrictions": [...],
        "special_population": [...], "equipment": [...]}（去重合并后的字符串列表；
        无家庭/无设备档案/异常时为空列表）。

    异常：
        不抛出（内部全捕获降级为空档案）。
    """
    merged: dict[str, list[str]] = {
        "allergen_codes": [],
        "dietary_restrictions": [],
        "special_population": [],
        "equipment": [],
    }
    try:
        family = session.execute(
            select(Family)
            .where(Family.user_id == int(user_id))
            .where(Family.deleted_at.is_(None))
            .order_by(Family.id)
            .limit(1)
        ).scalar_one_or_none()
        if family is None:
            # 无家庭档案仍尝试读取本人设备清单（user_skill_profile 独立于家庭存在）
            _load_equipment_into(session, user_id, merged)
            return merged
        members = session.execute(
            select(FamilyMember)
            .where(FamilyMember.family_id == int(family.id))
            .where(FamilyMember.deleted_at.is_(None))
            .order_by(FamilyMember.id)
        ).scalars().all()
        for member in members:
            for key, values in (
                ("allergen_codes", member.allergen_codes),
                ("dietary_restrictions", member.dietary_restrictions),
                ("special_population", member.special_population),
            ):
                for value in (values or []):
                    text_value = str(value).strip()
                    if text_value and text_value not in merged[key]:
                        merged[key].append(text_value)
        _load_equipment_into(session, user_id, merged)
        return merged
    except Exception as exc:  # noqa: BLE001 —— 档案读取失败降级为空档案，不阻断编排
        logger.warning("load profile from db failed (user_id=%s): %s", user_id, exc)
        return merged


def _load_equipment_into(session, user_id: int, merged: dict) -> None:
    """把 user_skill_profile.equipment 写入档案合并字典（函数）。

    说明：
        设备清单一人一份（user_skill_profile.user_id 唯一），与家庭档案解耦；
        查询异常仅告警（设备维度缺失按「未设置」处理，不阻断主链路）。

    参数：
        session：数据库会话。
        user_id：用户数据库 ID。
        merged：load_profile_from_db 的合并字典（原地追加 "equipment" 键）。

    返回值：
        None。

    异常：
        不抛出（查询异常告警后返回，equipment 保持空列表）。
    """
    try:
        row = session.execute(
            select(UserSkillProfile).where(UserSkillProfile.user_id == int(user_id))
        ).scalar_one_or_none()
        if row is not None:
            for value in (row.equipment or []):
                text_value = str(value).strip()
                if text_value and text_value not in merged["equipment"]:
                    merged["equipment"].append(text_value)
    except Exception as exc:  # noqa: BLE001 —— 设备读取失败按未设置处理
        logger.warning("load user equipment failed (user_id=%s): %s", user_id, exc)


def _normalize_ingredients(raw) -> list:
    """归一化食材输入（函数）。

    说明：
        兼容三种形态：["土豆", ...] / [{"ingredient_id": 1}, ...] / [{"name": "土豆"}, ...]；
        其他类型元素转为字符串忽略处理。

    参数：
        raw：payload 中的 ingredients 字段。

    返回值：
        list：归一化后的食材列表。

    异常：
        无。
    """
    if not raw:
        return []
    normalized: list = []
    for item in raw:
        if isinstance(item, dict):
            if item.get("ingredient_id") or item.get("name"):
                normalized.append(item)
        elif isinstance(item, str) and item.strip():
            normalized.append(item.strip())
    return normalized


def _merge_profile_field(payload_values, profile_values) -> list[str]:
    """合并安全档案单字段：payload 显式非空值 > 数据库档案值（函数）。

    说明：
        R-2 优先级口径：payload 显式提供【非空】值时覆盖档案（payload 覆盖档案）；
        payload 为空/缺失时回退档案值——路由层既有调用会传空数组占位
        （如 /v1/recommend 的 allergen_codes=[]），若按「键存在即覆盖」会让档案
        永远失效，故以非空为覆盖前提；两段均为空时返回空列表（向后兼容：
        无档案用户行为与改造前完全一致）。

    参数：
        payload_values：payload 中该字段的原始值（可 None/空列表）。
        profile_values：数据库档案中该字段的合并值（可 None/空列表）。

    返回值：
        list[str]：去空白后的字符串列表。

    异常：
        无。
    """
    payload_list = [str(v).strip() for v in (payload_values or []) if str(v).strip()]
    if payload_list:
        return payload_list
    return [str(v).strip() for v in (profile_values or []) if str(v).strip()]


def _init_state(payload: dict, input_text: str, ingredients: list) -> dict:
    """构建编排初态（函数）。

    说明：
        request_id 缺省自动生成（幂等键由调用方传入时可透传）；
        user_id_hash = sha256(user_key).hexdigest()[:12]（脱敏，不入原文）；
        R-2：payload 携带 user_id 时经 load_profile_from_db 读取家庭档案，
        按 _merge_profile_field 优先级（payload 非空 > 档案）构建 SafetyProfile。

    参数：
        payload：接口 payload（可含 request_id/user_id/allergen_codes 等）。
        input_text：输入文本。
        ingredients：归一化后的食材列表。

    返回值：
        dict：编排初态。

    异常：
        无（档案加载失败降级为空档案）。
    """
    request_id = str(payload.get("request_id") or new_request_id())
    user_key = str(payload.get("user_id") or payload.get("anonymous_id") or "anonymous")
    user_id_hash = hashlib.sha256(user_key.encode("utf-8")).hexdigest()[:12]

    # R-2：payload 携带 user_id 时加载家庭档案（短会话，随取随关）
    db_profile: dict = {}
    if payload.get("user_id"):
        try:
            with SessionLocal() as session:
                db_profile = load_profile_from_db(session, int(payload["user_id"]))
        except Exception as exc:  # noqa: BLE001 —— 档案加载失败按空档案继续（向后兼容）
            logger.warning("load user profile failed (user_id=%s): %s", payload.get("user_id"), exc)
            db_profile = {}

    profile = SafetyProfile(
        user_allergen_codes=_merge_profile_field(
            payload.get("allergen_codes"), db_profile.get("allergen_codes")
        ),
        dietary_restrictions=_merge_profile_field(
            payload.get("dietary_restrictions"), db_profile.get("dietary_restrictions")
        ),
        special_population=_merge_profile_field(
            payload.get("special_population"), db_profile.get("special_population")
        ),
        difficulty_cap=payload.get("difficulty_cap"),
        # 设备清单：payload 非空 > user_skill_profile.equipment（空档案=未设置，
        # hard_filter 设备维度不生效）
        equipment=_merge_profile_field(
            payload.get("equipment"), db_profile.get("equipment")
        ),
    )
    trace_id = f"tr_{uuid.uuid4().hex[:8]}"
    state: dict = {
        "request_id": request_id,
        "trace_id": trace_id,
        "user_id_hash": user_id_hash,
        "input_text": input_text or "",
        "ingredients": ingredients,
        "safety_profile": profile.model_dump(),
        "safe_mode": False,
        "trace": [],
    }
    # 数字 user_id 注入：M.4/M.5 专用节点与创新入口的查库路径依赖该字段
    # （payload 携带 user_id 时才存在；缺失时各节点按降级话术处理）
    if payload.get("user_id"):
        try:
            state["user_id"] = int(payload["user_id"])
        except (TypeError, ValueError):
            pass
    return state


def _invoke(payload: dict, input_text: str, ingredients: list) -> dict:
    """执行主图并返回响应（函数）。

    说明：
        图执行任何未捕获异常时兜底返回保守模式响应（响应永不 500 到编排层之外）。

    参数：
        payload：接口 payload。
        input_text：输入文本。
        ingredients：归一化食材列表。

    返回值：
        dict：响应体（正常/否决/保守模式三态之一）。

    异常：
        不抛出（内部全捕获兜底）。
    """
    state = _init_state(payload, input_text, ingredients)
    try:
        app = get_compiled_main_graph()
        final = app.invoke(state, config={"recursion_limit": 60})
        response = final.get("response")
        if response:
            return response
    except Exception as exc:  # noqa: BLE001 —— 编排层兜底：绝不向 API 层抛异常
        logger.error("graph invoke failed (request_id=%s): %s", state["request_id"], exc)
    return {
        "request_id": state["request_id"],
        "safe_mode": True,
        "message": TXT_G06,
        "detail": "本次请求未生成任何业务内容，已按最保守策略处理，请稍后重试。",
        "disclaimer_id": DISCLAIMER_ID,
        "trace_id": state["trace_id"],
    }


def run_recommend(payload: dict) -> dict:
    """推荐主入口（函数）。

    说明：
        食材可按名称或 ingredient_id 传入；文本可缺省（纯食材推荐）。

    参数：
        payload：{"request_id"?, "ingredients": [...], "text"?, "allergen_codes"?..., }。

    返回值：
        dict：响应体（正常三档结果 / 一票否决 / 保守模式）。

    异常：
        不抛出（编排层全捕获兜底）。
    """
    ingredients = _normalize_ingredients(payload.get("ingredients"))
    return _invoke(payload, str(payload.get("text") or ""), ingredients)


def run_ask(payload: dict) -> dict:
    """自然语言入口（函数）。

    说明：
        输入闸门 → 意图路由 → 受限问答 / 推荐子图（搜索路径）；
        命中阻断规则时返回一票否决响应（业务节点 not_executed）。

    参数：
        payload：{"request_id"?, "text": "...", "allergen_codes"?...}。

    返回值：
        dict：响应体（问答 / 推荐结果 / 一票否决 / 保守模式）。

    异常：
        不抛出（编排层全捕获兜底）。
    """
    return _invoke(payload, str(payload.get("text") or ""), _normalize_ingredients(payload.get("ingredients")))
