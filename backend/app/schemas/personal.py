"""收藏与个人中心 Schema 模块。

职责：
    收藏（/v1/favorites）、历史（/v1/history）、拿手菜（/v1/signature-dishes）、
    用户设置（/v1/settings）、数据导出（GET /v1/me/export）与注销（DELETE /v1/me）
    的请求/响应模型。
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

# 字号三档（user.preferences.font_size 合法值）
FontSize = Literal["normal", "large", "xlarge"]


class AnonymousMixin(BaseModel):
    """匿名身份可选字段混入（模型类）。

    说明：
        沿用现有端点惯例：请求体 anonymous_id → X-Anonymous-Id 头 → 新建匿名用户。

    属性：
        anonymous_id：匿名会话 ID（可缺省，缺省读请求头）。
    """

    anonymous_id: str | None = Field(default=None, max_length=64)


class FavoriteCreate(AnonymousMixin):
    """收藏菜谱请求体（模型类）。

    属性：
        recipe_id：菜谱 ID（不存在 404；重复收藏幂等返回既有）。
        group_name：收藏分组名（缺省「默认分组」）。
    """

    recipe_id: int
    group_name: str = Field(default="默认分组", max_length=64)


class FavoriteItemOut(BaseModel):
    """收藏条目响应体（模型类）。

    属性：
        recipe_id：菜谱 ID。
        recipe_name：菜名。
        group_name：收藏分组名。
        allergen_codes：菜谱致敏原（自带 ∪ 食材聚合）。
    """

    recipe_id: int
    recipe_name: str
    group_name: str
    allergen_codes: list[str] = Field(default_factory=list)


class FavoritesOut(BaseModel):
    """收藏列表响应体（模型类）。

    属性：
        groups：去重后的分组名列表（按出现顺序）。
        items：收藏条目列表（deleted_at 过滤后）。
    """

    groups: list[str] = Field(default_factory=list)
    items: list[FavoriteItemOut] = Field(default_factory=list)


class HistoryItemOut(BaseModel):
    """历史记录条目响应体（模型类）。

    属性：
        session_id：烹饪会话 ID。
        recipe_id：菜谱 ID。
        recipe_name：菜名。
        finished_at：完成时间（ISO 8601）。
        rating：完成时评分（未评分 None）。
    """

    session_id: int
    recipe_id: int
    recipe_name: str
    finished_at: str | None = None
    rating: int | None = None


class HistoryOut(BaseModel):
    """历史记录响应体（模型类）。

    属性：
        items：已完成会话列表（完成时间倒序）。
    """

    items: list[HistoryItemOut] = Field(default_factory=list)


class SignatureItemOut(BaseModel):
    """拿手菜条目响应体（模型类）。

    属性：
        recipe_id：菜谱 ID。
        recipe_name：菜名。
        cook_count：有评分的做完次数（≥2 才入选）。
        avg_rating：平均评分（≥4 才入选）。
    """

    recipe_id: int
    recipe_name: str
    cook_count: int
    avg_rating: float


class SignatureOut(BaseModel):
    """拿手菜列表响应体（模型类）。

    属性：
        items：拿手菜列表（平均评分降序、次数降序）。
    """

    items: list[SignatureItemOut] = Field(default_factory=list)


class SettingsOut(BaseModel):
    """用户设置响应体（模型类）。

    说明：
        GET 返回 user.preferences JSONB 与默认值的合并结果（未设置字段取默认）。

    属性：
        font_size：字号（normal/large/xlarge，默认 normal）。
        unit：度量单位（默认 metric）。
        voice_enabled：语音开关（默认开）。
        reminder_enabled：提醒开关（默认开）。
    """

    font_size: str = "normal"
    unit: str = "metric"
    voice_enabled: bool = True
    reminder_enabled: bool = True


class SettingsPatch(BaseModel):
    """用户设置更新请求体（模型类）。

    说明：
        合并写入 user.preferences JSONB：仅写入显式传入字段，未传字段保留原值；
        anonymous_id 可选（沿用身份解析惯例），不写入 preferences。

    属性：
        font_size：字号（可缺省）。
        unit：度量单位（可缺省，≤20 字）。
        voice_enabled：语音开关（可缺省）。
        reminder_enabled：提醒开关（可缺省）。
        anonymous_id：匿名会话 ID（可缺省，缺省读 X-Anonymous-Id 头）。
    """

    font_size: FontSize | None = None
    unit: str | None = Field(default=None, max_length=20)
    voice_enabled: bool | None = None
    reminder_enabled: bool | None = None
    anonymous_id: str | None = Field(default=None, max_length=64)


class ExportMeta(BaseModel):
    """数据导出元信息（模型类）。

    属性：
        exported_at：导出时间（ISO 8601）。
        anonymous_id：用户匿名 ID（脱敏场景可自行去除）。
        version：导出结构版本。
    """

    exported_at: str
    anonymous_id: str
    version: str = "1.0"
