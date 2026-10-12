"""收藏与个人中心路由模块。

职责：
    模块 I（tag=收藏与个人中心）：
    - GET    /v1/favorites：收藏列表（deleted_at 过滤，分组聚合）；
    - POST   /v1/favorites：收藏（重复幂等返回既有；菜谱不存在 404）；
    - DELETE /v1/favorites/{recipe_id}：取消收藏（软删 deleted_at → 204）；
    - GET    /v1/history：烹饪历史（cooking_session 完成倒序，带评分）；
    - GET    /v1/signature-dishes：拿手菜（cooked 且有评分聚合：次数≥2 且均分≥4）；
    - GET    /v1/settings：用户设置（preferences JSONB 与默认值合并）；
    - PUT    /v1/settings：用户设置（合并写入，未传字段保留）；
    - GET    /v1/me/export：个人数据导出（JSON 附件下载）；
    - DELETE /v1/me：注销（user 硬删 + 数据级联清理；order 为交易凭证保留，
      存在订单时 409 拒绝注销）。

身份：
    沿用现有惯例：请求体 anonymous_id → X-Anonymous-Id 头 → 新建匿名用户。
"""

from __future__ import annotations

import json
import math
from datetime import datetime

from fastapi import APIRouter, Depends, Query, Request, Response
from fastapi.responses import JSONResponse
from sqlalchemy import delete, func, select, update
from sqlalchemy.orm import Session

from app.api.v1.deps import (
    ERR_CONFLICT,
    ERR_NOT_FOUND,
    api_error,
    get_or_create_user,
    resolve_anonymous_id,
)
from app.core.db import get_db
from app.models import (
    CookingSession,
    DietGoal,
    Family,
    FamilyMember,
    FavoriteRecipe,
    Feedback,
    Ingredient,
    InventoryItem,
    MealRecord,
    Order,
    Recipe,
    RecipeFeedback,
    ShoppingListItem,
    User,
    UserSkillProfile,
)
from app.schemas.nutrition import MealBucketOut
from app.schemas.personal import (
    FavoriteCreate,
    FavoriteItemOut,
    FavoritesOut,
    HistoryItemOut,
    HistoryOut,
    SettingsOut,
    SettingsPatch,
    SignatureItemOut,
    SignatureOut,
)

router = APIRouter(tags=["收藏与个人中心"])

# 用户设置默认值（GET 合并口径；preferences 中未设置的字段取此默认）
_SETTINGS_DEFAULTS = {"font_size": "normal", "unit": "metric", "voice_enabled": True, "reminder_enabled": True}
# 设置白名单键（写入 preferences 时仅接受这些字段）
_SETTINGS_KEYS = ("font_size", "unit", "voice_enabled", "reminder_enabled")


def _resolve_user(session: Session, request: Request, anon_id: str | None) -> User:
    """解析当前用户（函数）。

    说明：
        请求体 anonymous_id → X-Anonymous-Id 头 → 新建匿名用户（与 cooking/auth 一致）。

    参数：
        session：数据库会话。
        request：FastAPI 请求对象。
        anon_id：请求体携带的匿名 ID（可 None）。

    返回值：
        User：用户 ORM 实例。

    异常：
        SQLAlchemyError 向上抛出（全局异常处理器兜底）。
    """
    user = get_or_create_user(session, resolve_anonymous_id(anon_id, request))
    session.commit()
    return user


# ---------------------------------------------------------------------------
# 收藏
# ---------------------------------------------------------------------------


@router.get("/favorites", response_model=FavoritesOut, summary="收藏列表（分组聚合，软删过滤）")
def list_favorites(
    request: Request,
    group: str | None = Query(default=None, max_length=64, description="按分组名过滤"),
    session: Session = Depends(get_db),
) -> FavoritesOut:
    """收藏列表端点（函数）。

    说明：
        仅返回 deleted_at IS NULL 的收藏；groups 为去重分组名；allergen_codes 为
        菜谱自带致敏原 ∪ 食材聚合致敏原。

    参数：
        request：FastAPI 请求对象。
        group：分组名过滤（可 None = 全部分组）。
        session：请求级数据库会话。

    返回值：
        FavoritesOut：{groups, items}。

    异常：
        数据库异常向上抛出。
    """
    user = _resolve_user(session, request, None)
    stmt = (
        select(FavoriteRecipe, Recipe)
        .join(Recipe, Recipe.id == FavoriteRecipe.recipe_id)
        .where(FavoriteRecipe.user_id == int(user.id), FavoriteRecipe.deleted_at.is_(None))
        .order_by(FavoriteRecipe.id)
    )
    if group:
        stmt = stmt.where(FavoriteRecipe.group_name == group)
    rows = session.execute(stmt).all()

    items: list[FavoriteItemOut] = []
    groups: list[str] = []
    for fav, recipe in rows:
        items.append(
            FavoriteItemOut(
                recipe_id=int(fav.recipe_id),
                recipe_name=recipe.title,
                group_name=fav.group_name,
                allergen_codes=sorted(
                    set(recipe.allergen_codes or []) | set(recipe.ingredient_allergen_codes or [])
                ),
            )
        )
        if fav.group_name not in groups:
            groups.append(fav.group_name)
    return FavoritesOut(groups=groups, items=items)


@router.post("/favorites", status_code=201, summary="收藏菜谱（重复幂等返回既有）")
def create_favorite(
    payload: FavoriteCreate, request: Request, session: Session = Depends(get_db)
) -> Response:
    """收藏菜谱端点（函数）。

    说明：
        - 菜谱不存在 → 404；
        - 未删除的重复收藏幂等：不重复建行，返回既有收藏（200）；
        - 新收藏 → 201。

    参数：
        payload：收藏请求体（recipe_id, group_name）。
        request：FastAPI 请求对象。
        session：请求级数据库会话。

    返回值：
        Response：201（新建）/ 200（幂等返回既有），JSON 体为收藏条目。

    异常：
        HTTPException 404：菜谱不存在。
    """
    user = _resolve_user(session, request, payload.anonymous_id)
    recipe = session.execute(select(Recipe).where(Recipe.id == payload.recipe_id)).scalar_one_or_none()
    if recipe is None:
        raise api_error(404, ERR_NOT_FOUND, "菜谱不存在", f"recipe_id={payload.recipe_id}")

    existing = session.execute(
        select(FavoriteRecipe).where(
            FavoriteRecipe.user_id == int(user.id),
            FavoriteRecipe.recipe_id == payload.recipe_id,
            FavoriteRecipe.deleted_at.is_(None),
        )
    ).scalar_one_or_none()

    def _body(fav: FavoriteRecipe) -> dict:
        """构造收藏响应体（内部函数）。

        参数：
            fav：收藏 ORM 实例。

        返回值：
            dict：收藏条目字典。

        异常：
            无。
        """
        return {
            "recipe_id": int(fav.recipe_id),
            "recipe_name": recipe.title,
            "group_name": fav.group_name,
            "allergen_codes": sorted(
                set(recipe.allergen_codes or []) | set(recipe.ingredient_allergen_codes or [])
            ),
        }

    if existing is not None:
        return JSONResponse(status_code=200, content=_body(existing))
    fav = FavoriteRecipe(user_id=int(user.id), recipe_id=int(recipe.id), group_name=payload.group_name)
    session.add(fav)
    session.commit()
    return JSONResponse(status_code=201, content=_body(fav))


@router.delete("/favorites/{recipe_id}", status_code=204, summary="取消收藏（软删）")
def delete_favorite(recipe_id: int, request: Request, session: Session = Depends(get_db)) -> Response:
    """取消收藏端点（函数）。

    说明：
        软删：deleted_at 置当前时间；不存在或已删除（或非本人）→ 404。

    参数：
        recipe_id：菜谱 ID。
        request：FastAPI 请求对象。
        session：请求级数据库会话。

    返回值：
        Response：204 无内容。

    异常：
        HTTPException 404：收藏不存在/已删除。
    """
    user = _resolve_user(session, request, None)
    fav = session.execute(
        select(FavoriteRecipe).where(
            FavoriteRecipe.user_id == int(user.id),
            FavoriteRecipe.recipe_id == recipe_id,
            FavoriteRecipe.deleted_at.is_(None),
        )
    ).scalar_one_or_none()
    if fav is None:
        raise api_error(404, ERR_NOT_FOUND, "收藏不存在或已取消", f"recipe_id={recipe_id}")
    fav.deleted_at = datetime.now()
    session.commit()
    return Response(status_code=204)


# ---------------------------------------------------------------------------
# 历史 / 拿手菜
# ---------------------------------------------------------------------------


@router.get("/history", response_model=HistoryOut, summary="烹饪历史（完成倒序）")
def list_history(
    request: Request,
    limit: int = Query(default=50, ge=1, le=200),
    session: Session = Depends(get_db),
) -> HistoryOut:
    """烹饪历史端点（函数）。

    说明：
        取本人已完成（completed）会话，按完成时间倒序；rating 来自该会话
        finish 时写入的 recipe_feedback（未评分 None）；duration_minutes 为
        completed_at - created_at 向上取整分钟数（无完成时间的旧数据为 None）。

    参数：
        request：FastAPI 请求对象。
        limit：返回条数上限（1~200，默认 50）。
        session：请求级数据库会话。

    返回值：
        HistoryOut：{items: [...]}。

    异常：
        数据库异常向上抛出。
    """
    user = _resolve_user(session, request, None)
    rows = session.execute(
        select(CookingSession, Recipe)
        .join(Recipe, Recipe.id == CookingSession.recipe_id)
        .where(CookingSession.user_id == int(user.id), CookingSession.status == "completed")
        .order_by(CookingSession.completed_at.desc().nulls_last(), CookingSession.id.desc())
        .limit(limit)
    ).all()

    session_ids = [int(cs.id) for cs, _ in rows]
    rating_map: dict[int, int] = {}
    if session_ids:
        for sid, rating in session.execute(
            select(RecipeFeedback.session_id, RecipeFeedback.rating)
            .where(
                RecipeFeedback.session_id.in_(session_ids),
                RecipeFeedback.rating.is_not(None),
            )
            .order_by(RecipeFeedback.id)
        ).all():
            rating_map.setdefault(int(sid), int(rating))

    return HistoryOut(
        items=[
            HistoryItemOut(
                session_id=int(cs.id),
                recipe_id=int(cs.recipe_id),
                recipe_name=recipe.title,
                finished_at=cs.completed_at.isoformat() if cs.completed_at else None,
                rating=rating_map.get(int(cs.id)),
                # 耗时分钟数：完成时间 - 创建时间，向上取整；无完成时间（旧数据）为 None
                duration_minutes=(
                    math.ceil((cs.completed_at - cs.created_at).total_seconds() / 60)
                    if cs.completed_at is not None and cs.created_at is not None
                    else None
                ),
            )
            for cs, recipe in rows
        ]
    )


@router.get("/signature-dishes", response_model=SignatureOut, summary="拿手菜（做完≥2 次且均分≥4）")
def list_signature_dishes(request: Request, session: Session = Depends(get_db)) -> SignatureOut:
    """拿手菜端点（函数）。

    说明：
        从 recipe_feedback（feedback_type=cooked 且 rating 非空）按菜谱聚合：
        cook_count≥2 且 avg_rating≥4 才入选，按均分、次数降序。

    参数：
        request：FastAPI 请求对象。
        session：请求级数据库会话。

    返回值：
        SignatureOut：{items: [...]}。

    异常：
        数据库异常向上抛出。
    """
    user = _resolve_user(session, request, None)
    rows = session.execute(
        select(
            RecipeFeedback.recipe_id,
            func.count(RecipeFeedback.id),
            func.avg(RecipeFeedback.rating),
        )
        .where(
            RecipeFeedback.user_id == int(user.id),
            RecipeFeedback.feedback_type == "cooked",
            RecipeFeedback.rating.is_not(None),
        )
        .group_by(RecipeFeedback.recipe_id)
    ).all()

    items: list[SignatureItemOut] = []
    for recipe_id, cook_count, avg_rating in rows:
        count = int(cook_count or 0)
        avg = round(float(avg_rating or 0), 2)
        if count < 2 or avg < 4:
            continue
        recipe = session.execute(
            select(Recipe.title).where(Recipe.id == recipe_id)
        ).scalar_one_or_none()
        if recipe is None:
            continue
        items.append(SignatureItemOut(recipe_id=int(recipe_id), recipe_name=recipe, cook_count=count, avg_rating=avg))
    items.sort(key=lambda i: (-i.avg_rating, -i.cook_count))
    return SignatureOut(items=items)


# ---------------------------------------------------------------------------
# 用户设置
# ---------------------------------------------------------------------------


@router.get("/settings", response_model=SettingsOut, summary="用户设置（默认值合并）")
def get_settings(request: Request, session: Session = Depends(get_db)) -> SettingsOut:
    """读取用户设置端点（函数）。

    说明：
        user.preferences JSONB 与默认值浅合并返回（未设置字段取默认）。

    参数：
        request：FastAPI 请求对象。
        session：请求级数据库会话。

    返回值：
        SettingsOut：合并后的设置。

    异常：
        数据库异常向上抛出。
    """
    user = _resolve_user(session, request, None)
    merged = {**_SETTINGS_DEFAULTS, **{k: v for k, v in (user.preferences or {}).items() if k in _SETTINGS_KEYS}}
    return SettingsOut(**merged)


@router.put("/settings", response_model=SettingsOut, summary="更新用户设置（合并写入）")
def put_settings(payload: SettingsPatch, request: Request, session: Session = Depends(get_db)) -> SettingsOut:
    """更新用户设置端点（函数）。

    说明：
        合并写入 user.preferences JSONB：仅写入显式传入的白名单字段，
        未传字段保留原值；anonymous_id 不写入 preferences。

    参数：
        payload：设置更新请求体。
        request：FastAPI 请求对象。
        session：请求级数据库会话。

    返回值：
        SettingsOut：合并后的最新设置。

    异常：
        数据库异常向上抛出。
    """
    user = _resolve_user(session, request, payload.anonymous_id)
    prefs = dict(user.preferences or {})
    for key, value in payload.model_dump(exclude_unset=True, exclude={"anonymous_id"}).items():
        if key in _SETTINGS_KEYS and value is not None:
            prefs[key] = value
    user.preferences = prefs
    session.commit()
    merged = {**_SETTINGS_DEFAULTS, **{k: v for k, v in prefs.items() if k in _SETTINGS_KEYS}}
    return SettingsOut(**merged)


# ---------------------------------------------------------------------------
# 数据导出 / 注销
# ---------------------------------------------------------------------------


@router.get("/me/export", summary="个人数据导出（JSON 附件下载）")
def export_me(request: Request, session: Session = Depends(get_db)) -> Response:
    """个人数据导出端点（函数）。

    说明：
        汇出结构：{meta, profile: {family, members, skill, goal},
        inventory, favorites, history, feedbacks, meal_records, shopping_list}；
        members 仅含未软删行（与档案列表读取端同口径，避免已删成员残留导出）；
        以 application/json + Content-Disposition: attachment 下载。

    参数：
        request：FastAPI 请求对象。
        session：请求级数据库会话。

    返回值：
        Response：JSON 文件下载响应。

    异常：
        数据库异常向上抛出。
    """
    user = _resolve_user(session, request, None)
    uid = int(user.id)

    family_rows = session.execute(
        select(Family).where(Family.user_id == uid).order_by(Family.id)
    ).scalars().all()
    member_rows = (
        session.execute(
            select(FamilyMember)
            .where(FamilyMember.family_id.in_([int(f.id) for f in family_rows] or [0]))
            .where(FamilyMember.deleted_at.is_(None))
            .order_by(FamilyMember.id)
        ).scalars().all()
        if family_rows
        else []
    )
    skill = session.execute(
        select(UserSkillProfile).where(UserSkillProfile.user_id == uid)
    ).scalar_one_or_none()
    goals = session.execute(
        select(DietGoal).where(DietGoal.user_id == uid).order_by(DietGoal.id)
    ).scalars().all()

    inv_rows = session.execute(
        select(InventoryItem, Ingredient.name)
        .join(Ingredient, Ingredient.id == InventoryItem.ingredient_id)
        .where(InventoryItem.user_id == uid)
        .order_by(InventoryItem.id)
    ).all()
    fav_rows = session.execute(
        select(FavoriteRecipe, Recipe.title)
        .join(Recipe, Recipe.id == FavoriteRecipe.recipe_id)
        .where(FavoriteRecipe.user_id == uid, FavoriteRecipe.deleted_at.is_(None))
        .order_by(FavoriteRecipe.id)
    ).all()
    history_rows = session.execute(
        select(CookingSession, Recipe.title)
        .join(Recipe, Recipe.id == CookingSession.recipe_id)
        .where(CookingSession.user_id == uid, CookingSession.status == "completed")
        .order_by(CookingSession.completed_at.desc().nulls_last())
    ).all()
    feedback_rows = session.execute(
        select(RecipeFeedback, Recipe.title)
        .join(Recipe, Recipe.id == RecipeFeedback.recipe_id)
        .where(RecipeFeedback.user_id == uid)
        .order_by(RecipeFeedback.id)
    ).all()
    meal_rows = session.execute(
        select(MealRecord).where(MealRecord.user_id == uid).order_by(MealRecord.id)
    ).scalars().all()
    shopping_rows = session.execute(
        select(ShoppingListItem).where(ShoppingListItem.user_id == uid).order_by(ShoppingListItem.id)
    ).scalars().all()

    def _iso(value: datetime | None) -> str | None:
        """时间转 ISO 字符串（内部函数）。

        参数：
            value：时间值（可 None）。

        返回值：
            str | None：ISO 8601 字符串。

        异常：
            无。
        """
        return value.isoformat() if value else None

    body = {
        "meta": {
            "exported_at": datetime.now().isoformat(),
            "anonymous_id": user.anonymous_id,
            "version": "1.0",
        },
        "profile": {
            "family": [
                {"id": int(f.id), "name": f.name, "member_limit": int(f.member_limit), "created_at": _iso(f.created_at)}
                for f in family_rows
            ],
            "members": [
                {
                    "nickname": m.nickname,
                    "age_group": m.age_group,
                    "allergen_codes": list(m.allergen_codes or []),
                    "dietary_restrictions": list(m.dietary_restrictions or []),
                    "special_diet": list(m.special_diet or []),
                    "special_population": list(m.special_population or []),
                }
                for m in member_rows
            ],
            "skill": (
                {
                    "skill_level": skill.skill_level,
                    "difficulty_cap": int(skill.difficulty_cap),
                    "equipment": list(skill.equipment or []),
                }
                if skill
                else None
            ),
            "goal": [
                {
                    "goal_type": g.goal_type,
                    "target_kcal": int(g.target_kcal) if g.target_kcal is not None else None,
                    "effective_from": g.effective_from.isoformat(),
                    "effective_to": g.effective_to.isoformat() if g.effective_to else None,
                }
                for g in goals
            ],
        },
        "inventory": [
            {
                "ingredient_name": name,
                "quantity_level": row.quantity_level,
                "storage": row.storage,
                "expiry_date": row.expiry_date.isoformat() if row.expiry_date else None,
                "status": row.status,
            }
            for row, name in inv_rows
        ],
        "favorites": [
            {"recipe_name": title, "group_name": fav.group_name, "created_at": _iso(fav.created_at)}
            for fav, title in fav_rows
        ],
        "history": [
            {"recipe_name": title, "finished_at": _iso(cs.completed_at), "servings": int(cs.servings)}
            for cs, title in history_rows
        ],
        "feedbacks": [
            {
                "recipe_name": title,
                "feedback_type": fb.feedback_type,
                "rating": int(fb.rating) if fb.rating is not None else None,
                "tags": list(fb.tags or []),
                "created_at": _iso(fb.created_at),
            }
            for fb, title in feedback_rows
        ],
        "meal_records": [
            {
                "recorded_date": r.recorded_date.isoformat(),
                "meal_type": r.meal_type,
                "custom_name": r.custom_name,
                "source": r.source,
            }
            for r in meal_rows
        ],
        "shopping_list": [
            {"name": r.name, "quantity_note": r.category, "checked": bool(r.checked)} for r in shopping_rows
        ],
        # 营养合计快照（复用营养桶聚合口径，缺失不按 0 计）
        "nutrition_totals": _export_nutrition_totals(meal_rows).model_dump(),
    }

    payload = json.dumps(body, ensure_ascii=False, default=str)
    response = JSONResponse(content=json.loads(payload), media_type="application/json")
    filename = f"aicook_export_{user.anonymous_id}_{datetime.now().date().isoformat()}.json"
    response.headers["Content-Disposition"] = f'attachment; filename="{filename}"'
    return response


def _export_nutrition_totals(meal_rows: list[MealRecord]) -> MealBucketOut:
    """导出用营养合计（函数）。

    说明：
        复用 nutrition 路由同口径：缺失营养不按 0 计（无有效值 → None）。

    参数：
        meal_rows：用户全部 meal_record 行。

    返回值：
        MealBucketOut：合计桶（excluded 置空，导出无需重复明细）。

    异常：
        无。
    """
    from app.api.v1.nutrition import _build_bucket  # 局部导入避免循环依赖

    bucket = _build_bucket(list(meal_rows))
    bucket.excluded = []
    return bucket


@router.delete("/me", status_code=204, summary="注销账号（级联清理，订单保留）")
def delete_me(request: Request, session: Session = Depends(get_db)) -> Response:
    """注销账号端点（函数）。

    说明：
        User 模型无软删列 → 硬删：
        - 存在交易订单（order.user_id 无级联且非空，交易凭证保留）→ 409 拒绝注销；
        - feedback.user_id 可空且无级联 → 置 NULL 脱敏保留工单；
        - family.user_id 无级联 → 先删 family（成员随 CASCADE 清理）；
        - 其余业务表（inventory/shopping/ favorite/meal/session/consent 等）
          由 user.id ON DELETE CASCADE 级联清理；
        - 注销后同 anonymous_id 再来由 auth upsert 视为新用户。

    参数：
        request：FastAPI 请求对象。
        session：请求级数据库会话。

    返回值：
        Response：204 无内容。

    异常：
        HTTPException 409：存在交易订单；数据库异常向上抛出。
    """
    user = _resolve_user(session, request, None)
    uid = int(user.id)

    order_count = int(
        session.execute(select(func.count(Order.id)).where(Order.user_id == uid)).scalar() or 0
    )
    if order_count > 0:
        raise api_error(409, ERR_CONFLICT, "账户存在交易订单，暂无法注销，请联系客服处理", f"orders={order_count}")

    # 工单脱敏保留（user_id 可空、无级联，直接删会违反外键）
    session.execute(update(Feedback).where(Feedback.user_id == uid).values(user_id=None))
    # 家庭档案：先删 family（family.user_id 无级联；成员随 ORM cascade / DB CASCADE 清理）
    family_ids = session.execute(select(Family.id).where(Family.user_id == uid)).scalars().all()
    if family_ids:
        session.execute(delete(FamilyMember).where(FamilyMember.family_id.in_(family_ids)))
        session.execute(delete(Family).where(Family.user_id == uid))
    # 其余数据随 user 行级联清理
    session.delete(user)
    session.commit()
    return Response(status_code=204)
