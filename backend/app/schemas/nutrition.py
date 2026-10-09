"""营养汇总 Schema 模块。

职责：
    GET /v1/nutrition/summary（按日/按餐聚合 meal_record）与
    POST /v1/nutrition/manual（手动补录，先过 RiskEngine input 闸门）的请求/响应模型。

口径说明：
    - 缺失营养的记录项进入 excluded（「XX 未纳入统计」），绝不按 0 计入合计：
      无任何有效数据的营养键值为 null（非 0）；
    - 碳水字段 API 名为 carb（对齐任务口径），DB 列为 carbs_g。
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

# 餐次类型（与 meal_record chk_meal_type 枚举一致）
MealType = Literal["breakfast", "lunch", "dinner", "snack"]

# 营养汇总固定免责声明（RL-6：不构成营养建议）
NUTRITION_DISCLAIMER = "估算值，非实测值，误差约 ±15%，不构成营养建议"


class AnonymousMixin(BaseModel):
    """匿名身份可选字段混入（模型类）。

    说明：
        沿用现有端点惯例：请求体 anonymous_id → X-Anonymous-Id 头 → 新建匿名用户。

    属性：
        anonymous_id：匿名会话 ID（可缺省，缺省读请求头）。
    """

    anonymous_id: str | None = Field(default=None, max_length=64)


class MealBucketOut(BaseModel):
    """单餐/合计营养桶（模型类）。

    说明：
        营养键值为 null 表示该桶内所有记录均缺失该营养（未纳入统计，不按 0 计）。

    属性：
        kcal：热量合计（kcal）。
        protein：蛋白质合计（g）。
        fat：脂肪合计（g）。
        carb：碳水化合物合计（g）。
        sodium：钠合计（mg）。
        excluded：未纳入统计的记录说明列表（如「米饭一碗 未纳入统计」）。
    """

    kcal: float | None = None
    protein: float | None = None
    fat: float | None = None
    carb: float | None = None
    sodium: float | None = None
    excluded: list[str] = Field(default_factory=list)


class SummaryDayOut(BaseModel):
    """单日营养汇总（模型类）。

    属性：
        date：日期（ISO 8601 字符串，如 2026-10-09）。
        meals：四餐桶（breakfast/lunch/dinner/snack，键恒存在）。
    """

    date: str
    meals: dict[str, MealBucketOut] = Field(default_factory=dict)


class NutritionSummaryOut(BaseModel):
    """营养汇总响应体（模型类）。

    属性：
        days：逐日汇总列表（含无记录日期，桶值为 null）。
        totals：窗口内合计（同桶结构）。
        excluded：全窗口未纳入统计说明（按出现顺序去重）。
        disclaimer：固定免责声明。
    """

    days: list[SummaryDayOut] = Field(default_factory=list)
    totals: MealBucketOut = Field(default_factory=MealBucketOut)
    excluded: list[str] = Field(default_factory=list)
    disclaimer: str = NUTRITION_DISCLAIMER


class ManualMealRequest(AnonymousMixin):
    """手动补录饮食记录请求体（模型类）。

    说明：
        description 先过 RiskEngine input 闸门：命中拦截规则 → 200 {blocked:true}
        不落库；通过后写 meal_record（source=manual，营养字段可空）→ 201。

    属性：
        meal_type：餐次（breakfast/lunch/dinner/snack）。
        description：记录描述（≤100 字，落 custom_name 列）。
    """

    meal_type: MealType
    description: str = Field(min_length=1, max_length=100)


class ManualMealCreatedOut(BaseModel):
    """手动补录成功响应体（模型类）。

    属性：
        id：meal_record ID。
        meal_type：餐次。
        description：记录描述。
        recorded_date：记录日期（ISO 8601）。
        blocked：是否被风控拦截（恒 False）。
    """

    id: int
    meal_type: MealType
    description: str
    recorded_date: str
    blocked: bool = False


class RiskBlockedOut(BaseModel):
    """风控拦截响应体（模型类）。

    说明：
        命中 input 闸门拦截规则时返回（200），不落库。

    属性：
        blocked：是否拦截（恒 True）。
        rule_id：命中规则编码（如 MR-001）。
        message：面向用户的安全话术（来自 risk_message 表）。
    """

    blocked: bool = True
    rule_id: str | None = None
    message: str
