"""后台食材与营养管理路由模块（模块 K）。

职责：
    - GET/POST /admin/v1/ingredients、PUT/DELETE /admin/v1/ingredients/{id}：
      食材 CRUD（keyword 模糊、分页；DELETE 被菜谱引用时 409 拒绝）；
    - GET/POST/DELETE /admin/v1/ingredients/{id}/aliases：别名管理；
    - GET/PUT /admin/v1/nutrition/{ingredient_id}：营养数据读写
      （data_source 必填 422，溯源红线）。
    全部写操作记 operation_log（module='ingredient' / 'nutrition'）。
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.admin import ERR_CONFLICT, ERR_NOT_FOUND, api_error, page_args
from app.core.db import get_db
from app.core.security import require_writer, write_operation_log
from app.models import Ingredient, IngredientAlias, IngredientNutrition, RecipeIngredient
from app.schemas.admin import AliasCreate, IngredientCreate, IngredientUpdate, NutritionUpsertRequest

router = APIRouter(tags=["后台-食材与营养"])

_MODULE_ING = "ingredient"
_MODULE_NUT = "nutrition"


def _ingredient_snapshot(ing: Ingredient) -> dict:
    """食材审计快照（函数）。

    参数：
        ing：食材 ORM 实例。

    返回值：
        dict：可 JSONB 序列化的关键字段字典。

    异常：
        无。
    """
    return {
        "name": ing.name,
        "category": ing.category,
        "allergen_codes": list(ing.allergen_codes or []),
        "allergen_verified": bool(ing.allergen_verified),
        "is_active": bool(ing.is_active),
    }


def _nutrition_snapshot(n: IngredientNutrition) -> dict:
    """营养数据审计快照（函数）。

    参数：
        n：营养 ORM 实例。

    返回值：
        dict：数值字段字典（None 保留为 None，语义「未纳入统计」）。

    异常：
        无。
    """
    return {
        "kcal_100g": float(n.kcal_100g) if n.kcal_100g is not None else None,
        "protein_g": float(n.protein_g) if n.protein_g is not None else None,
        "fat_g": float(n.fat_g) if n.fat_g is not None else None,
        "carbs_g": float(n.carbs_g) if n.carbs_g is not None else None,
        "sodium_mg": float(n.sodium_mg) if n.sodium_mg is not None else None,
        "data_source": n.data_source,
        "source_license": n.source_license,
    }


def _load_ingredient_or_404(session: Session, ingredient_id: int) -> Ingredient:
    """加载食材或抛 404（函数）。

    参数：
        session：数据库会话。
        ingredient_id：食材 ID。

    返回值：
        Ingredient：食材 ORM 实例。

    异常：
        HTTPException 404：食材不存在。
    """
    ing = session.get(Ingredient, ingredient_id)
    if ing is None:
        raise api_error(404, ERR_NOT_FOUND, "食材不存在", f"ingredient_id={ingredient_id}")
    return ing


@router.get("/ingredients", summary="食材分页列表（keyword 模糊）")
def list_ingredients(
    keyword: str | None = None,
    session: Session = Depends(get_db),
    offset_limit: tuple[int, int] = Depends(page_args),
) -> dict:
    """食材列表端点（函数）。

    参数：
        keyword：名称模糊关键词（可 None）。
        session：请求级数据库会话。
        offset_limit：(offset, limit)。

    返回值：
        dict：{items, total}；item 含别名列表。

    异常：
        无。
    """
    offset, limit = offset_limit
    stmt = select(Ingredient)
    count_stmt = select(func.count(Ingredient.id))
    if keyword:
        like = f"%{keyword}%"
        alias_ids = select(IngredientAlias.ingredient_id).where(
            IngredientAlias.alias.ilike(like)
        )
        cond = Ingredient.name.ilike(like) | Ingredient.id.in_(alias_ids)
        stmt = stmt.where(cond)
        count_stmt = count_stmt.where(cond)
    total = session.execute(count_stmt).scalar_one()
    rows = session.execute(
        stmt.order_by(Ingredient.id).offset(offset).limit(limit)
    ).scalars().all()
    return {
        "items": [
            {
                "id": int(i.id),
                "name": i.name,
                "category": i.category,
                "allergen_codes": list(i.allergen_codes or []),
                "verified": bool(i.allergen_verified),
                "is_active": bool(i.is_active),
                "aliases": [a.alias for a in i.aliases],
            }
            for i in rows
        ],
        "total": int(total),
    }


@router.post("/ingredients", status_code=201, summary="创建食材")
def create_ingredient(
    payload: IngredientCreate,
    request: Request,
    admin=Depends(require_writer),
    session: Session = Depends(get_db),
) -> dict:
    """创建食材端点（函数）。

    参数：
        payload：创建请求体。
        request：FastAPI 请求对象（取 ip）。
        admin：当前管理员（require_writer）。
        session：请求级数据库会话。

    返回值：
        dict：创建后的食材对象。

    异常：
        HTTPException 409：同名食材已存在；403：readonly。
    """
    exists = session.execute(
        select(Ingredient.id).where(Ingredient.name == payload.name)
    ).scalar_one_or_none()
    if exists is not None:
        raise api_error(409, ERR_CONFLICT, "同名食材已存在", payload.name)
    ing = Ingredient(
        name=payload.name,
        category=payload.category,
        allergen_codes=payload.allergen_codes,
        allergen_verified=payload.verified,
        unit_conversion=payload.unit_conversion,
    )
    session.add(ing)
    session.flush()
    write_operation_log(
        session, admin, _MODULE_ING, "create",
        target_type="ingredient", target_id=int(ing.id),
        before=None, after=_ingredient_snapshot(ing), request=request,
    )
    session.commit()
    return {"id": int(ing.id), "name": ing.name, "category": ing.category}


@router.put("/ingredients/{ingredient_id}", summary="更新食材")
def update_ingredient(
    ingredient_id: int,
    payload: IngredientUpdate,
    request: Request,
    admin=Depends(require_writer),
    session: Session = Depends(get_db),
) -> dict:
    """更新食材端点（函数）。

    参数：
        ingredient_id：食材 ID。
        payload：更新请求体（全字段可选）。
        request：FastAPI 请求对象（取 ip）。
        admin：当前管理员（require_writer）。
        session：请求级数据库会话。

    返回值：
        dict：更新后的食材对象。

    异常：
        HTTPException 404：食材不存在；403：readonly。
    """
    ing = _load_ingredient_or_404(session, ingredient_id)
    before = _ingredient_snapshot(ing)
    if payload.name is not None:
        ing.name = payload.name
    if payload.category is not None:
        ing.category = payload.category
    if payload.allergen_codes is not None:
        ing.allergen_codes = payload.allergen_codes
    if payload.verified is not None:
        ing.allergen_verified = payload.verified
    if payload.is_active is not None:
        ing.is_active = payload.is_active
    write_operation_log(
        session, admin, _MODULE_ING, "update",
        target_type="ingredient", target_id=ingredient_id,
        before=before, after=_ingredient_snapshot(ing), request=request,
    )
    session.commit()
    return _ingredient_snapshot(ing) | {"id": int(ing.id)}


@router.delete("/ingredients/{ingredient_id}", summary="删除食材（被菜谱引用时 409）")
def delete_ingredient(
    ingredient_id: int,
    request: Request,
    admin=Depends(require_writer),
    session: Session = Depends(get_db),
) -> dict:
    """删除食材端点（函数）。

    说明：
        recipe_ingredient.ingredient_id 为 RESTRICT 外键：被引用时先查引用数，
        >0 返回 409（给出友好提示而非数据库异常）。

    参数：
        ingredient_id：食材 ID。
        request：FastAPI 请求对象（取 ip）。
        admin：当前管理员（require_writer）。
        session：请求级数据库会话。

    返回值：
        dict：{deleted: true, id}。

    异常：
        HTTPException 404：食材不存在；409：被菜谱引用；403：readonly。
    """
    ing = _load_ingredient_or_404(session, ingredient_id)
    ref_count = session.execute(
        select(func.count(RecipeIngredient.id)).where(
            RecipeIngredient.ingredient_id == ingredient_id
        )
    ).scalar_one()
    if int(ref_count) > 0:
        raise api_error(
            409, ERR_CONFLICT, "食材已被菜谱引用，无法删除", f"refs={int(ref_count)}"
        )
    before = _ingredient_snapshot(ing)
    session.delete(ing)
    write_operation_log(
        session, admin, _MODULE_ING, "delete",
        target_type="ingredient", target_id=ingredient_id,
        before=before, after=None, request=request,
    )
    session.commit()
    return {"deleted": True, "id": ingredient_id}


@router.get("/ingredients/{ingredient_id}/aliases", summary="食材别名列表")
def list_aliases(
    ingredient_id: int, session: Session = Depends(get_db)
) -> dict:
    """别名列表端点（函数）。

    参数：
        ingredient_id：食材 ID。
        session：请求级数据库会话。

    返回值：
        dict：{items: [{id, alias}]}。

    异常：
        HTTPException 404：食材不存在。
    """
    ing = _load_ingredient_or_404(session, ingredient_id)
    return {
        "items": [{"id": int(a.id), "alias": a.alias} for a in ing.aliases],
    }


@router.post("/ingredients/{ingredient_id}/aliases", status_code=201, summary="新增别名")
def create_alias(
    ingredient_id: int,
    payload: AliasCreate,
    request: Request,
    admin=Depends(require_writer),
    session: Session = Depends(get_db),
) -> dict:
    """新增别名为端点（函数）。

    参数：
        ingredient_id：食材 ID。
        payload：{alias}。
        request：FastAPI 请求对象（取 ip）。
        admin：当前管理员（require_writer）。
        session：请求级数据库会话。

    返回值：
        dict：{id, alias}。

    异常：
        HTTPException 404：食材不存在；409：别名已存在；403：readonly。
    """
    ing = _load_ingredient_or_404(session, ingredient_id)
    exists = session.execute(
        select(IngredientAlias.id).where(
            IngredientAlias.ingredient_id == ingredient_id,
            IngredientAlias.alias == payload.alias,
        )
    ).scalar_one_or_none()
    if exists is not None:
        raise api_error(409, ERR_CONFLICT, "别名已存在", payload.alias)
    alias = IngredientAlias(ingredient_id=int(ing.id), alias=payload.alias)
    session.add(alias)
    session.flush()
    write_operation_log(
        session, admin, _MODULE_ING, "create_alias",
        target_type="ingredient_alias", target_id=int(alias.id),
        before=None, after={"ingredient_id": ingredient_id, "alias": payload.alias},
        request=request,
    )
    session.commit()
    return {"id": int(alias.id), "alias": alias.alias}


@router.delete("/ingredients/{ingredient_id}/aliases/{alias_id}", summary="删除别名")
def delete_alias(
    ingredient_id: int,
    alias_id: int,
    request: Request,
    admin=Depends(require_writer),
    session: Session = Depends(get_db),
) -> dict:
    """删除别名端点（函数）。

    参数：
        ingredient_id：食材 ID（校验别名归属）。
        alias_id：别名 ID。
        request：FastAPI 请求对象（取 ip）。
        admin：当前管理员（require_writer）。
        session：请求级数据库会话。

    返回值：
        dict：{deleted: true}。

    异常：
        HTTPException 404：食材/别名不存在或不归属；403：readonly。
    """
    _load_ingredient_or_404(session, ingredient_id)
    alias = session.get(IngredientAlias, alias_id)
    if alias is None or int(alias.ingredient_id) != ingredient_id:
        raise api_error(404, ERR_NOT_FOUND, "别名不存在", f"alias_id={alias_id}")
    before = {"alias": alias.alias}
    session.delete(alias)
    write_operation_log(
        session, admin, _MODULE_ING, "delete_alias",
        target_type="ingredient_alias", target_id=alias_id,
        before=before, after=None, request=request,
    )
    session.commit()
    return {"deleted": True}


@router.get("/nutrition/{ingredient_id}", summary="食材营养数据查询")
def get_nutrition(
    ingredient_id: int, session: Session = Depends(get_db)
) -> dict:
    """营养查询端点（函数）。

    参数：
        ingredient_id：食材 ID。
        session：请求级数据库会话。

    返回值：
        dict：{ingredient_id, nutrition: 对象或 None}。

    异常：
        HTTPException 404：食材不存在。
    """
    _load_ingredient_or_404(session, ingredient_id)
    n = session.execute(
        select(IngredientNutrition).where(IngredientNutrition.ingredient_id == ingredient_id)
    ).scalar_one_or_none()
    return {
        "ingredient_id": ingredient_id,
        "nutrition": _nutrition_snapshot(n) if n is not None else None,
    }


@router.put("/nutrition/{ingredient_id}", summary="食材营养数据 upsert（data_source 必填）")
def upsert_nutrition(
    ingredient_id: int,
    payload: NutritionUpsertRequest,
    request: Request,
    admin=Depends(require_writer),
    session: Session = Depends(get_db),
) -> dict:
    """营养 upsert 端点（函数）。

    说明：
        data_source 由 Pydantic 必填校验（缺失 422）；存在行则更新，否则创建
        （一对一 unique ingredient_id）；before/after 写审计日志。

    参数：
        ingredient_id：食材 ID。
        payload：营养请求体。
        request：FastAPI 请求对象（取 ip）。
        admin：当前管理员（require_writer）。
        session：请求级数据库会话。

    返回值：
        dict：{ingredient_id, nutrition}。

    异常：
        HTTPException 404：食材不存在；403：readonly。
    """
    _load_ingredient_or_404(session, ingredient_id)
    n = session.execute(
        select(IngredientNutrition).where(IngredientNutrition.ingredient_id == ingredient_id)
    ).scalar_one_or_none()
    before = _nutrition_snapshot(n) if n is not None else None
    if n is None:
        n = IngredientNutrition(ingredient_id=ingredient_id, data_source=payload.data_source)
        session.add(n)
        session.flush()
    n.kcal_100g = payload.kcal_100g
    n.protein_g = payload.protein_g
    n.fat_g = payload.fat_g
    n.carbs_g = payload.carbs_g
    n.sodium_mg = payload.sodium_mg
    n.data_source = payload.data_source
    n.source_license = payload.source_license
    session.flush()
    write_operation_log(
        session, admin, _MODULE_NUT, "upsert",
        target_type="ingredient_nutrition", target_id=ingredient_id,
        before=before, after=_nutrition_snapshot(n), request=request,
    )
    session.commit()
    return {"ingredient_id": ingredient_id, "nutrition": _nutrition_snapshot(n)}
