"""食材库 Schema 模块。

职责：
    GET /v1/ingredients 的响应模型。字段对齐前端 types.ts Ingredient
    （id/name/category/allergens/aliases），并附加任务要求的
    allergen_codes / allergen_verified 原始字段（多余字段无害）。
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class IngredientItem(BaseModel):
    """食材条目（模型类）。

    说明：
        allergens 与 allergen_codes 同值并存：前端 Ingredient.allergens 消费展示，
        后端/管理口径使用 allergen_codes（GB 7718 八类 code）。

    属性：
        id：食材唯一 ID。
        name：食材名称。
        category：所属分类编码（veg/meat/seafood/egg_milk/soy/staple/seasoning/dry/frozen/other）。
        allergen_codes：致敏原编码列表（GB 7718 八类 code）。
        allergen_verified：致敏原标注是否已核实（false 时前端展示「待核实」）。
        aliases：别名列表（搜索命中用）。
        allergens：致敏原列表（与 allergen_codes 同值，前端契约字段）。
    """

    id: int
    name: str
    category: str
    allergen_codes: list[str] = Field(default_factory=list)
    allergen_verified: bool = False
    aliases: list[str] = Field(default_factory=list)
    allergens: list[str] = Field(default_factory=list)


class IngredientListResponse(BaseModel):
    """食材列表响应体（模型类）。

    属性：
        total：当前过滤条件下的总条数（供前端分页）。
        items：食材条目列表。
    """

    total: int
    items: list[IngredientItem] = Field(default_factory=list)
