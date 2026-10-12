"""会员状态与识别额度服务模块（模块 J 支撑层）。

职责：
    提供会员判定、AI 识别额度计算与扣减/回补的服务函数，供
    app/api/v1/member.py（GET /v1/member/me）与 Task 5 的 vision 识别模块
    （识别成功后 consume_quota）统一调用：
    - get_member_status(session, user_id)：按 paid 订单判定会员身份与到期时间；
    - get_quota(session, user_id)：读当日识别额度（会员 10 / 免费 3）；
    - consume_quota(session, user_id, n)：扣减额度并落库（内部 commit）；
    - refund_quota(session, user_id, n)：识别失败回补额度（内部 commit）。

额度存储约定（🔴 无专用表，阶段一不改模型的降级方案）：
    复用 user.preferences JSONB 列，键 "vision_quota"：
        {"vision_quota": {"date": "2026-10-09", "used": 3}}
    - date 为额度所属业务日（Asia/Shanghai 口径，固定 UTC+8 偏移，中国无夏令时）；
    - 读取时 date 与当日不一致即视为「跨日已重置」（used=0），惰性重置不回写；
    - 仅 consume/refund 写库（重新赋值顶层 dict 触发 JSONB 变更检测）。

会员判定约定：
    本人 order 表中存在 status='paid' 的订单即计为购买记录，到期时间
    expire_at = paid_at + 时长（monthly +30 天 / quarterly +90 天 / yearly +365 天），
    取全部 paid 订单中的最大 expire_at；expire_at 晚于当前时间即 is_member=True。
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.logging import get_logger
from app.models import Order, User

logger = get_logger(__name__)

# 免费档每日 AI 识别额度（PRD 会员权益对照：免费 3 次/日）
FREE_QUOTA_LIMIT = 3

# 会员档每日 AI 识别额度（会员 10 次/日）
MEMBER_QUOTA_LIMIT = 10

# 会员时长映射（order.product_type → 权益天数；模拟口径，正式定价阶段配置化）
MEMBER_DURATION_DAYS: dict[str, int] = {
    "monthly": 30,
    "quarterly": 90,
    "yearly": 365,
}

# user.preferences JSONB 中识别额度的存储键
QUOTA_PREF_KEY = "vision_quota"

# 东八区固定偏移（中国无夏令时，固定偏移即业务日口径；避免 Windows 缺 tzdata 依赖）
_CN_TZ = timezone(timedelta(hours=8))


def business_today() -> date:
    """取业务日（函数）。

    说明：
        识别额度「当日」以中国本地日历日为准（Asia/Shanghai 固定 UTC+8）。

    参数：
        无。

    返回值：
        date：当前业务日（东八区日历日）。

    异常：
        无。
    """
    return datetime.now(_CN_TZ).date()


def _load_quota_state(user: User) -> dict:
    """读取用户的额度原始状态并做跨日重置（函数）。

    说明：
        preferences 缺失/键缺失/日期非当日 → used 归零（惰性重置，仅读不写）。

    参数：
        user：用户 ORM 实例。

    返回值：
        dict：{"date": "YYYY-MM-DD", "used": int}（已按当日口径归一）。

    异常：
        无（非法 JSON 结构一律按空额度处理）。
    """
    prefs = user.preferences if isinstance(user.preferences, dict) else {}
    state = prefs.get(QUOTA_PREF_KEY)
    if not isinstance(state, dict):
        state = {}
    today = business_today().isoformat()
    used = state.get("used")
    try:
        used_int = int(used)
    except (TypeError, ValueError):
        used_int = 0
    # 跨日（或日期缺失）→ 当日额度重置为 0
    if str(state.get("date")) != today:
        used_int = 0
    return {"date": today, "used": max(0, used_int)}


def get_member_status(session: Session, user_id: int) -> dict:
    """按 paid 订单判定会员身份与到期时间（函数）。

    说明：
        会员判定 = 本人存在 status='paid' 订单；到期时间 = max(paid_at + 时长)；
        expire_at 晚于当前时间即有效会员。仅查询，不写库、不 commit。

    参数：
        session：数据库会话（请求级或独立短会话）。
        user_id：用户 ID。

    返回值：
        dict：{"is_member": bool, "expire_at": str | None}
        （expire_at 为 ISO 8601 字符串；无 paid 订单时为 None）。

    异常：
        SQLAlchemyError：数据库异常向上抛出（调用方兜底）。
    """
    rows = session.execute(
        select(Order.product_type, Order.paid_at).where(
            Order.user_id == user_id, Order.status == "paid"
        )
    ).all()
    expire_at: datetime | None = None
    for product_type, paid_at in rows:
        days = MEMBER_DURATION_DAYS.get(str(product_type), 0)
        if paid_at is None or days <= 0:
            continue
        candidate = paid_at + timedelta(days=days)
        if expire_at is None or candidate > expire_at:
            expire_at = candidate
    is_member = expire_at is not None and expire_at > datetime.now(expire_at.tzinfo)
    return {
        "is_member": bool(is_member),
        "expire_at": expire_at.isoformat() if expire_at is not None else None,
    }


def get_quota(session: Session, user_id: int) -> dict:
    """读取用户当日 AI 识别额度（函数）。

    说明：
        limit 按会员身份取 MEMBER_QUOTA_LIMIT(10) / FREE_QUOTA_LIMIT(3)；
        used 为当日已用次数（跨日自动归零，惰性重置不回写）。仅查询，不写库。

    参数：
        session：数据库会话。
        user_id：用户 ID。

    返回值：
        dict：{"used": int, "limit": int, "remaining": int}。

    异常：
        SQLAlchemyError：数据库异常向上抛出（调用方兜底）。
    """
    user = session.get(User, user_id)
    state = _load_quota_state(user) if user is not None else {"date": "", "used": 0}
    limit = MEMBER_QUOTA_LIMIT if get_member_status(session, user_id)["is_member"] else FREE_QUOTA_LIMIT
    used = min(state["used"], limit)
    return {"used": used, "limit": limit, "remaining": max(0, limit - used)}


def consume_quota(session: Session, user_id: int, n: int = 1) -> dict:
    """扣减用户当日 AI 识别额度并落库（函数）。

    说明：
        供 Task 5 vision 识别成功后调用；内部直接 commit（自包含服务函数，
        调用方无需再 commit）。额度不足（used + n > limit）抛 ValueError，
        调用方应先用 get_quota 判定 remaining。

    参数：
        session：数据库会话（函数内部 commit）。
        user_id：用户 ID。
        n：扣减次数（默认 1）。

    返回值：
        dict：扣减后的 {"used": int, "limit": int, "remaining": int}。

    异常：
        ValueError：n <= 0 或当日剩余额度不足。
        SQLAlchemyError：数据库异常向上抛出。
    """
    if n <= 0:
        raise ValueError("扣减次数必须为正整数")
    user = session.get(User, user_id)
    if user is None:
        raise ValueError(f"用户不存在: user_id={user_id}")
    is_member = get_member_status(session, user_id)["is_member"]
    limit = MEMBER_QUOTA_LIMIT if is_member else FREE_QUOTA_LIMIT
    state = _load_quota_state(user)
    used = state["used"]
    if used + n > limit:
        raise ValueError(f"当日识别额度不足: used={used}, limit={limit}, need={n}")
    # 重新赋值顶层 preferences dict，触发 JSONB 变更检测（SQLAlchemy 不追踪原地变更）
    prefs = dict(user.preferences or {})
    prefs[QUOTA_PREF_KEY] = {"date": state["date"], "used": used + n}
    user.preferences = prefs
    session.commit()
    return {"used": used + n, "limit": limit, "remaining": max(0, limit - used - n)}


def refund_quota(session: Session, user_id: int, n: int = 1) -> dict:
    """回补用户当日 AI 识别额度并落库（函数）。

    说明：
        识别失败/服务异常时回退已扣减的次数（下限 0，不产生负数）；
        内部直接 commit。

    参数：
        session：数据库会话（函数内部 commit）。
        user_id：用户 ID。
        n：回补次数（默认 1）。

    返回值：
        dict：回补后的 {"used": int, "limit": int, "remaining": int}。

    异常：
        ValueError：n <= 0 或用户不存在。
        SQLAlchemyError：数据库异常向上抛出。
    """
    if n <= 0:
        raise ValueError("回补次数必须为正整数")
    user = session.get(User, user_id)
    if user is None:
        raise ValueError(f"用户不存在: user_id={user_id}")
    state = _load_quota_state(user)
    is_member = get_member_status(session, user_id)["is_member"]
    limit = MEMBER_QUOTA_LIMIT if is_member else FREE_QUOTA_LIMIT
    used = max(0, state["used"] - n)
    prefs = dict(user.preferences or {})
    prefs[QUOTA_PREF_KEY] = {"date": state["date"], "used": used}
    user.preferences = prefs
    session.commit()
    return {"used": used, "limit": limit, "remaining": max(0, limit - used)}
