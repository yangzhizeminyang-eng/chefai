"""API 路由共享依赖模块。

职责：
    提供各路由模块共用的工具函数：
    - api_error：构造统一错误 JSON（{code, message, detail}）的 HTTPException；
    - get_or_create_user：按 anonymous_id 检索/创建匿名用户（upsert 语义）；
    - resolve_anonymous_id：请求体 → X-Anonymous-Id 头 → 新建 的兜底解析链；
    - resolve_user：JWT 优先、匿名头兜底 的当前用户解析（登录态统一入口）；
    - get_current_user：FastAPI 依赖（档案端点用，JWT 优先，自动 upsert 匿名用户）；
    - resolve_existing_user_id：只读解析已存在用户 ID（ask/recommend 传参 runner 用）；
    - difficulty_label：DB 1~5 难度 → 前端三档文案映射。
"""

from __future__ import annotations

from fastapi import Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.idempotency import make_request_id
from app.core.logging import get_logger, request_id_var
from app.core.user_security import user_id_from_request
from app.models import User

logger = get_logger(__name__)

# 匿名 ID 前缀（后端自动生成时的固定标识）
ANON_PREFIX = "anon_"

# 统一错误码常量
ERR_NOT_FOUND = "NOT_FOUND"
ERR_CONFLICT = "STATE_CONFLICT"
ERR_BAD_REQUEST = "BAD_REQUEST"
ERR_VALIDATION = "VALIDATION_ERROR"


def api_error(status_code: int, code: str, message: str, detail=None) -> HTTPException:
    """构造统一错误 HTTPException（函数）。

    说明：
        detail 携带 {code, message, detail} 结构，由 main.py 的 HTTPException
        处理器展开为顶层统一错误 JSON（前端 normalizeError 直接消费 message）。

    参数：
        status_code：HTTP 状态码。
        code：业务错误码（如 NOT_FOUND / STATE_CONFLICT）。
        message：面向用户的错误文案。
        detail：补充调试信息（可 None）。

    返回值：
        HTTPException：可直接 raise 的异常实例。

    异常：
        无。
    """
    return HTTPException(
        status_code=status_code,
        detail={"code": code, "message": message, "detail": detail},
    )


def resolve_request_id(payload_request_id: str | None, request: Request) -> str:
    """解析幂等键并回写日志上下文（函数）。

    说明：
        解析顺序：请求体 request_id → 中间件已生成的 request_id（ContextVar，排除
        占位符 "-"）→ X-Request-Id 请求头 → 自动生成。保证路由内幂等键与
        request_id 中间件的响应头一致（trace 查询按同一键取证）。

    参数：
        payload_request_id：请求体显式传入的 request_id（可 None）。
        request：FastAPI 请求对象。

    返回值：
        str：本次请求的幂等键。

    异常：
        无。
    """
    rid = payload_request_id or None
    if not rid:
        current = request_id_var.get()
        if current and current != "-":
            rid = current
    if not rid:
        rid = request.headers.get("X-Request-Id") or None
    if not rid:
        rid = make_request_id()
    request_id_var.set(rid)
    return rid


def resolve_anonymous_id(payload_anonymous_id: str | None, request: Request) -> str | None:
    """解析匿名会话 ID（函数）。

    说明：
        解析顺序：请求体 anonymous_id → X-Anonymous-Id 请求头 → None
        （None 时由调用方决定是否新建匿名用户）。

    参数：
        payload_anonymous_id：请求体中的 anonymous_id（可 None）。
        request：FastAPI 请求对象（读请求头）。

    返回值：
        str | None：匿名会话 ID 或 None。

    异常：
        无。
    """
    if payload_anonymous_id:
        return payload_anonymous_id.strip() or None
    header_value = request.headers.get("X-Anonymous-Id")
    if header_value:
        return header_value.strip() or None
    return None


def get_or_create_user(session: Session, anonymous_id: str | None) -> User:
    """按 anonymous_id 检索或创建匿名用户（函数）。

    说明：
        upsert 语义：anonymous_id 已存在则复用（不更新既有行）；缺失时生成
        anon_ 前缀新 ID 并建行（提交由调用方负责）。

    参数：
        session：数据库会话。
        anonymous_id：匿名会话 ID（可 None）。

    返回值：
        User：用户 ORM 实例（新建实例由调用方 commit）。

    异常：
        SQLAlchemyError：数据库异常向上抛出（由全局异常处理器兜底）。
    """
    if anonymous_id:
        user = session.execute(
            select(User).where(User.anonymous_id == anonymous_id)
        ).scalar_one_or_none()
        if user is not None:
            return user
    else:
        # 缺省生成 anon_ 前缀唯一 ID（uuid 短串足够演示环境防碰撞）
        import uuid

        anonymous_id = f"{ANON_PREFIX}{uuid.uuid4().hex[:12]}"
    user = User(anonymous_id=anonymous_id)
    session.add(user)
    session.flush()
    return user


def resolve_user(
    session: Session, payload_anonymous_id: str | None, request: Request
) -> User:
    """解析当前请求用户：JWT 优先、匿名兜底（函数）。

    说明：
        登录态统一入口：Authorization Bearer 用户 token 合法时直接加载对应
        user（不新建行，token 中 user_id 不存在则回退匿名链）；否则沿用匿名
        解析链（请求体 anonymous_id → X-Anonymous-Id 头 → 自动建 anon_ 用户，
        upsert 语义）。前端登录后匿名头仍会携带，但 JWT 优先保证账号隔离。

    参数：
        session：数据库会话。
        payload_anonymous_id：请求体中的 anonymous_id（可 None）。
        request：FastAPI 请求对象。

    返回值：
        User：当前用户 ORM 实例（新建实例由调用方 commit）。

    异常：
        SQLAlchemyError：数据库异常向上抛出（由全局异常处理器兜底）。
    """
    jwt_user_id = user_id_from_request(request)
    if jwt_user_id is not None:
        user = session.get(User, jwt_user_id)
        if user is not None:
            return user
        logger.warning("jwt user_id=%s not found, fallback to anonymous", jwt_user_id)
    anon_id = resolve_anonymous_id(payload_anonymous_id, request)
    return get_or_create_user(session, anon_id)


def get_current_user(request: Request, session: Session = Depends(get_db)) -> User:
    """解析当前请求用户并保证落库（函数，FastAPI 依赖）。

    说明：
        JWT 优先（resolve_user），回退匿名身份解析：X-Anonymous-Id 请求头 →
        自动生成 anon_ 前缀新用户（跟随 consent/auth 端点的 upsert 惯例：未带头
        不拒绝，自动建档）；新建或既有的用户行在此提交，后续端点可直接基于
        user.id 关联写库。

    参数：
        request：FastAPI 请求对象（读 Authorization / X-Anonymous-Id 头）。
        session：请求级数据库会话（依赖缓存与端点共用同一实例）。

    返回值：
        User：当前用户 ORM 实例（已 commit，属性可用）。

    异常：
        SQLAlchemyError：数据库异常向上抛出（由全局异常处理器兜底）。
    """
    user = resolve_user(session, None, request)
    session.commit()
    return user


def resolve_existing_user_id(
    session: Session, payload_anonymous_id: str | None, request: Request
) -> int | None:
    """只读解析已存在用户的数据库 ID（函数）。

    说明：
        与 get_or_create_user 的 upsert 不同，本函数不建行、不提交——仅用于
        ask/recommend 把既有用户身份传参给编排层（runner 据此加载档案）：
        解析顺序：JWT 用户 token → 请求体 anonymous_id → X-Anonymous-Id 头 → None；
        用户不存在时返回 None（编排层按空档案处理，行为与无档案用户一致）。

    参数：
        session：数据库会话。
        payload_anonymous_id：请求体中的 anonymous_id（可 None）。
        request：FastAPI 请求对象（读 Authorization / X-Anonymous-Id 头）。

    返回值：
        int | None：用户数据库 ID；请求未携带身份或用户不存在时返回 None。

    异常：
        不抛出（查询异常返回 None，不阻断主链路）。
    """
    try:
        jwt_user_id = user_id_from_request(request)
        if jwt_user_id is not None:
            exists = session.execute(
                select(User.id).where(User.id == jwt_user_id).limit(1)
            ).scalar_one_or_none()
            if exists is not None:
                return int(exists)
        anon_id = resolve_anonymous_id(payload_anonymous_id, request)
        if not anon_id:
            return None
        return session.execute(
            select(User.id).where(User.anonymous_id == anon_id)
        ).scalar_one_or_none()
    except Exception as exc:  # noqa: BLE001 —— 身份解析失败按匿名处理，不影响响应
        logger.warning("resolve existing user id failed: %s", exc)
        return None


def difficulty_label(difficulty: int | None) -> str:
    """DB 难度值 → 前端三档文案映射（函数）。

    说明：
        1-2 → easy、3 → medium、4-5 → hard；非法值兜底 medium。

    参数：
        difficulty：DB 难度值（1~5）。

    返回值：
        str：三档文案（easy / medium / hard）。

    异常：
        无。
    """
    try:
        value = int(difficulty or 0)
    except (TypeError, ValueError):
        return "medium"
    if value <= 2:
        return "easy"
    if value == 3:
        return "medium"
    return "hard"


def format_amount(value: float | None, amount_min: float | None, amount_max: float | None, unit: str | None) -> str:
    """生成量化用量描述串（函数）。

    说明：
        固定值 → 「200g」；区间 → 「100~150g」；无单位只出数值（chk_amount_quantified
        保证二者至少其一非空）。

    参数：
        value：固定用量值。
        amount_min：区间下限。
        amount_max：区间上限。
        unit：用量单位。

    返回值：
        str：用量描述串（如「200g」「100~150g」「2勺」）。

    异常：
        无。
    """
    suffix = unit or ""
    try:
        if value is not None:
            return _trim_num(float(value)) + suffix
        if amount_min is not None and amount_max is not None:
            return f"{_trim_num(float(amount_min))}~{_trim_num(float(amount_max))}{suffix}"
    except (TypeError, ValueError):
        pass
    return suffix or "见步骤"


def _trim_num(num: float) -> str:
    """数值转展示串（函数）。

    说明：
        整数去小数尾（200.0 → 200），保留最多两位小数。

    参数：
        num：数值。

    返回值：
        str：展示串。

    异常：
        无。
    """
    if float(num).is_integer():
        return str(int(num))
    return f"{num:.2f}".rstrip("0").rstrip(".")


def adapt_risk(risk: dict | None) -> dict:
    """编排层 risk 字典 → 前端契约风险详情（函数）。

    说明：
        rule_id 与 rule_code 同值并存（W-05 消费 rule_code、W-06 消费 rule_id）；
        缺失字段以 None 补齐（前端类型要求键恒存在或以 ?. 访问）。

    参数：
        risk：编排否决响应中的 risk 字典（可 None）。

    返回值：
        dict：补齐后的风险详情字典。

    异常：
        无。
    """
    risk = risk or {}
    rule_code = risk.get("rule_code")
    return {
        "hit": bool(risk.get("hit", False)),
        "category": risk.get("category"),
        "rule_code": rule_code,
        "rule_id": rule_code,
        "risk_level": risk.get("risk_level"),
        "message_id": risk.get("message_id"),
        "title": risk.get("title"),
        "body": risk.get("body"),
        "correct_action": risk.get("correct_action"),
        "after_consumption_advice": risk.get("after_consumption_advice"),
        "evidence_ref": list(risk.get("evidence_ref") or []),
    }
