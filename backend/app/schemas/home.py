"""首页聚合 Schema 模块。

职责：
    GET /v1/home 的响应模型。聚合结构对齐任务契约：
    entries（六入口开关）/ unfinished_session（断点续做）/ expiring（临期提醒）/
    last_expiry_check（当日不重复语义时间戳）/ profile_hint（档案提示）/
    seasonal_categories（当季推荐类别）/ disclaimer（免责声明文案）。
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class HomeEntries(BaseModel):
    """首页六入口开关（模型类）。

    说明：
        cooking/seasonal/goal/fridge 为固定入口（阶段一恒 true）；
        vision/innovation 与 remote_config 的 switch.* 开关联动（仅置灰展示）。

    属性：
        cooking：做菜入口。
        vision：AI 识别入口（联动 switch.vision）。
        seasonal：当季推荐入口。
        goal：饮食目标入口。
        fridge：冰箱库存入口。
        innovation：AI 菜品创新入口（联动 switch.innovation，模块 O 阶段二）。
    """

    cooking: bool = True
    vision: bool = True
    seasonal: bool = True
    goal: bool = True
    fridge: bool = True
    innovation: bool = True


class UnfinishedSessionOut(BaseModel):
    """断点续做会话摘要（模型类）。

    属性：
        session_id：烹饪会话 ID。
        recipe_id：菜谱 ID。
        recipe_name：菜谱名称。
        current_step：当前步骤序号（1 起）。
        total_steps：菜谱总步骤数。
    """

    session_id: int
    recipe_id: int
    recipe_name: str
    current_step: int
    total_steps: int


class ExpiringItemOut(BaseModel):
    """临期库存条目（模型类）。

    属性：
        id：库存条目 ID。
        ingredient_name：食材名称。
        expire_date：到期日（YYYY-MM-DD）。
        days_left：剩余天数（0 = 今日到期）。
        allergen_codes：食材致敏原 code 列表（GB 7718 八类）。
    """

    id: int
    ingredient_name: str
    expire_date: str
    days_left: int
    allergen_codes: list[str] = Field(default_factory=list)


class ProfileHintOut(BaseModel):
    """家庭档案提示（模型类）。

    属性：
        has_profile：是否已创建家庭档案（未删除）。
        member_count：档案内未删除成员数（无档案为 0）。
    """

    has_profile: bool = False
    member_count: int = 0


class HomeResponse(BaseModel):
    """首页聚合响应体（模型类）。

    说明：
        任何子项查询失败均降级为空值（None/[]），HTTP 恒 200。

    属性：
        entries：六入口开关。
        unfinished_session：最近未完成烹饪会话（无则为 None）。
        expiring：3 天内到期库存条目（按到期日升序，最多 5 条）。
        last_expiry_check：服务端出参时间戳（前端据此做「当日不重复检查」）。
        profile_hint：家庭档案提示。
        seasonal_categories：当季推荐食材类别（静态月份映射）。
        disclaimer：免责声明固定文案。
    """

    entries: HomeEntries = Field(default_factory=HomeEntries)
    unfinished_session: UnfinishedSessionOut | None = None
    expiring: list[ExpiringItemOut] = Field(default_factory=list)
    last_expiry_check: str | None = None
    profile_hint: ProfileHintOut = Field(default_factory=ProfileHintOut)
    seasonal_categories: list[str] = Field(default_factory=list)
    disclaimer: str = ""
