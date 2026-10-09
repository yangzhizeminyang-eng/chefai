"""食材库路由模块。

职责：
    GET /v1/ingredients：食材库查询（分类过滤 + 关键词搜索）。
    关键词同时匹配 name 与 ingredient_alias（别名命中去重）；
    category 为 10 类编码（veg/meat/seafood/egg_milk/soy/staple/seasoning/dry/frozen/other）。
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.models import Ingredient, IngredientAlias
from app.schemas.ingredients import IngredientItem, IngredientListResponse

router = APIRouter(prefix="/ingredients", tags=["ingredients"])

# 10 类分类编码（供 OpenAPI 文档说明）
CATEGORY_CODES = "veg/meat/seafood/egg_milk/soy/staple/seasoning/dry/frozen/other"


@router.get("", response_model=IngredientListResponse, summary="食材库查询（分类/关键词含别名搜索）")
def list_ingredients(
    category: str | None = Query(default=None, max_length=20, description=f"分类编码：{CATEGORY_CODES}"),
    q: str | None = Query(default=None, max_length=50, description="关键词（匹配名称与别名）"),
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    session: Session = Depends(get_db),
) -> IngredientListResponse:
    """查询食材库（函数）。

    说明：
        - q 非空时：name 包含 OR 别名包含，命中食材按 id 去重；
        - category 非空时按编码精确过滤；
        - 返回 total（过滤后总数）+ items（别名随行聚合，供前端即时过滤与展示）。

    参数：
        category：分类编码（可 None = 全部）。
        q：关键词（可 None）。
        limit：分页大小（1~500）。
        offset：分页偏移。
        session：请求级数据库会话。

    返回值：
        IngredientListResponse：{total, items}。

    异常：
        数据库异常向上抛出（全局异常处理器兜底 500）。
    """
    keyword = (q or "").strip()

    # 命中别名的 ingredient_id 集合（关键词搜索时与 name 命中去重合并）
    alias_ing_ids = None
    if keyword:
        alias_ing_ids = set(
            session.execute(
                select(IngredientAlias.ingredient_id).where(IngredientAlias.alias.ilike(f"%{keyword}%"))
            ).scalars().all()
        )

    base_filters = [Ingredient.is_active.is_(True)]
    if category:
        base_filters.append(Ingredient.category == category)
    if keyword:
        # 名称包含 OR 别名命中（别名集合为空时仅名称条件）
        name_cond = Ingredient.name.ilike(f"%{keyword}%")
        if alias_ing_ids:
            base_filters.append(or_(name_cond, Ingredient.id.in_(alias_ing_ids)))
        else:
            base_filters.append(name_cond)

    total = int(
        session.execute(select(func.count(Ingredient.id)).where(*base_filters)).scalar() or 0
    )

    rows = (
        session.execute(
            select(Ingredient).where(*base_filters).order_by(Ingredient.id).limit(limit).offset(offset)
        )
        .scalars()
        .all()
    )

    # 批量聚合别名（避免 N+1：单查命中的食材行）
    alias_map: dict[int, list[str]] = {}
    if rows:
        alias_rows = session.execute(
            select(IngredientAlias.ingredient_id, IngredientAlias.alias).where(
                IngredientAlias.ingredient_id.in_([int(r.id) for r in rows])
            )
        ).all()
        for ing_id, alias in alias_rows:
            alias_map.setdefault(int(ing_id), []).append(alias)

    items = [
        IngredientItem(
            id=int(row.id),
            name=row.name,
            category=row.category,
            allergen_codes=list(row.allergen_codes or []),
            allergen_verified=bool(row.allergen_verified),
            aliases=alias_map.get(int(row.id), []),
            allergens=list(row.allergen_codes or []),
        )
        for row in rows
    ]
    return IngredientListResponse(total=total, items=items)
