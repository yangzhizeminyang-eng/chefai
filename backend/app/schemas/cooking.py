"""烹饪会话 Schema 模块。

职责：
    POST/PATCH /v1/cooking/sessions、GET /v1/cooking/sessions/{id}、
    POST /v1/cooking/sessions/{id}/finish 的请求/响应模型。
    状态机（架构文档 §12.1 五态）：not_started → ongoing → rating → completed。
    字段对齐前端 types.ts CookingSession（id 为字符串、allergen_conflict 为冲突说明数组）。
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from app.schemas.recipes import NutritionOut, RecipeStepItem


class CookingSessionCreate(BaseModel):
    """创建烹饪会话请求体（模型类）。

    说明：
        前端仅发送 recipe_id/servings（request_id 由拦截器注入，anonymous_id 随请求头）。

    属性：
        recipe_id：菜谱 ID。
        servings：份数（1~20，缺省 2）。
        anonymous_id：匿名会话 ID（可缺省，缺省读 X-Anonymous-Id 头或新建匿名用户）。
    """

    recipe_id: int
    servings: int = Field(default=2, ge=1, le=20)
    anonymous_id: str | None = Field(default=None, max_length=64)


class CookingSessionPatch(BaseModel):
    """更新烹饪会话请求体（模型类）。

    说明：
        - current_step_no：直接设置当前步骤（断点续做恢复，前端实际使用）；
        - action：确定性动作（next/prev/abort，任务口径）；
        - ack：过敏原冲突「仍要继续」确认（冲突会话需 ack=true 才进入 ongoing）；
        - status：前端类型预留字段（阶段一忽略，完成必须走 /finish 接口）。

    属性：
        current_step_no：目标步骤序号（1 起）。
        action：动作（next / prev / abort）。
        ack：过敏原冲突确认标记。
        status：状态字段（兼容前端类型定义，阶段一不做业务处理）。
    """

    current_step_no: int | None = Field(default=None, ge=1)
    action: str | None = Field(default=None, pattern="^(next|prev|abort)$")
    ack: bool | None = None
    status: str | None = None


class FinishRequest(BaseModel):
    """完成烹饪会话请求体（模型类）。

    属性：
        rating：评分 1~5（可缺省，非空时写 recipe_feedback）。
        tags：评分标签列表（可缺省，随 recipe_feedback 落库）。
    """

    rating: int | None = Field(default=None, ge=1, le=5)
    tags: list[str] = Field(default_factory=list)


class CookingSessionOut(BaseModel):
    """烹饪会话响应体（模型类）。

    说明：
        对齐前端 CookingSession：id 为字符串（前端路由 /cook/:sessionId 直接拼接）；
        allergen_conflict 为冲突说明数组（空数组 = 无冲突，前端以 length 判断）；
        另附 allergen_conflict_bool（任务口径布尔语义，多余字段无害）。

    属性：
        id：会话 ID（字符串化主键）。
        recipe_id：关联菜谱 ID。
        servings：份数。
        current_step_no：当前步骤序号（从 1 开始）。
        status：会话状态（not_started / ongoing / rating / completed）。
        allergen_conflict：过敏原冲突说明列表（空 = 无冲突）。
        allergen_conflict_bool：是否存在过敏原冲突（布尔口径）。
        abandoned_step_no：放弃时所在步骤（abort 后非空）。
        started_at：开始时间（ISO 8601，可 None）。
        completed_at：完成时间（ISO 8601，可 None）。
        created_at：创建时间（ISO 8601）。
    """

    id: str
    recipe_id: int
    servings: int
    current_step_no: int = 1
    status: str = "not_started"
    allergen_conflict: list[str] = Field(default_factory=list)
    allergen_conflict_bool: bool = False
    abandoned_step_no: int | None = None
    started_at: str | None = None
    completed_at: str | None = None
    created_at: str | None = None


class CookingSessionDetailOut(CookingSessionOut):
    """烹饪会话详情响应体（模型类）。

    说明：
        GET /v1/cooking/sessions/{id} 返回：会话实体 + 菜谱步骤快照
        （断点续做恢复时前端无需再请求菜谱详情）。

    属性：
        recipe_title：菜谱名称。
        total_steps：步骤总数。
        steps：菜谱步骤快照列表（与菜谱详情 steps 结构一致）。
    """

    recipe_title: str | None = None
    total_steps: int = 0
    steps: list[RecipeStepItem] = Field(default_factory=list)


class FinishResponse(BaseModel):
    """完成会话响应体（模型类）。

    说明：
        返回完成后的会话 + 营养小结（复用 estimate_recipe_nutrition，每份口径）。

    属性：
        session：完成后的会话实体。
        nutrition：营养小结（每份估算，缺失项 excluded_items 标注）。
    """

    session: CookingSessionOut
    nutrition: NutritionOut | None = None
