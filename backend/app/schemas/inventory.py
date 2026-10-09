"""库存与购物清单 Schema 模块。

职责：
    库存 CRUD（POST/PATCH/GET /v1/inventory）、临期查询（GET /v1/inventory/expiring）、
    两段式扣减（POST /v1/inventory/deduct-suggest、/deduct-confirm）与
    购物清单（/v1/shopping-list）的请求/响应模型。

字段映射说明（API 口径 → DB 列，ORM 不可改，见 app/models/cooking.py）：
    - quantity_level：API 三档 low/mid/plenty ↔ DB 枚举 little/enough/has
      （plenty=has、mid=enough、low=little；扣减档位降级 plenty→mid→low→删除）；
    - status：API active/used/expired/discarded ↔ DB normal|expiring/consumed/expired/deleted；
    - location：API 展示名 ↔ DB 列 storage（fridge/freezer/room/dry 四值枚举）；
    - expire_date：API 展示名 ↔ DB 列 expiry_date；
    - stocked_at：出库时间展示（取 DB created_at）；
    - quantity_note：购物清单备注 ↔ DB 列 category（String(20)，故限 20 字）；
    - from_recipe_name：来源菜名 ↔ DB 列 source_recipe_ids（能按菜名解析到菜谱则存
      recipe_id，否则存原始菜名字符串，读取时反向解析）。
"""

from __future__ import annotations

from datetime import date
from typing import Literal

from pydantic import BaseModel, Field

# ---------------------------------------------------------------------------
# 枚举类型别名（API 口径）
# ---------------------------------------------------------------------------

# 库存数量三档（API 口径；DB 存 little/enough/has，路由层做双向映射）
QuantityLevel = Literal["low", "mid", "plenty"]

# 存放位置四值（与 DB chk_storage 枚举一致）
StorageLocation = Literal["fridge", "freezer", "room", "dry"]

# 库存条目状态（API 口径；active 涵盖 DB normal/expiring 两态）
InventoryStatus = Literal["active", "used", "expired", "discarded"]

# 扣减确认动作：deduct=档位降一档（降到 low 再扣即删除条目）；mark_used=标记已用完
DeductAction = Literal["deduct", "mark_used"]


class AnonymousMixin(BaseModel):
    """匿名身份可选字段混入（模型类）。

    说明：
        沿用现有端点惯例：请求体 anonymous_id → X-Anonymous-Id 头 → 新建匿名用户。

    属性：
        anonymous_id：匿名会话 ID（可缺省，缺省读请求头）。
    """

    anonymous_id: str | None = Field(default=None, max_length=64)


class InventoryCreate(AnonymousMixin):
    """新增库存条目请求体（模型类）。

    属性：
        ingredient_id：食材 ID（须存在，否则 404）。
        quantity_level：数量档位（low/mid/plenty）。
        expire_date：到期日期（可缺省，仅提醒用途，RL-3 不做安否判定）。
        location：存放位置（fridge/freezer/room/dry，缺省 fridge）。
    """

    ingredient_id: int
    quantity_level: QuantityLevel
    expire_date: date | None = None
    location: StorageLocation = "fridge"


class InventoryPatch(AnonymousMixin):
    """更新库存条目请求体（模型类）。

    说明：
        status 状态机（API 口径）：active → used/expired/discarded；
        终态（used/expired/discarded）不允许再流转（含回退 active），非法流转 422。

    属性：
        quantity_level：数量档位（可缺省）。
        location：存放位置（可缺省）。
        expire_date：到期日期（可缺省）。
        status：目标状态（可缺省，受状态机约束）。
    """

    quantity_level: QuantityLevel | None = None
    location: StorageLocation | None = None
    expire_date: date | None = None
    status: InventoryStatus | None = None


class InventoryItemOut(BaseModel):
    """库存条目响应体（模型类）。

    说明：
        quantity_level/status/location/expire_date 均为 API 口径（映射见模块头）；
        allergen_codes 来自 ingredient.allergen_codes（H.9 致敏原标注）。

    属性：
        id：库存条目 ID。
        ingredient_id：食材 ID。
        ingredient_name：食材名。
        quantity_level：数量档位（low/mid/plenty）。
        stocked_at：入库时间（ISO 8601，取 created_at）。
        expire_date：到期日期（可 None）。
        location：存放位置（fridge/freezer/room/dry）。
        allergen_codes：食材致敏原 code 列表。
        status：条目状态（active/used/expired/discarded）。
    """

    id: int
    ingredient_id: int
    ingredient_name: str
    quantity_level: QuantityLevel
    stocked_at: str | None = None
    expire_date: date | None = None
    location: StorageLocation = "fridge"
    allergen_codes: list[str] = Field(default_factory=list)
    status: InventoryStatus = "active"


class InventoryListOut(BaseModel):
    """库存列表响应体（模型类）。

    属性：
        items：库存条目列表（默认按到期日升序、NULL 最后，临期优先）。
    """

    items: list[InventoryItemOut] = Field(default_factory=list)


class ExpiringGroupOut(BaseModel):
    """临期分组响应体（模型类）。

    说明：
        RL-3 红线：仅描述「距到期 X 天」，不出现可食用/不能吃等判定字段。

    属性：
        expire_date：到期日期。
        days_left：距到期天数（0 表示今天到期）。
        label：中性描述文案（如「距到期 2 天」）。
        items：该日期到期的库存条目列表。
    """

    expire_date: date
    days_left: int
    label: str
    items: list[InventoryItemOut] = Field(default_factory=list)


class ExpiringListOut(BaseModel):
    """临期查询响应体（模型类）。

    属性：
        days：查询窗口天数。
        groups：按到期日升序分组（仅含窗口内有到期日的在库条目）。
    """

    days: int = 3
    groups: list[ExpiringGroupOut] = Field(default_factory=list)


class DeductSuggestRequest(AnonymousMixin):
    """扣减建议请求体（模型类）。

    属性：
        session_id：烹饪会话 ID（须属于本人且已完成，否则 422/404）。
    """

    session_id: int


class DeductSuggestionOut(BaseModel):
    """单条扣减建议（模型类）。

    属性：
        ingredient_id：食材 ID。
        ingredient_name：食材名。
        suggest_action：建议动作（当前均为 deduct；mark_used 由用户确认时可选）。
        reason：建议原因（含菜谱用量描述）。
    """

    ingredient_id: int
    ingredient_name: str
    suggest_action: Literal["deduct"] = "deduct"
    reason: str


class DeductSuggestOut(BaseModel):
    """扣减建议响应体（模型类）。

    说明：
        只返回建议不改库存；菜谱主料但库存中不存在的食材不返回。

    属性：
        suggestions：建议列表（主料且在库）。
    """

    suggestions: list[DeductSuggestionOut] = Field(default_factory=list)


class DeductConfirmItem(BaseModel):
    """单条扣减确认（模型类）。

    属性：
        item_id：库存条目 ID（须属于本人且在库）。
        action：确认动作（deduct=降一档 / mark_used=标记已用）。
    """

    item_id: int
    action: DeductAction


class DeductConfirmRequest(AnonymousMixin):
    """扣减确认请求体（模型类）。

    属性：
        session_id：烹饪会话 ID（须属于本人且已完成）。
        confirmations：确认项列表（至少 1 条）。
    """

    session_id: int
    confirmations: list[DeductConfirmItem] = Field(min_length=1)


class DeductConfirmOut(BaseModel):
    """扣减确认响应体（模型类）。

    属性：
        applied：实际生效的确认条数。
    """

    applied: int = 0


class ShoppingListCreateItem(BaseModel):
    """购物清单新增单条请求体（模型类）。

    说明：
        quantity_note 持久化于 shopping_list_item.category 列（String(20)，限 20 字）；
        from_recipe_name 能按标题解析到菜谱则存 recipe_id，否则存原始字符串。

    属性：
        ingredient_id：食材 ID（须存在，否则 404）。
        quantity_note：数量备注（≤20 字，可缺省）。
        from_recipe_name：来源菜名（可缺省）。
    """

    ingredient_id: int
    quantity_note: str | None = Field(default=None, max_length=20)
    from_recipe_name: str | None = Field(default=None, max_length=100)


class ShoppingListCreateRequest(AnonymousMixin):
    """购物清单批量新增请求体（模型类）。

    属性：
        items：新增项列表（至少 1 条；ingredient_id 相同的既有行合并去重）。
    """

    items: list[ShoppingListCreateItem] = Field(min_length=1)


class ShoppingListCreateOut(BaseModel):
    """购物清单批量新增响应体（模型类）。

    属性：
        added：新建行数。
        merged：合并进既有行的条数（同名 ingredient_id 去重）。
    """

    added: int = 0
    merged: int = 0


class ShoppingListItemOut(BaseModel):
    """购物清单条目响应体（模型类）。

    属性：
        id：清单条目 ID。
        ingredient_id：食材 ID（可 None，自定义条目）。
        ingredient_name：条目名（取 ingredient.name）。
        quantity_note：数量备注（映射 category 列，可 None）。
        from_recipe_name：来源菜名（映射 source_recipe_ids 反解，可 None）。
        checked：是否已勾选（买入）。
        allergen_codes：食材致敏原 code 列表（自定义条目为空）。
    """

    id: int
    ingredient_id: int | None = None
    ingredient_name: str
    quantity_note: str | None = None
    from_recipe_name: str | None = None
    checked: bool = False
    allergen_codes: list[str] = Field(default_factory=list)


class ShoppingListOut(BaseModel):
    """购物清单列表响应体（模型类）。

    属性：
        items：清单条目列表（未勾选在前，按创建时间升序）。
    """

    items: list[ShoppingListItemOut] = Field(default_factory=list)


class ShoppingListCheckPatch(AnonymousMixin):
    """购物清单勾选状态更新请求体（模型类）。

    属性：
        checked：目标勾选状态。
    """

    checked: bool


class ShoppingToInventoryRequest(AnonymousMixin):
    """清单转入库存请求体（模型类）。

    属性：
        expire_date：转入后的到期日期（可缺省；档位固定 low，位置缺省 fridge）。
    """

    expire_date: date | None = None


class ShoppingToInventoryOut(BaseModel):
    """清单转入库存响应体（模型类）。

    属性：
        inventory_item_id：新建库存条目 ID。
    """

    inventory_item_id: int
