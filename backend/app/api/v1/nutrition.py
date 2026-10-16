"""营养分析路由模块。

职责：
    模块 G（tag=营养分析）：
    - GET  /v1/nutrition/summary：基于 meal_record 按日/按餐聚合（days ∈ {1,7,30}）；
    - POST /v1/nutrition/manual：手动补录（描述先过 RiskEngine input 闸门，命中拦截
      → 200 {blocked:true} 不落库；通过 → 写 meal_record(source=manual) → 201）。

口径：
    - 缺失营养的记录项进入 excluded（「XX 未纳入统计」），绝不按 0 计入合计：
      桶内某营养无任何有效数据时该键为 null（非 0）；
    - summary 固定携带免责声明（RL-6：估算值，不构成营养建议）；
    - 本模块不做任何「可食用/不能吃」类判定（RL-3）。
"""

from __future__ import annotations

from datetime import date, timedelta

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.v1.deps import ERR_VALIDATION, api_error, resolve_user
from app.core.db import get_db
from app.models import MealRecord, User
from app.safety.engine import get_risk_engine
from app.schemas.nutrition import (
    NUTRITION_DISCLAIMER,
    ManualMealCreatedOut,
    ManualMealRequest,
    MealBucketOut,
    NutritionSummaryOut,
    RiskBlockedOut,
    SummaryDayOut,
)

router = APIRouter(prefix="/nutrition", tags=["营养分析"])

# 合法窗口天数（任务口径：days ∈ {1,7,30}）
_VALID_DAYS = (1, 7, 30)

# 餐次键（响应结构恒包含四桶）
_MEAL_KEYS = ("breakfast", "lunch", "dinner", "snack")

# 营养字段映射：响应键 → (DB 列, 中文名)，用于聚合与 excluded 文案
_NUTRIENT_MAP = {
    "kcal": ("kcal", "热量"),
    "protein": ("protein_g", "蛋白质"),
    "fat": ("fat_g", "脂肪"),
    "carb": ("carbs_g", "碳水"),
    "sodium": ("sodium_mg", "钠"),
}


def _resolve_user(session: Session, request: Request, anon_id: str | None) -> User:
    """解析当前用户（函数）。

    说明：
        请求体 anonymous_id → X-Anonymous-Id 头 → 新建匿名用户（与 cooking/auth 一致）。

    参数：
        session：数据库会话。
        request：FastAPI 请求对象。
        anon_id：请求体携带的匿名 ID（可 None）。

    返回值：
        User：用户 ORM 实例。

    异常：
        SQLAlchemyError 向上抛出（全局异常处理器兜底）。
    """
    user = resolve_user(session, anon_id, request)
    session.commit()
    return user


def _record_nutrients(record: MealRecord) -> dict[str, float | None]:
    """读取单条 meal_record 的营养值（函数）。

    参数：
        record：meal_record ORM 实例。

    返回值：
        dict：{响应键: 值或 None}（kcal/protein/fat/carb/sodium）。

    异常：
        无（数值转换失败按 None 处理）。
    """
    values: dict[str, float | None] = {}
    for key, (column, _) in _NUTRIENT_MAP.items():
        raw = getattr(record, column)
        try:
            values[key] = float(raw) if raw is not None else None
        except (TypeError, ValueError):
            values[key] = None
    return values


def _build_bucket(records: list[MealRecord]) -> MealBucketOut:
    """聚合一组 meal_record 为营养桶（函数）。

    说明：
        - 全营养缺失的记录 → excluded 追加「{名称} 未纳入统计」，不参与任何合计；
        - 部分缺失 → 缺失营养追加「{名称} {营养名}未纳入统计」，其余正常合计；
        - 某营养无任何有效数据时该键为 None（绝不按 0 计入合计）。

    参数：
        records：meal_record ORM 实例列表。

    返回值：
        MealBucketOut：聚合后的营养桶。

    异常：
        无。
    """
    sums = {key: 0.0 for key in _NUTRIENT_MAP}
    has_value = {key: False for key in _NUTRIENT_MAP}
    excluded: list[str] = []

    for record in records:
        name = (record.custom_name or f"记录#{record.id}").strip()
        values = _record_nutrients(record)
        if all(v is None for v in values.values()):
            excluded.append(f"{name} 未纳入统计")
            continue
        for key, value in values.items():
            if value is None:
                excluded.append(f"{name} {_NUTRIENT_MAP[key][1]}未纳入统计")
            else:
                sums[key] += value
                has_value[key] = True

    return MealBucketOut(
        **{key: (round(sums[key], 1) if has_value[key] else None) for key in _NUTRIENT_MAP},
        excluded=excluded,
    )


def _merge_excluded(days: list[SummaryDayOut], totals: MealBucketOut) -> list[str]:
    """合并全窗口 excluded 列表（函数）。

    参数：
        days：逐日汇总列表。
        totals：合计桶。

    返回值：
        list[str]：按出现顺序去重后的说明列表。

    异常：
        无。
    """
    seen: set[str] = set()
    merged: list[str] = []
    for bucket in [d.meals[key] for d in days for key in _MEAL_KEYS] + [totals]:
        for item in bucket.excluded:
            if item not in seen:
                seen.add(item)
                merged.append(item)
    return merged


@router.get("/summary", response_model=NutritionSummaryOut, summary="营养汇总（按日/按餐聚合，缺失不按 0 计）")
def get_nutrition_summary(
    request: Request,
    days: int = Query(default=7, description="统计窗口天数（1/7/30）"),
    session: Session = Depends(get_db),
) -> NutritionSummaryOut:
    """营养汇总端点（函数）。

    说明：
        统计窗口为「含今天的近 N 天」；逐日输出四餐桶（breakfast/lunch/dinner/snack，
        键恒存在，无记录时营养键为 null）；totals 为窗口合计；缺失项进 excluded。

    参数：
        request：FastAPI 请求对象。
        days：窗口天数（仅允许 1/7/30，其它 422）。
        session：请求级数据库会话。

    返回值：
        NutritionSummaryOut：{days, totals, excluded, disclaimer}。

    异常：
        HTTPException 422：days 非法；数据库异常向上抛出。
    """
    user = _resolve_user(session, request, None)
    if days not in _VALID_DAYS:
        raise api_error(422, ERR_VALIDATION, "days 仅支持 1/7/30", f"days={days}")

    today = date.today()
    start = today - timedelta(days=days - 1)
    records = session.execute(
        select(MealRecord)
        .where(
            MealRecord.user_id == int(user.id),
            MealRecord.recorded_date >= start,
            MealRecord.recorded_date <= today,
        )
        .order_by(MealRecord.recorded_date, MealRecord.id)
    ).scalars().all()

    by_day: dict[date, dict[str, list[MealRecord]]] = {}
    for record in records:
        by_day.setdefault(record.recorded_date, {}).setdefault(record.meal_type, []).append(record)

    day_outs: list[SummaryDayOut] = []
    for offset in range(days):
        current = start + timedelta(days=offset)
        meals: dict[str, MealBucketOut] = {}
        for meal_key in _MEAL_KEYS:
            meals[meal_key] = _build_bucket(by_day.get(current, {}).get(meal_key, []))
        day_outs.append(SummaryDayOut(date=current.isoformat(), meals=meals))

    totals = _build_bucket(list(records))
    excluded = _merge_excluded(day_outs, totals)
    return NutritionSummaryOut(days=day_outs, totals=totals, excluded=excluded, disclaimer=NUTRITION_DISCLAIMER)


@router.post(
    "/manual",
    summary="手动补录饮食记录（描述先过风控闸门）",
    response_model=ManualMealCreatedOut | RiskBlockedOut,
)
def create_manual_meal(
    payload: ManualMealRequest, request: Request, session: Session = Depends(get_db)
) -> ManualMealCreatedOut | RiskBlockedOut:
    """手动补录饮食记录端点（函数）。

    说明：
        description 先过 RiskEngine input 闸门：
        - 命中拦截规则（block=true）→ 200 {blocked:true, rule_id, message}，不落库；
        - 通过 → 写 meal_record（source=manual，营养字段为空 → 汇总时进 excluded）→ 201。

    参数：
        payload：补录请求体（meal_type + description）。
        request：FastAPI 请求对象。
        session：请求级数据库会话。

    返回值：
        ManualMealCreatedOut（201）或 RiskBlockedOut（200）。

    异常：
        数据库异常向上抛出。
    """
    user = _resolve_user(session, request, payload.anonymous_id)

    engine = get_risk_engine()
    verdict = engine.scan("input", payload.description)
    if verdict.hit and verdict.block:
        message = engine.get_message(verdict.message_id) or {}
        return RiskBlockedOut(
            blocked=True,
            rule_id=verdict.rule_code,
            message=str(message.get("body") or "该描述涉及安全风险，请调整后重试。"),
        )

    record = MealRecord(
        user_id=int(user.id),
        recorded_date=date.today(),
        meal_type=payload.meal_type,
        recipe_id=None,
        custom_name=payload.description,
        servings=None,
        kcal=None,
        protein_g=None,
        fat_g=None,
        carbs_g=None,
        sodium_mg=None,
        source="manual",
    )
    session.add(record)
    session.commit()
    return ManualMealCreatedOut(
        id=int(record.id),
        meal_type=payload.meal_type,
        description=payload.description,
        recorded_date=record.recorded_date.isoformat(),
        blocked=False,
    )
