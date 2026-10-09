"""菜谱与营养 Schema 模块。

职责：
    GET /v1/recipes/{id}、GET /v1/recipes/{id}/nutrition 的响应模型。
    菜谱详情字段对齐前端 types.ts RecipeDetail（主料/辅料/调味三段清单 +
    步骤 no/description/duration_sec/tips/rescue/amount_hint），
    并附加任务要求的 ingredients / steps 原始量化字段（多余字段无害）。
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class NutritionOut(BaseModel):
    """营养估算结果（模型类）。

    说明：
        对齐前端 types.ts NutritionResult；缺失营养数据不按 0 计，
        以 excluded_items 标注「XX 未纳入统计」。

    属性：
        kcal：每份估算热量（kcal，None 表示未纳入统计）。
        protein：蛋白质（g/份）。
        fat：脂肪（g/份）。
        carbs：碳水化合物（g/份）。
        sodium：钠（mg/份）。
        per_serving：当前计算份数。
        excluded_items：未纳入统计的食材说明列表（不按 0 计）。
        estimate_note：估算说明（固定含「估算值，非实测值，误差约 ±15%」）。
    """

    kcal: float | None = None
    protein: float | None = None
    fat: float | None = None
    carbs: float | None = None
    sodium: float | None = None
    per_serving: int = 2
    excluded_items: list[str] = Field(default_factory=list)
    estimate_note: str = "估算值，非实测值，误差约 ±15%"


class RecipeIngredientItem(BaseModel):
    """菜谱食材行（模型类）。

    说明：
        对齐前端 RecipeIngredientItem：amount 为量化值描述串（如「200g」「100~150g」），
        由 amount_value 或 (amount_min, amount_max) + amount_unit 生成并随份数缩放；
        附加原始量化字段（amount_type/amount_value/amount_min/amount_max/amount_unit/
        amount_note，多余字段无害）。

    属性：
        name：食材名。
        amount：量化值描述串（缩放后）。
        is_main：是否主料。
        allergens：该食材的致敏原标注。
        substitute：替代建议（阶段一整谱级替代，单项为 None）。
        amount_type：用量类型（main/minor/seasoning）。
        amount_value：固定用量值（缩放后）。
        amount_min：区间下限（缩放后）。
        amount_max：区间上限（缩放后）。
        amount_unit：用量单位。
        amount_note：用量备注（勺参照等）。
    """

    name: str
    amount: str
    is_main: bool = False
    allergens: list[str] = Field(default_factory=list)
    substitute: str | None = None
    amount_type: str = "main"
    amount_value: float | None = None
    amount_min: float | None = None
    amount_max: float | None = None
    amount_unit: str | None = None
    amount_note: str | None = None


class RecipeStepItem(BaseModel):
    """菜谱步骤（模型类）。

    说明：
        对齐前端 RecipeStep（no/description/duration_sec/tips/rescue/amount_hint），
        附加 DB 原始字段（step_no/duration_seconds/key_point/failure_tips，
        供烹饪会话 steps 快照与后台复用）。

    属性：
        no：步骤序号（从 1 开始）。
        description：步骤描述。
        duration_sec：预计耗时（秒，0 表示无需等待）。
        tips：新手动作要点（对应 DB key_point）。
        rescue：失败补救建议（对应 DB failure_tips）。
        amount_hint：本步用量提示。
        step_no：步骤序号（与 no 同值，DB 原始字段名）。
        duration_seconds：预计耗时（与 duration_sec 同值）。
        key_point：新手动作要点（与 tips 同值）。
        failure_tips：失败补救建议（与 rescue 同值）。
    """

    no: int
    description: str
    duration_sec: int = 0
    tips: str | None = None
    rescue: str | None = None
    amount_hint: str | None = None
    step_no: int = 0
    duration_seconds: int = 0
    key_point: str | None = None
    failure_tips: str | None = None


class RecipeDetailResponse(BaseModel):
    """菜谱详情响应体（模型类）。

    说明：
        对齐前端 RecipeDetail；difficulty 为三档文案；servings 为缩放后份数；
        tips 为 DB 小贴士文本按行/分号拆分后的列表。

    属性：
        id：菜谱 ID。
        title：菜名。
        description：菜谱简介（阶段一无该字段，None）。
        difficulty：难度三档文案（easy/medium/hard）。
        time_minutes：总耗时（分钟）。
        servings：当前份数（随 servings 参数缩放）。
        calories_kcal：每份估算热量（kcal，None 表示未纳入统计）。
        allergen_codes：菜谱聚合致敏原列表。
        equipment：所需厨房设备。
        main_ingredients：主料清单。
        side_ingredients：辅料清单。
        seasoning_ingredients：调味料清单（用量必量化）。
        steps：步骤列表。
        substitutes：替代食材建议。
        tips：小贴士列表。
        source_label：来源标注。
        ingredients：全部食材行（附原始量化字段，供任务口径消费）。
    """

    id: int
    title: str
    description: str | None = None
    difficulty: str = "medium"
    time_minutes: int | None = None
    servings: int = 2
    calories_kcal: int | None = None
    allergen_codes: list[str] = Field(default_factory=list)
    equipment: list[str] = Field(default_factory=list)
    main_ingredients: list[RecipeIngredientItem] = Field(default_factory=list)
    side_ingredients: list[RecipeIngredientItem] = Field(default_factory=list)
    seasoning_ingredients: list[RecipeIngredientItem] = Field(default_factory=list)
    steps: list[RecipeStepItem] = Field(default_factory=list)
    substitutes: list[str] = Field(default_factory=list)
    tips: list[str] = Field(default_factory=list)
    source_label: str = ""
    ingredients: list[RecipeIngredientItem] = Field(default_factory=list)
