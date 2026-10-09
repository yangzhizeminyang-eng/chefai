"""库存与购物清单路由模块。

职责：
    模块 H（tag=库存与购物清单）：
    - GET    /v1/inventory：库存列表（默认在库 active；临期优先：到期日升序、NULL 最后）；
    - POST   /v1/inventory：新增库存条目（食材不存在 404；档位/位置枚举校验 422）；
    - GET    /v1/inventory/expiring：临期查询（N 天窗口内按到期日分组，仅描述「距到期 X 天」，RL-3）；
    - POST   /v1/inventory/deduct-suggest：扣减建议（两段式第一步，只建议不改库存）；
    - POST   /v1/inventory/deduct-confirm：扣减确认（两段式第二步，档位降级/标记已用 + operation 留痕）；
    - PATCH  /v1/inventory/{id}：更新条目（状态机：active → used/expired/discarded，非法流转 422）；
    - DELETE /v1/inventory/{id}：删除条目（204；只能操作本人条目，他人 404）；
    - GET/POST /v1/shopping-list：购物清单查询/批量新增（ingredient_id 相同合并去重）；
    - PATCH  /v1/shopping-list/{id}：勾选状态同步；
    - DELETE /v1/shopping-list/{id}：删除清单行；
    - POST   /v1/shopping-list/{id}/to-inventory：转入库存（low 档）并删除清单行。

口径映射（ORM 不可改，映射详见 app/schemas/inventory.py 模块头）：
    quantity_level plenty/mid/low ↔ DB has/enough/little；
    status active/used/expired/discarded ↔ DB normal|expiring/consumed/expired/deleted；
    location ↔ DB storage；expire_date ↔ DB expiry_date；
    扣减档位降级：plenty→mid→low→删除条目（DB 口径 has→enough→little→删除）。

身份：
    沿用现有惯例：请求体 anonymous_id → X-Anonymous-Id 头 → 新建匿名用户（deps.get_or_create_user）。
"""

from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, Query, Request, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.v1.deps import (
    ERR_BAD_REQUEST,
    ERR_NOT_FOUND,
    ERR_VALIDATION,
    api_error,
    format_amount,
    get_or_create_user,
    resolve_anonymous_id,
)
from app.core.db import get_db
from app.models import (
    CookingSession,
    Ingredient,
    InventoryItem,
    OperationLog,
    Recipe,
    RecipeIngredient,
    ShoppingListItem,
    User,
)
from app.schemas.inventory import (
    DeductConfirmOut,
    DeductConfirmRequest,
    DeductSuggestOut,
    DeductSuggestRequest,
    ExpiringListOut,
    InventoryCreate,
    InventoryItemOut,
    InventoryListOut,
    InventoryPatch,
    ShoppingListCheckPatch,
    ShoppingListCreateOut,
    ShoppingListCreateRequest,
    ShoppingListItemOut,
    ShoppingListOut,
    ShoppingToInventoryOut,
    ShoppingToInventoryRequest,
)

# 库存域路由（/v1/inventory）
router = APIRouter(prefix="/inventory", tags=["库存与购物清单"])

# 购物清单域路由（/v1/shopping-list，同属模块 H，由 router.py 一并注册）
shopping_router = APIRouter(prefix="/shopping-list", tags=["库存与购物清单"])

# ---------------------------------------------------------------------------
# API 口径 ↔ DB 口径映射
# ---------------------------------------------------------------------------

# 数量档位：API plenty/mid/low → DB has/enough/little
_LEVEL_API_TO_DB = {"plenty": "has", "mid": "enough", "low": "little"}
# 数量档位：DB → API（反向映射）
_LEVEL_DB_TO_API = {db: api for api, db in _LEVEL_API_TO_DB.items()}
# 扣减降档：DB 档位 → 下一档（None 表示删除条目），即 plenty→mid→low→删除
_LEVEL_DB_DOWN = {"has": "enough", "enough": "little", "little": None}
# 状态：DB → API（normal/expiring 均视为在库 active）
_STATUS_DB_TO_API = {
    "normal": "active",
    "expiring": "active",
    "consumed": "used",
    "expired": "expired",
    "deleted": "discarded",
}
# 状态：API → DB（active 显式设置时归一为 normal）
_STATUS_API_TO_DB = {
    "active": "normal",
    "used": "consumed",
    "expired": "expired",
    "discarded": "deleted",
}
# DB 在库状态集合（active 的两个内部态）
_DB_ACTIVE_STATUSES = ("normal", "expiring")
# 存放位置合法值（与 chk_storage 一致，用于缺省与校验提示）
_STORAGE_VALUES = ("fridge", "freezer", "room", "dry")


def _resolve_user(session: Session, request: Request, anon_id: str | None) -> User:
    """解析当前用户（函数）。

    说明：
        请求体 anonymous_id → X-Anonymous-Id 头 → 新建匿名用户（与 cooking/auth 一致）；
        新建用户立即提交，保证只读端点不丢身份行。

    参数：
        session：数据库会话。
        request：FastAPI 请求对象（读 X-Anonymous-Id 头）。
        anon_id：请求体携带的匿名 ID（可 None）。

    返回值：
        User：用户 ORM 实例。

    异常：
        SQLAlchemyError 向上抛出（全局异常处理器兜底）。
    """
    user = get_or_create_user(session, resolve_anonymous_id(anon_id, request))
    session.commit()
    return user


def _load_owned_item_or_404(session: Session, user_id: int, item_id: int) -> InventoryItem:
    """加载本人库存条目或抛 404（函数）。

    参数：
        session：数据库会话。
        user_id：当前用户 ID。
        item_id：库存条目 ID。

    返回值：
        InventoryItem：库存条目 ORM 实例。

    异常：
        HTTPException 404：条目不存在或不属于本人。
    """
    row = session.execute(
        select(InventoryItem).where(InventoryItem.id == item_id)
    ).scalar_one_or_none()
    if row is None or int(row.user_id) != int(user_id):
        raise api_error(404, ERR_NOT_FOUND, "库存条目不存在", f"inventory_item_id={item_id}")
    return row


def _item_out(row: InventoryItem, ingredient_name: str, allergen_codes: list[str] | None) -> dict:
    """库存条目 ORM → API 响应字典（函数）。

    说明：
        字段映射见模块头：stocked_at 取 created_at，location 取 storage，
        quantity_level/status 转换为 API 口径。

    参数：
        row：库存条目 ORM 实例。
        ingredient_name：食材名。
        allergen_codes：食材致敏原 code 列表。

    返回值：
        dict：InventoryItemOut 结构。

    异常：
        无。
    """
    return {
        "id": int(row.id),
        "ingredient_id": int(row.ingredient_id),
        "ingredient_name": ingredient_name,
        "quantity_level": _LEVEL_DB_TO_API.get(row.quantity_level, row.quantity_level),
        "stocked_at": row.created_at.isoformat() if row.created_at else None,
        "expire_date": row.expiry_date,
        "location": row.storage,
        "allergen_codes": list(allergen_codes or []),
        "status": _STATUS_DB_TO_API.get(row.status, row.status),
    }


def _load_ingredient_info(
    session: Session, ingredient_ids: list[int]
) -> tuple[dict[int, str], dict[int, list[str]]]:
    """批量加载食材名与致敏原（函数）。

    参数：
        session：数据库会话。
        ingredient_ids：食材 ID 列表。

    返回值：
        tuple：({id: 名称}, {id: 致敏原列表}) 两个映射。

    异常：
        无。
    """
    names: dict[int, str] = {}
    allergens: dict[int, list[str]] = {}
    if not ingredient_ids:
        return names, allergens
    rows = session.execute(
        select(Ingredient.id, Ingredient.name, Ingredient.allergen_codes).where(
            Ingredient.id.in_(ingredient_ids)
        )
    ).all()
    for ing_id, name, codes in rows:
        names[int(ing_id)] = name
        allergens[int(ing_id)] = list(codes or [])
    return names, allergens


def _load_finished_session_or_error(session: Session, user_id: int, session_id: int) -> CookingSession:
    """加载本人已完成烹饪会话或抛错（函数）。

    说明：
        会话不存在或不属于本人 → 404（与「他人条目 404」惯例一致）；
        存在但状态非 completed（DB 口径，即任务口径的 finished）→ 422。

    参数：
        session：数据库会话。
        user_id：当前用户 ID。
        session_id：烹饪会话 ID。

    返回值：
        CookingSession：会话 ORM 实例。

    异常：
        HTTPException 404：会话不存在/非本人；422：状态非 completed。
    """
    row = session.execute(
        select(CookingSession).where(CookingSession.id == session_id)
    ).scalar_one_or_none()
    if row is None or int(row.user_id) != int(user_id):
        raise api_error(404, ERR_NOT_FOUND, "烹饪会话不存在", f"session_id={session_id}")
    if row.status != "completed":
        raise api_error(
            422,
            ERR_VALIDATION,
            f"会话尚未完成（当前状态 {row.status}），无法生成扣减建议",
            f"status={row.status}",
        )
    return row


# ---------------------------------------------------------------------------
# 库存 CRUD
# ---------------------------------------------------------------------------


@router.get("", response_model=InventoryListOut, summary="库存列表（默认在库，临期优先排序）")
def list_inventory(
    request: Request,
    status: str | None = Query(default="active", description="状态过滤：active/used/expired/discarded"),
    session: Session = Depends(get_db),
) -> InventoryListOut:
    """库存列表端点（函数）。

    说明：
        默认只返回在库条目（active，涵盖 DB normal/expiring）；排序为到期日升序、
        NULL 最后（临期优先），同日按 id 升序；每条携带 ingredient.allergen_codes（H.9）。

    参数：
        request：FastAPI 请求对象（身份解析）。
        status：状态过滤（active/used/expired/discarded，非法值 422）。
        session：请求级数据库会话。

    返回值：
        InventoryListOut：{items: [...]}。

    异常：
        HTTPException 422：status 非法；数据库异常向上抛出。
    """
    user = _resolve_user(session, request, None)
    if status is not None and status not in _STATUS_API_TO_DB:
        raise api_error(
            422, ERR_VALIDATION, "status 仅支持 active/used/expired/discarded", f"status={status}"
        )
    stmt = select(InventoryItem).where(InventoryItem.user_id == int(user.id))
    if status == "active":
        stmt = stmt.where(InventoryItem.status.in_(_DB_ACTIVE_STATUSES))
    elif status is not None:
        stmt = stmt.where(InventoryItem.status == _STATUS_API_TO_DB[status])
    # 临期优先：到期日升序、NULL 最后，再按 id 稳定排序
    stmt = stmt.order_by(InventoryItem.expiry_date.asc().nulls_last(), InventoryItem.id)
    rows = session.execute(stmt).scalars().all()
    names, allergens = _load_ingredient_info(session, [int(r.ingredient_id) for r in rows])
    return InventoryListOut(
        items=[
            InventoryItemOut(**_item_out(r, names.get(int(r.ingredient_id), ""), allergens.get(int(r.ingredient_id))))
            for r in rows
        ]
    )


@router.post("", status_code=201, summary="新增库存条目")
def create_inventory_item(
    payload: InventoryCreate, request: Request, session: Session = Depends(get_db)
) -> InventoryItemOut:
    """新增库存条目端点（函数）。

    说明：
        食材必须存在（404）；quantity_level/location 由 Pydantic 枚举校验（422）；
        source=manual、purchase_date=当天、status=normal（API 口径 active）。

    参数：
        payload：创建请求体。
        request：FastAPI 请求对象。
        session：请求级数据库会话。

    返回值：
        InventoryItemOut：新建条目（201）。

    异常：
        HTTPException 404：食材不存在。
    """
    user = _resolve_user(session, request, payload.anonymous_id)
    ingredient = session.execute(
        select(Ingredient).where(Ingredient.id == payload.ingredient_id)
    ).scalar_one_or_none()
    if ingredient is None:
        raise api_error(404, ERR_NOT_FOUND, "食材不存在", f"ingredient_id={payload.ingredient_id}")
    row = InventoryItem(
        user_id=int(user.id),
        ingredient_id=int(ingredient.id),
        quantity_level=_LEVEL_API_TO_DB[payload.quantity_level],
        storage=payload.location,
        purchase_date=date.today(),
        expiry_date=payload.expire_date,
        status="normal",
        source="manual",
    )
    session.add(row)
    session.commit()
    return InventoryItemOut(**_item_out(row, ingredient.name, list(ingredient.allergen_codes or [])))


@router.get("/expiring", response_model=ExpiringListOut, summary="临期查询（N 天窗口按天分组）")
def list_expiring(
    request: Request,
    days: int = Query(default=3, ge=1, le=30, description="临期窗口天数"),
    session: Session = Depends(get_db),
) -> ExpiringListOut:
    """临期查询端点（函数）。

    说明：
        返回在库（active）且到期日落在 [今天, 今天+N天] 的条目，按到期日升序分组；
        RL-3 红线：仅中性描述「距到期 X 天」，不做可食用/不能吃判定。

    参数：
        request：FastAPI 请求对象。
        days：窗口天数（1~30，默认 3）。
        session：请求级数据库会话。

    返回值：
        ExpiringListOut：{days, groups: [{expire_date, days_left, label, items}]}。

    异常：
        数据库异常向上抛出。
    """
    user = _resolve_user(session, request, None)
    today = date.today()
    rows = session.execute(
        select(InventoryItem)
        .where(
            InventoryItem.user_id == int(user.id),
            InventoryItem.status.in_(_DB_ACTIVE_STATUSES),
            InventoryItem.expiry_date.is_not(None),
            InventoryItem.expiry_date >= today,
            InventoryItem.expiry_date <= today.fromordinal(today.toordinal() + days),
        )
        .order_by(InventoryItem.expiry_date, InventoryItem.id)
    ).scalars().all()
    names, allergens = _load_ingredient_info(session, [int(r.ingredient_id) for r in rows])

    groups: list[dict] = []
    bucket: dict[date, list[InventoryItemOut]] = {}
    for r in rows:
        bucket.setdefault(r.expiry_date, []).append(
            InventoryItemOut(
                **_item_out(r, names.get(int(r.ingredient_id), ""), allergens.get(int(r.ingredient_id)))
            )
        )
    for expire_date, items in sorted(bucket.items(), key=lambda kv: kv[0]):
        days_left = expire_date.toordinal() - today.toordinal()
        groups.append(
            {
                "expire_date": expire_date,
                "days_left": days_left,
                "label": f"距到期 {days_left} 天",
                "items": items,
            }
        )
    return ExpiringListOut(days=days, groups=groups)


# ---------------------------------------------------------------------------
# 两段式扣减（建议 → 确认）
# ---------------------------------------------------------------------------


@router.post("/deduct-suggest", response_model=DeductSuggestOut, summary="扣减建议（只建议不改库存）")
def suggest_deduct(
    payload: DeductSuggestRequest, request: Request, session: Session = Depends(get_db)
) -> DeductSuggestOut:
    """扣减建议端点（函数）。

    说明：
        针对已完成会话的菜谱主料（amount_type=main）生成建议：
        主料且本人在库（active）存在 → suggest_action=deduct，reason 含按份数缩放后的用量；
        主料但无库存 → 不返回。本端点绝不修改库存。

    参数：
        payload：请求体（session_id）。
        request：FastAPI 请求对象。
        session：请求级数据库会话。

    返回值：
        DeductSuggestOut：{suggestions: [...]}。

    异常：
        HTTPException 404：会话不存在/非本人；422：会话未完成。
    """
    user = _resolve_user(session, request, payload.anonymous_id)
    cook_session = _load_finished_session_or_error(session, int(user.id), payload.session_id)

    recipe = session.execute(
        select(Recipe).where(Recipe.id == cook_session.recipe_id)
    ).scalar_one_or_none()
    base_servings = int(recipe.servings or 2) if recipe else 2
    ratio = int(cook_session.servings) / base_servings

    mains = session.execute(
        select(RecipeIngredient, Ingredient.name)
        .join(Ingredient, Ingredient.id == RecipeIngredient.ingredient_id)
        .where(
            RecipeIngredient.recipe_id == cook_session.recipe_id,
            RecipeIngredient.amount_type == "main",
        )
        .order_by(RecipeIngredient.sort_order, RecipeIngredient.id)
    ).all()

    # 本人在库（active）条目：食材 ID → 条目
    stock_rows = session.execute(
        select(InventoryItem).where(
            InventoryItem.user_id == int(user.id),
            InventoryItem.status.in_(_DB_ACTIVE_STATUSES),
        )
    ).scalars().all()
    stocked: dict[int, InventoryItem] = {int(r.ingredient_id): r for r in stock_rows}

    suggestions = []
    for ri, ing_name in mains:
        item = stocked.get(int(ri.ingredient_id))
        if item is None:
            continue  # 主料无库存 → 不返回建议
        amount = format_amount(
            None if ri.amount_value is None else round(float(ri.amount_value) * ratio, 2),
            None if ri.amount_min is None else round(float(ri.amount_min) * ratio, 2),
            None if ri.amount_max is None else round(float(ri.amount_max) * ratio, 2),
            ri.amount_unit,
        )
        suggestions.append(
            {
                "ingredient_id": int(ri.ingredient_id),
                "ingredient_name": ing_name,
                "suggest_action": "deduct",
                "reason": f"菜谱用量 {amount}（{int(cook_session.servings)} 人份），建议从库存扣减一档",
            }
        )
    return DeductSuggestOut(suggestions=suggestions)


@router.post("/deduct-confirm", response_model=DeductConfirmOut, summary="扣减确认（生效并留痕）")
def confirm_deduct(
    payload: DeductConfirmRequest, request: Request, session: Session = Depends(get_db)
) -> DeductConfirmOut:
    """扣减确认端点（函数）。

    说明：
        用户对建议确认后生效：
        - deduct：档位降一档（plenty→mid→low→删除条目，DB 口径 has→enough→little→删除）；
        - mark_used：status='used'（DB consumed）；
        每条生效写 operation_log 留痕（module=inventory，含改前/改后快照）。

    参数：
        payload：请求体（session_id + confirmations）。
        request：FastAPI 请求对象。
        session：请求级数据库会话。

    返回值：
        DeductConfirmOut：{applied: 生效条数}。

    异常：
        HTTPException 404：会话或库存条目不存在/非本人；
        422：会话未完成、条目不在库或 action 非法（Pydantic）。
    """
    user = _resolve_user(session, request, payload.anonymous_id)
    _load_finished_session_or_error(session, int(user.id), payload.session_id)

    applied = 0
    for conf in payload.confirmations:
        item = _load_owned_item_or_404(session, int(user.id), conf.item_id)
        if item.status not in _DB_ACTIVE_STATUSES:
            raise api_error(
                422,
                ERR_VALIDATION,
                f"库存条目当前状态（{_STATUS_DB_TO_API.get(item.status, item.status)}）不可扣减",
                f"item_id={item.id}",
            )
        before = {"quantity_level": item.quantity_level, "status": item.status}
        if conf.action == "deduct":
            next_level = _LEVEL_DB_DOWN.get(item.quantity_level)
            if next_level is None:
                # 已是 low 档再扣 → 删除条目
                session.delete(item)
                after: dict | None = {"quantity_level": None, "status": "deleted"}
            else:
                item.quantity_level = next_level
                after = {"quantity_level": next_level, "status": item.status}
        else:  # mark_used
            item.status = "consumed"
            after = {"quantity_level": item.quantity_level, "status": item.status}
        session.add(
            OperationLog(
                admin_user_id=None,
                module="inventory",
                action=str(conf.action),
                target_type="inventory_item",
                target_id=int(conf.item_id),
                before_snapshot=before,
                after_snapshot=after,
            )
        )
        applied += 1
    session.commit()
    return DeductConfirmOut(applied=applied)


# ---------------------------------------------------------------------------
# 单条目更新/删除
# ---------------------------------------------------------------------------


@router.patch("/{item_id}", response_model=InventoryItemOut, summary="更新库存条目（状态机校验）")
def patch_inventory_item(
    item_id: int, payload: InventoryPatch, request: Request, session: Session = Depends(get_db)
) -> InventoryItemOut:
    """更新库存条目端点（函数）。

    说明：
        只能操作本人条目（他人 404）。状态机（API 口径）：
        active → used/expired/discarded；终态（used/expired/discarded）任何再流转
        （含回退 active）均 422；location/expire_date/quantity_level 可独立更新。

    参数：
        item_id：库存条目 ID。
        payload：更新请求体（各字段可缺省）。
        request：FastAPI 请求对象。
        session：请求级数据库会话。

    返回值：
        InventoryItemOut：更新后的条目。

    异常：
        HTTPException 404：条目不存在/非本人；422：非法状态流转。
    """
    user = _resolve_user(session, request, payload.anonymous_id)
    row = _load_owned_item_or_404(session, int(user.id), item_id)

    if payload.quantity_level is not None:
        row.quantity_level = _LEVEL_API_TO_DB[payload.quantity_level]
    if payload.location is not None:
        row.storage = payload.location
    if payload.expire_date is not None:
        row.expiry_date = payload.expire_date
    if payload.status is not None:
        current_api_status = _STATUS_DB_TO_API.get(row.status, row.status)
        if payload.status != current_api_status:
            if current_api_status != "active":
                raise api_error(
                    422,
                    ERR_VALIDATION,
                    f"当前状态 {current_api_status} 为终态，不允许再流转（含回退 active）",
                    f"from={current_api_status},to={payload.status}",
                )
            row.status = _STATUS_API_TO_DB[payload.status]
    session.commit()
    names, allergens = _load_ingredient_info(session, [int(row.ingredient_id)])
    return InventoryItemOut(
        **_item_out(row, names.get(int(row.ingredient_id), ""), allergens.get(int(row.ingredient_id)))
    )


@router.delete("/{item_id}", status_code=204, summary="删除库存条目")
def delete_inventory_item(
    item_id: int, request: Request, session: Session = Depends(get_db)
) -> Response:
    """删除库存条目端点（函数）。

    参数：
        item_id：库存条目 ID。
        request：FastAPI 请求对象。
        session：请求级数据库会话。

    返回值：
        Response：204 无内容。

    异常：
        HTTPException 404：条目不存在/非本人。
    """
    user = _resolve_user(session, request, None)
    row = _load_owned_item_or_404(session, int(user.id), item_id)
    session.delete(row)
    session.commit()
    return Response(status_code=204)


# ---------------------------------------------------------------------------
# 购物清单
# ---------------------------------------------------------------------------


def _resolve_recipe_ref(session: Session, recipe_name: str | None) -> int | str | None:
    """来源菜名 → 持久化引用（函数）。

    说明：
        能按标题精确匹配菜谱 → 存 recipe_id（int）；否则存原始菜名（str）。
        读取时由 _recipe_name_from_refs 反解。

    参数：
        session：数据库会话。
        recipe_name：来源菜名（可 None）。

    返回值：
        int | str | None：recipe_id 或原始菜名（空值返回 None）。

    异常：
        无。
    """
    if not recipe_name or not recipe_name.strip():
        return None
    name = recipe_name.strip()
    recipe_id = session.execute(
        select(Recipe.id).where(Recipe.title == name).limit(1)
    ).scalar_one_or_none()
    return int(recipe_id) if recipe_id is not None else name


def _recipe_name_from_refs(session: Session, refs: list | None) -> str | None:
    """持久化引用 → 来源菜名（函数）。

    说明：
        int 元素按 recipe id 反查标题（查不到跳过）；str 元素即原始菜名。

    参数：
        session：数据库会话。
        refs：source_recipe_ids 列表（可 None）。

    返回值：
        str | None：首个可解析的菜名。

    异常：
        无。
    """
    for ref in refs or []:
        if isinstance(ref, bool):
            continue
        if isinstance(ref, int):
            title = session.execute(
                select(Recipe.title).where(Recipe.id == int(ref))
            ).scalar_one_or_none()
            if title:
                return title
        elif isinstance(ref, str) and ref.strip():
            return ref.strip()
    return None


def _shopping_item_out(session: Session, row: ShoppingListItem) -> ShoppingListItemOut:
    """购物清单行 ORM → 响应模型（函数）。

    参数：
        session：数据库会话（解析来源菜名与致敏原）。
        row：清单行 ORM 实例。

    返回值：
        ShoppingListItemOut：清单条目响应。

    异常：
        无。
    """
    ingredient_name = row.name
    allergen_codes: list[str] = []
    if row.ingredient_id is not None:
        info = session.execute(
            select(Ingredient.name, Ingredient.allergen_codes).where(Ingredient.id == row.ingredient_id)
        ).first()
        if info is not None:
            ingredient_name, codes = info
            allergen_codes = list(codes or [])
    return ShoppingListItemOut(
        id=int(row.id),
        ingredient_id=int(row.ingredient_id) if row.ingredient_id is not None else None,
        ingredient_name=ingredient_name,
        quantity_note=row.category,
        from_recipe_name=_recipe_name_from_refs(session, row.source_recipe_ids),
        checked=bool(row.checked),
        allergen_codes=allergen_codes,
    )


@shopping_router.get("", response_model=ShoppingListOut, summary="购物清单列表")
def list_shopping_list(request: Request, session: Session = Depends(get_db)) -> ShoppingListOut:
    """购物清单列表端点（函数）。

    参数：
        request：FastAPI 请求对象。
        session：请求级数据库会话。

    返回值：
        ShoppingListOut：{items: [...]}（未勾选在前，按创建顺序）。

    异常：
        数据库异常向上抛出。
    """
    user = _resolve_user(session, request, None)
    rows = session.execute(
        select(ShoppingListItem)
        .where(ShoppingListItem.user_id == int(user.id))
        .order_by(ShoppingListItem.checked, ShoppingListItem.id)
    ).scalars().all()
    return ShoppingListOut(items=[_shopping_item_out(session, r) for r in rows])


@shopping_router.post("", status_code=201, response_model=ShoppingListCreateOut, summary="批量加入购物清单（同名合并去重）")
def add_shopping_items(
    payload: ShoppingListCreateRequest, request: Request, session: Session = Depends(get_db)
) -> ShoppingListCreateOut:
    """批量加入购物清单端点（函数）。

    说明：
        ingredient_id 相同视为同名条目：已存在则合并（quantity_note 追加/更新、
        来源菜谱引用追加），不重复建行；食材不存在 → 404。

    参数：
        payload：批量新增请求体。
        request：FastAPI 请求对象。
        session：请求级数据库会话。

    返回值：
        ShoppingListCreateOut：{added, merged}（201）。

    异常：
        HTTPException 404：任一食材不存在。
    """
    user = _resolve_user(session, request, payload.anonymous_id)

    # 预校验全部食材存在，避免半提交
    ingredient_ids = [item.ingredient_id for item in payload.items]
    found = set(
        session.execute(
            select(Ingredient.id).where(Ingredient.id.in_(ingredient_ids))
        ).scalars().all()
    )
    missing = sorted(set(ingredient_ids) - found)
    if missing:
        raise api_error(404, ERR_NOT_FOUND, "食材不存在", f"ingredient_id={missing[0]}")

    existing_rows = session.execute(
        select(ShoppingListItem).where(
            ShoppingListItem.user_id == int(user.id),
            ShoppingListItem.ingredient_id.in_(set(ingredient_ids)),
        )
    ).scalars().all()
    # 同 ingredient_id 可能有多行（历史遗留）：优先未勾选行，其次最新行
    existing: dict[int, ShoppingListItem] = {}
    for row in sorted(existing_rows, key=lambda r: r.id):
        existing[int(row.ingredient_id)] = row  # 后写覆盖 → 取最新
    for row in sorted(existing_rows, key=lambda r: r.id):
        if not row.checked:
            existing[int(row.ingredient_id)] = row  # 未勾选行优先

    added = 0
    merged = 0
    for item in payload.items:
        row = existing.get(item.ingredient_id)
        ref = _resolve_recipe_ref(session, item.from_recipe_name)
        if row is None:
            row = ShoppingListItem(
                user_id=int(user.id),
                ingredient_id=item.ingredient_id,
                name=session.get(Ingredient, item.ingredient_id).name,
                category=item.quantity_note,
                source_recipe_ids=[ref] if ref is not None else [],
                checked=False,
            )
            session.add(row)
            existing[item.ingredient_id] = row
            added += 1
        else:
            # 合并：quantity_note 追加（超 20 字则覆盖），来源引用去重追加
            if item.quantity_note:
                old = row.category
                if old and old != item.quantity_note and len(old) + 1 + len(item.quantity_note) <= 20:
                    row.category = f"{old}；{item.quantity_note}"
                else:
                    row.category = item.quantity_note
            if ref is not None and ref not in (row.source_recipe_ids or []):
                row.source_recipe_ids = list(row.source_recipe_ids or []) + [ref]
            merged += 1
    session.commit()
    return ShoppingListCreateOut(added=added, merged=merged)


def _load_owned_shopping_row_or_404(session: Session, user_id: int, item_id: int) -> ShoppingListItem:
    """加载本人购物清单行或抛 404（函数）。

    参数：
        session：数据库会话。
        user_id：当前用户 ID。
        item_id：清单行 ID。

    返回值：
        ShoppingListItem：清单行 ORM 实例。

    异常：
        HTTPException 404：行不存在或不属于本人。
    """
    row = session.execute(
        select(ShoppingListItem).where(ShoppingListItem.id == item_id)
    ).scalar_one_or_none()
    if row is None or int(row.user_id) != int(user_id):
        raise api_error(404, ERR_NOT_FOUND, "购物清单条目不存在", f"shopping_list_item_id={item_id}")
    return row


@shopping_router.patch("/{item_id}", response_model=ShoppingListItemOut, summary="更新勾选状态")
def patch_shopping_item(
    item_id: int,
    payload: ShoppingListCheckPatch,
    request: Request,
    session: Session = Depends(get_db),
) -> ShoppingListItemOut:
    """更新购物清单勾选状态端点（函数）。

    参数：
        item_id：清单行 ID。
        payload：{checked} 布尔状态。
        request：FastAPI 请求对象。
        session：请求级数据库会话。

    返回值：
        ShoppingListItemOut：更新后的清单条目。

    异常：
        HTTPException 404：行不存在/非本人。
    """
    user = _resolve_user(session, request, payload.anonymous_id)
    row = _load_owned_shopping_row_or_404(session, int(user.id), item_id)
    row.checked = payload.checked
    session.commit()
    return _shopping_item_out(session, row)


@shopping_router.delete("/{item_id}", status_code=204, summary="删除购物清单条目")
def delete_shopping_item(item_id: int, request: Request, session: Session = Depends(get_db)) -> Response:
    """删除购物清单条目端点（函数）。

    参数：
        item_id：清单行 ID。
        request：FastAPI 请求对象。
        session：请求级数据库会话。

    返回值：
        Response：204 无内容。

    异常：
        HTTPException 404：行不存在/非本人。
    """
    user = _resolve_user(session, request, None)
    row = _load_owned_shopping_row_or_404(session, int(user.id), item_id)
    session.delete(row)
    session.commit()
    return Response(status_code=204)


@shopping_router.post(
    "/{item_id}/to-inventory",
    status_code=201,
    response_model=ShoppingToInventoryOut,
    summary="清单转入库存（low 档）并删除清单行",
)
def shopping_to_inventory(
    item_id: int,
    payload: ShoppingToInventoryRequest,
    request: Request,
    session: Session = Depends(get_db),
) -> ShoppingToInventoryOut:
    """清单转入库存端点（函数）。

    说明：
        新建库存条目：quantity_level=low（DB little）、location=fridge（缺省）、
        expire_date 可带、source=manual；随后删除对应清单行。
        自定义条目（无 ingredient_id）无法转入 → 422。

    参数：
        item_id：清单行 ID。
        payload：{expire_date?}。
        request：FastAPI 请求对象。
        session：请求级数据库会话。

    返回值：
        ShoppingToInventoryOut：{inventory_item_id}（201）。

    异常：
        HTTPException 404：行不存在/非本人；422：自定义条目无法转入。
    """
    user = _resolve_user(session, request, payload.anonymous_id)
    row = _load_owned_shopping_row_or_404(session, int(user.id), item_id)
    if row.ingredient_id is None:
        raise api_error(422, ERR_BAD_REQUEST, "自定义条目（无关联食材）无法转入库存", f"item_id={row.id}")
    inv_row = InventoryItem(
        user_id=int(user.id),
        ingredient_id=int(row.ingredient_id),
        quantity_level="little",
        storage="fridge",
        purchase_date=date.today(),
        expiry_date=payload.expire_date,
        status="normal",
        source="manual",
    )
    session.add(inv_row)
    session.flush()
    inventory_item_id = int(inv_row.id)
    session.delete(row)
    session.commit()
    return ShoppingToInventoryOut(inventory_item_id=inventory_item_id)
