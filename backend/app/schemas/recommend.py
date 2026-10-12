"""推荐主接口 Schema 模块。

职责：
    POST /v1/recommend 的请求/响应模型。字段对齐前端 types.ts
    RecommendRequest / RecommendResultItem / RecommendResponse / BlockedResponse，
    并附加营养结果（nutrition，Top 结果的每份估算）。
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from app.schemas.ask import BlockedResponse
from app.schemas.recipes import NutritionOut


class RecommendIngredient(BaseModel):
    """推荐输入食材项（模型类）。

    说明：
        ingredient_id 与 name 二选一（ID 优先）；quantity_level 为数量三档。

    属性：
        ingredient_id：食材 ID（与 name 至少其一）。
        name：食材名（库内名称或别名）。
        quantity_level：数量档位（few / enough / plenty，阶段一仅透传记录）。
    """

    ingredient_id: int | None = None
    name: str | None = Field(default=None, max_length=50)
    quantity_level: str | None = Field(default=None, pattern="^(few|enough|plenty)$")


class RecommendOptions(BaseModel):
    """推荐附加选项（模型类）。

    属性：
        show_filtered：是否返回被过滤菜谱的说明信息（W-02「显示被我过滤掉的菜」）。
    """

    show_filtered: bool = False


class RecommendRequest(BaseModel):
    """推荐请求体（模型类）。

    说明：
        ingredients 至少 1 条（缺食材由路由层返回 4xx 统一错误）；
        request_id 缺省时后端自动生成并回显。

    属性：
        request_id：幂等键（可缺省，后端自动生成）。
        client_type：客户端类型标识（如 web_stage1）。
        ingredients：已选食材列表（≥1）。
        options：附加选项。
        anonymous_id：匿名会话 ID（可缺省）。
        text：附加文本（可缺省，如「用土豆做点什么」）。
    """

    request_id: str | None = Field(default=None, max_length=40)
    client_type: str | None = Field(default=None, max_length=30)
    ingredients: list[RecommendIngredient] = Field(min_length=1)
    options: RecommendOptions = Field(default_factory=RecommendOptions)
    anonymous_id: str | None = Field(default=None, max_length=64)
    text: str | None = Field(default=None, max_length=500)


class RecommendResultItem(BaseModel):
    """推荐结果单条菜谱（模型类）。

    说明：
        对齐前端 RecommendResultItem；difficulty 为三档文案（easy/medium/hard），
        由 DB 1~5 难度映射（1-2→easy、3→medium、4-5→hard）。

    属性：
        recipe_id：菜谱 ID。
        title：菜名。
        match_level：三档匹配等级（can_cook_now / missing_1_2 / need_more）。
        covered_ingredients：已覆盖（用户现有）食材名列表。
        missing_ingredients：缺失食材名列表。
        time_minutes：总耗时（分钟）。
        difficulty：难度三档文案。
        calories_kcal：每份估算热量（kcal，None 表示未纳入统计）。
        allergens：菜谱含有的致敏原列表（菜谱自带 ∪ 食材聚合）。
        required_equipment：所需厨房设备。
        rank_score：7 因子加权排序得分。
        rank_reasons：排序理由（至少 1 条）。
        source：菜谱来源标注。
        cover_image_url：封面成品图 URL（/v1/media/recipe-covers/ 下；None 表示
            无图，前端回落程序化占位封面）。
    """

    recipe_id: int
    title: str
    match_level: str
    covered_ingredients: list[str] = Field(default_factory=list)
    missing_ingredients: list[str] = Field(default_factory=list)
    time_minutes: int | None = None
    difficulty: str = "medium"
    calories_kcal: float | None = None
    allergens: list[str] = Field(default_factory=list)
    required_equipment: list[str] = Field(default_factory=list)
    rank_score: float = 0.0
    rank_reasons: list[str] = Field(default_factory=list)
    source: str | None = None
    cover_image_url: str | None = None


class RecommendResponse(BaseModel):
    """推荐正常响应体（模型类）。

    说明：
        一票否决时路由层原样透传 BlockedResponse（不含本模型的 results 字段）。

    属性：
        request_id：幂等键回显。
        safe_mode：是否处于保守模式（风控异常降级）。
        results：三档推荐结果（≤8 条）。
        filtered_by：布尔硬过滤计数（allergen / dietary_restriction / difficulty）。
        disclaimer_id：附着的免责声明 ID。
        trace_id：Agent 调度 trace ID。
        nutrition：Top 结果的每份营养估算（可缺省）。
        partial_failures：部分 Agent 失败说明（可缺省）。
        notice：附加提示文案（可缺省）。
    """

    request_id: str | None = None
    safe_mode: bool = False
    results: list[RecommendResultItem] = Field(default_factory=list)
    filtered_by: dict = Field(default_factory=dict)
    disclaimer_id: str | None = None
    trace_id: str | None = None
    nutrition: NutritionOut | None = None
    partial_failures: list[str] | None = None
    notice: str | None = None


__all__ = [
    "RecommendIngredient",
    "RecommendOptions",
    "RecommendRequest",
    "RecommendResultItem",
    "RecommendResponse",
    "BlockedResponse",
]
