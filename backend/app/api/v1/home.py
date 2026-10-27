"""首页聚合路由模块（模块 B）。

职责：
    GET /v1/home：首页一次性聚合六入口开关、断点续做会话、临期库存提醒、
    家庭档案提示、当季推荐类别与免责声明。

降级约定（🔴 任务红线）：
    任何子项查询失败（含数据库异常）一律降级为空值（None/[]/默认结构），
    HTTP 恒 200，绝不因局部子项失败阻断整页。

身份约定（沿用现有惯例）：
    X-Anonymous-Id 请求头 → user 行（不存在则创建）；无请求头时返回匿名空态
    （全空值），不创建用户行（避免无头轮询造成行膨胀）。

口径说明：
    - 未完成会话：任务口径 status='in_progress'，cooking_session 表 CHECK 枚举
      无该值，映射为「非 completed 的进行态集合」（not_started/allergen_checking/
      ongoing/rating），取最近一条；
    - last_expiry_check：阶段一无按用户的检查时间存储（remote_config 为全局键，
      不适合多用户语义），直接返回服务端当前时间，「当日不重复」由前端本地存储实现；
    - seasonal_categories：静态月份映射（见 _SEASONAL_CATEGORIES），阶段二可配置化。
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Request
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.v1.config import get_switches
from app.api.v1.deps import resolve_anonymous_id, resolve_user
from app.core.db import get_db
from app.core.logging import get_logger
from app.core.user_security import user_id_from_request
from app.models import (
    CookingSession,
    Family,
    FamilyMember,
    Ingredient,
    InventoryItem,
    Recipe,
    RecipeStep,
)
from app.schemas.home import HomeResponse

router = APIRouter(prefix="/home", tags=["首页"])

logger = get_logger(__name__)

# 免责声明固定文案（对齐 DISCLAIMER_V1 免责口径；阶段一为固定常量，
# 阶段二可迁移至 remote_config 文案键做远程配置化）
_HOME_DISCLAIMER = (
    "本应用提供的菜谱、营养估算与食材建议均为智能参考信息，不构成医疗建议；"
    "涉及过敏原、特殊人群与疾病饮食请咨询专业医师，食材状况请以实际查验为准。"
)

# 未完成会话状态集合（任务口径 in_progress → 表 CHECK 枚举映射，见模块头）
_UNFINISHED_STATUSES = ("not_started", "allergen_checking", "ongoing", "rating")

# 临期提醒窗口（天）：active 且 3 天内到期
_EXPIRING_WINDOW_DAYS = 3

# 临期提醒最大条数
_EXPIRING_LIMIT = 5

# 当季推荐食材类别静态映射（按公历月份，华北/华东通用口径）。
# 🔴 阶段一为静态常量（无农时数据接入），键为月份 1~12，值为类别中文名列表；
# 阶段二可迁移至 remote_config（如 seasonal.categories）按月远程配置。
_SEASONAL_CATEGORIES: dict[int, list[str]] = {
    1: ["根茎类", "白菜甘蓝类", "柑橘类"],
    2: ["根茎类", "白菜甘蓝类", "豆苗类"],
    3: ["叶菜类", "豆类", "葱蒜类"],
    4: ["叶菜类", "豆类", "茄果类"],
    5: ["叶菜类", "瓜果类", "豆类"],
    6: ["瓜果类", "茄果类", "叶菜类"],
    7: ["瓜果类", "茄果类", "豆类"],
    8: ["瓜果类", "叶菜类", "豆类"],
    9: ["瓜果类", "根茎类", "叶菜类"],
    10: ["根茎类", "瓜果类", "菌菇类"],
    11: ["根茎类", "白菜甘蓝类", "菌菇类"],
    12: ["根茎类", "白菜甘蓝类", "柑橘类"],
}


def _load_unfinished_session(session: Session, user_id: int) -> dict | None:
    """查询本人最近未完成烹饪会话（函数）。

    参数：
        session：数据库会话。
        user_id：用户 ID。

    返回值：
        dict | None：{session_id, recipe_id, recipe_name, current_step, total_steps}；
        无未完成会话返回 None。

    异常：
        异常向上抛出（由调用方统一降级）。
    """
    row = session.execute(
        select(CookingSession.id, CookingSession.recipe_id, CookingSession.current_step_no, Recipe.title)
        .join(Recipe, CookingSession.recipe_id == Recipe.id)
        .where(CookingSession.user_id == user_id, CookingSession.status.in_(_UNFINISHED_STATUSES))
        .order_by(CookingSession.created_at.desc(), CookingSession.id.desc())
        .limit(1)
    ).first()
    if row is None:
        return None
    session_id, recipe_id, current_step, recipe_name = row
    total_steps = int(
        session.execute(
            select(func.count()).where(RecipeStep.recipe_id == recipe_id)
        ).scalar_one()
    )
    return {
        "session_id": int(session_id),
        "recipe_id": int(recipe_id),
        "recipe_name": str(recipe_name or ""),
        "current_step": int(current_step),
        "total_steps": total_steps,
    }


def _load_expiring(session: Session, user_id: int) -> list[dict]:
    """查询本人 3 天内到期的在库食材（函数）。

    说明：
        active = status IN (normal, expiring)；按到期日升序，最多 5 条。

    参数：
        session：数据库会话。
        user_id：用户 ID。

    返回值：
        list[dict]：{id, ingredient_name, expire_date, days_left, allergen_codes}。

    异常：
        异常向上抛出（由调用方统一降级）。
    """
    today = datetime.now(timezone(timedelta(hours=8))).date()  # 东八区业务日（中国无夏令时）
    deadline = today + timedelta(days=_EXPIRING_WINDOW_DAYS)
    rows = session.execute(
        select(
            InventoryItem.id,
            Ingredient.name,
            InventoryItem.expiry_date,
            Ingredient.allergen_codes,
        )
        .join(Ingredient, InventoryItem.ingredient_id == Ingredient.id)
        .where(
            InventoryItem.user_id == user_id,
            InventoryItem.status.in_(["normal", "expiring"]),
            InventoryItem.expiry_date.is_not(None),
            InventoryItem.expiry_date >= today,
            InventoryItem.expiry_date <= deadline,
        )
        .order_by(InventoryItem.expiry_date.asc())
        .limit(_EXPIRING_LIMIT)
    ).all()
    return [
        {
            "id": int(item_id),
            "ingredient_name": str(name),
            "expire_date": expiry_date.isoformat(),
            "days_left": (expiry_date - today).days,
            "allergen_codes": list(allergen_codes or []),
        }
        for item_id, name, expiry_date, allergen_codes in rows
    ]


def _load_profile_hint(session: Session, user_id: int) -> dict:
    """查询本人家庭档案提示（函数）。

    参数：
        session：数据库会话。
        user_id：用户 ID。

    返回值：
        dict：{has_profile: bool, member_count: int}（family+family_member，均排除软删行）。

    异常：
        异常向上抛出（由调用方统一降级）。
    """
    family = session.execute(
        select(Family).where(Family.user_id == user_id, Family.deleted_at.is_(None))
    ).scalar_one_or_none()
    if family is None:
        return {"has_profile": False, "member_count": 0}
    member_count = int(
        session.execute(
            select(func.count()).where(
                FamilyMember.family_id == family.id, FamilyMember.deleted_at.is_(None)
            )
        ).scalar_one()
    )
    return {"has_profile": member_count > 0, "member_count": member_count}


def _seasonal_categories() -> list[str]:
    """取当季推荐食材类别（静态月份映射）（函数）。

    参数：
        无。

    返回值：
        list[str]：当月类别列表（映射缺失时为空列表）。

    异常：
        无。
    """
    month = datetime.now(timezone(timedelta(hours=8))).month
    return list(_SEASONAL_CATEGORIES.get(month, []))


@router.get("", response_model=HomeResponse, summary="首页聚合（开关/断点/临期/档案/当季/免责）")
def get_home(
    request: Request,
    session: Session = Depends(get_db),
) -> HomeResponse:
    """首页聚合端点（函数）。

    说明：
        各子项独立 try/except 降级：失败子项记 warning 日志并取空值，整页恒 200。
        entries.vision / entries.innovation 与 remote_config 开关联动
        （复用 config.get_switches 的直查与缺省 True 语义）。

    参数：
        request：FastAPI 请求对象（读 X-Anonymous-Id 头）。
        session：请求级数据库会话。

    返回值：
        HomeResponse：聚合响应体（子项失败降级为空值）。

    异常：
        不向外抛业务异常（子项级降级；身份创建等致命异常由全局处理器兜底）。
    """
    # 无任何身份（无 JWT、无匿名头）：匿名空态（不创建用户行，避免无头轮询膨胀）
    if user_id_from_request(request) is None and not resolve_anonymous_id(None, request):
        return HomeResponse(last_expiry_check=datetime.now(UTC).isoformat())

    try:
        user = resolve_user(session, None, request)
        session.commit()
        user_id = int(user.id)
    except Exception as exc:  # noqa: BLE001 —— 身份解析失败按匿名空态降级
        logger.warning("home resolve user failed: %s", exc)
        session.rollback()
        return HomeResponse(last_expiry_check=datetime.now(UTC).isoformat())

    # 子项 1：入口开关（复用 config.get_switches：直查 remote_config，异常回退全开）
    entries = {
        "cooking": True,
        "vision": True,
        "seasonal": True,
        "goal": True,
        "fridge": True,
        "innovation": True,
    }
    try:
        switches = get_switches(session=session)
        entries["vision"] = switches.vision
        entries["innovation"] = switches.innovation
    except Exception as exc:  # noqa: BLE001 —— 开关失败保留缺省全开
        logger.warning("home load switches failed: %s", exc)

    # 子项 2：断点续做会话
    try:
        unfinished = _load_unfinished_session(session, user_id)
    except Exception as exc:  # noqa: BLE001 —— 失败降级 None
        logger.warning("home load unfinished session failed: %s", exc)
        unfinished = None

    # 子项 3：临期库存提醒
    try:
        expiring = _load_expiring(session, user_id)
    except Exception as exc:  # noqa: BLE001 —— 失败降级空列表
        logger.warning("home load expiring failed: %s", exc)
        expiring = []

    # 子项 4：家庭档案提示
    try:
        profile_hint = _load_profile_hint(session, user_id)
    except Exception as exc:  # noqa: BLE001 —— 失败降级无档案
        logger.warning("home load profile hint failed: %s", exc)
        profile_hint = {"has_profile": False, "member_count": 0}

    return HomeResponse(
        entries=entries,
        unfinished_session=unfinished,
        expiring=expiring,
        last_expiry_check=datetime.now(UTC).isoformat(),
        profile_hint=profile_hint,
        seasonal_categories=_seasonal_categories(),
        disclaimer=_HOME_DISCLAIMER,
    )
