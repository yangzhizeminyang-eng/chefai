"""时令端点路由模块（首页「时令吃什么」入口数据源）。

职责：
    GET /v1/seasonal：返回当月（东八区）当季食材清单 + 以当季食材为主料的
    已发布菜谱列表，供前端 /seasonal 页面「当季食材标签 + 当季菜谱卡」消费。

口径说明：
    - 当季食材：静态「月份 → 当季食材名称白名单」映射（_SEASONAL_INGREDIENTS，
      12 个月，每月 15~25 种，华北/华东通用口径；每个名称已逐一与
      app/seed/ingredients.py 食材库种子核对存在，宁取库内稍欠佳名称也不用
      库外名称）。静态白名单为产品口径示例，阶段二可迁移 DB season_tags；
    - 当季菜谱：主料（recipe_ingredient.amount_type='main'）命中当季白名单的
      published 菜谱，经同款 SafetyProfile（家庭档案过敏原/忌口/特殊人群 +
      user_skill_profile 设备与难度上限）+ hard_filter 布尔硬过滤（🔴 时令
      推荐同样不绕过风控），按 (time_minutes, difficulty, recipe_id) 升序取 ≤8；
    - 食材查询对齐 home.py 口径（按名称 IN 匹配，无额外状态过滤）。

降级约定（🔴 对齐 home.py）：
    任何子项查询失败（含数据库异常）一律降级为空值（[]），HTTP 恒 200；
    月份无映射 / 白名单未命中种子时对应子项直接空数组返回。

身份约定（沿用 recommend.py 惯例）：
    GET 请求无请求体，resolve_existing_user_id(session, None, request) 从
    X-Anonymous-Id 请求头只读解析既有用户（不创建用户行）；无头/无档案时
    按空档案处理（hard_filter 各维度空集不生效）。

合规（RL-3）：
    当季信息仅为食材供应参考，不代表食材品质或营养优劣；rank_reasons 只
    描述食材构成与耗时，绝不出现「更营养 / 养生 / 滋补」等功效表述。
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ability.ranking import hard_filter
from app.api.v1.deps import difficulty_label, resolve_existing_user_id
from app.core.db import get_db
from app.core.logging import get_logger
from app.graph.runner import load_profile_from_db
from app.models import Ingredient, Recipe, RecipeIngredient, UserSkillProfile
from app.safety import SafetyProfile
from app.schemas.recommend import RecommendResultItem

router = APIRouter(prefix="/seasonal", tags=["时令"])

logger = get_logger(__name__)

# 当季菜谱返回上限（道数）：spec「按耗时升序取 ≤ 8 道」
_MAX_RESULTS = 8

# 当季食材名称白名单（按公历月份，华北/华东通用口径；产品口径示例，
# 阶段二可迁移 DB season_tags）。所有名称均已与 app/seed/ingredients.py
# 食材库种子逐一核对存在（如「竹笋」而非「春笋」、「花生米」而非「花生」、
# 「柿饼」而非「柿子」、「西兰花」而非「菜花」——以库内实际名称为准）。
_SEASONAL_INGREDIENTS: dict[int, list[str]] = {
    1: [
        "白萝卜", "大白菜", "冬笋", "橙子", "雪梨", "荸荠", "菠菜", "油菜", "山药", "莲藕",
        "红薯", "芋头", "卷心菜", "娃娃菜", "茼蒿", "香菇", "金针菇", "杏鲍菇", "草鱼", "带鱼",
        "猪排骨", "鸡腿", "心里美萝卜", "青萝卜", "甘蔗",
    ],
    2: [
        "白萝卜", "大白菜", "油菜", "菠菜", "芹菜", "冬笋", "山药", "莲藕", "红薯", "荸荠",
        "雪梨", "橙子", "韭菜", "卷心菜", "芋头", "鲈鱼", "草鱼", "茼蒿", "娃娃菜", "心里美萝卜",
    ],
    3: [
        "荠菜", "香椿", "韭菜", "菠菜", "油菜", "莴笋", "竹笋", "豌豆苗", "芦笋", "芹菜",
        "白萝卜", "莲藕", "荸荠", "草莓", "鲈鱼", "草鱼", "茼蒿", "蚕豆", "生菜", "小白菜",
    ],
    4: [
        "竹笋", "蚕豆", "豌豆苗", "莴笋", "菠菜", "韭菜", "芦笋", "香椿", "荠菜", "油菜",
        "蒜苗", "鲈鱼", "草鱼", "蛏子", "菠萝", "草莓", "青椒", "生菜", "小白菜", "花蛤",
    ],
    5: [
        "蚕豆", "黄瓜", "苋菜", "空心菜", "莴笋", "蒜苔", "樱桃", "枇杷", "草莓", "西葫芦",
        "卷心菜", "生菜", "小白菜", "鲈鱼", "四季豆", "豌豆苗", "油菜", "茼蒿", "花蛤", "彩椒",
    ],
    6: [
        "杨梅", "苋菜", "黄瓜", "空心菜", "冬瓜", "丝瓜", "苦瓜", "茄子", "豇豆", "毛豆",
        "荔枝", "甜玉米", "糯玉米", "藕带", "蒜苔", "鲈鱼", "番茄", "西葫芦", "桃子", "四季豆",
    ],
    7: [
        "西瓜", "桃子", "冬瓜", "丝瓜", "苦瓜", "黄瓜", "茄子", "豇豆", "空心菜", "苋菜",
        "毛豆", "甜玉米", "糯玉米", "番茄", "青椒", "秋葵", "龙眼", "蛏子", "荔枝", "南瓜",
    ],
    8: [
        "毛豆", "冬瓜", "丝瓜", "苦瓜", "黄瓜", "茄子", "豇豆", "空心菜", "苋菜", "西瓜",
        "桃子", "葡萄", "甜玉米", "糯玉米", "番茄", "青椒", "秋葵", "莲藕", "龙眼", "南瓜",
    ],
    9: [
        "菱角", "莲子", "莲藕", "梭子蟹", "大闸蟹", "甜玉米", "芋头", "山药", "冬瓜", "南瓜",
        "苋菜", "空心菜", "葡萄", "猕猴桃", "雪梨", "花生米", "毛豆", "秋葵", "丝瓜", "苦瓜",
        "蛏子", "带鱼", "草鱼", "鲈鱼",
    ],
    10: [
        "南瓜", "山药", "莲藕", "大闸蟹", "梭子蟹", "柿饼", "白萝卜", "冬瓜", "芋头", "红薯",
        "西兰花", "菠菜", "雪梨", "带鱼", "草鱼", "甜玉米", "花生米", "冬枣", "山楂", "茼蒿",
        "莴笋", "香菇", "芥蓝", "佛手瓜",
    ],
    11: [
        "大白菜", "卷心菜", "白萝卜", "胡萝卜", "红薯", "山药", "莲藕", "芋头", "菠菜", "油菜",
        "茼蒿", "莴笋", "香菇", "金针菇", "杏鲍菇", "平菇", "带鱼", "草鱼", "鲫鱼", "橙子",
        "苹果", "冬枣", "山楂", "荸荠",
    ],
    12: [
        "大白菜", "白萝卜", "胡萝卜", "红薯", "山药", "莲藕", "芋头", "卷心菜", "娃娃菜", "菠菜",
        "油菜", "茼蒿", "香菇", "金针菇", "杏鲍菇", "平菇", "带鱼", "草鱼", "鲫鱼", "橙子",
        "苹果", "雪梨", "荸荠", "冬笋",
    ],
}


class SeasonalIngredient(BaseModel):
    """当季食材条目（模型类）。

    说明：
        时令页食材标签消费的最小结构（id/name/category）。

    属性：
        id：食材 ID。
        name：食材名称（库内主名）。
        category：食材 10 分类编码（veg/meat/seafood/…）。
    """

    id: int
    name: str
    category: str


class SeasonalResponse(BaseModel):
    """时令端点响应体（模型类）。

    说明：
        recipes 复用 RecommendResultItem 条目结构（含并行任务追加的
        cover_image_url 字段，本模块只 import 不编辑该 schema）。

    属性：
        month：当月月份（1~12，东八区）。
        ingredients：当月当季食材列表（按白名单顺序；查询失败/未命中为空数组）。
        recipes：当季菜谱列表（≤8 条，硬过滤后按耗时升序；失败/未命中为空数组）。
    """

    month: int
    ingredients: list[SeasonalIngredient] = Field(default_factory=list)
    recipes: list[RecommendResultItem] = Field(default_factory=list)


def _current_month() -> int:
    """取当前业务月份（函数）。

    说明：
        东八区口径（中国无夏令时，对齐 home.py 的业务日惯例）。

    参数：
        无。

    返回值：
        int：月份 1~12。

    异常：
        无。
    """
    return datetime.now(timezone(timedelta(hours=8))).month


def _load_seasonal_ingredients(session: Session, names: list[str]) -> list[SeasonalIngredient]:
    """按白名单名称查询当季食材条目（函数）。

    说明：
        查询条件对齐 home.py 查 Ingredient 的口径（按名称 IN 匹配，无额外
        状态过滤）；返回顺序按白名单顺序（保证前端展示的时令次序稳定）。

    参数：
        session：数据库会话。
        names：当月白名单食材名称列表。

    返回值：
        list[SeasonalIngredient]：命中的食材条目（白名单顺序）。

    异常：
        查询异常向上抛出（由端点统一降级）。
    """
    rows = session.execute(
        select(Ingredient.id, Ingredient.name, Ingredient.category).where(
            Ingredient.name.in_(names)
        )
    ).all()
    by_name = {str(name): (int(row_id), str(name), str(category)) for row_id, name, category in rows}
    return [SeasonalIngredient(id=by_name[n][0], name=by_name[n][1], category=by_name[n][2]) for n in names if n in by_name]


def _load_seasonal_recipe_ids(session: Session, names: list[str]) -> dict[int, list[str]]:
    """查询主料命中当季白名单的菜谱及其命中食材名（函数）。

    说明：
        口径：recipe_ingredient.amount_type='main'（主料）且食材名命中白名单；
        一道菜命中多个当季食材时合并（命中名按白名单顺序排列）。

    参数：
        session：数据库会话。
        names：当月白名单食材名称列表。

    返回值：
        dict[int, list[str]]：{recipe_id: [命中的当季食材名, ...]}。

    异常：
        查询异常向上抛出（由端点统一降级）。
    """
    rank = {name: idx for idx, name in enumerate(names)}
    rows = session.execute(
        select(RecipeIngredient.recipe_id, Ingredient.name)
        .join(Ingredient, RecipeIngredient.ingredient_id == Ingredient.id)
        .where(RecipeIngredient.amount_type == "main", Ingredient.name.in_(names))
    ).all()
    hits: dict[int, list[str]] = {}
    for recipe_id, name in rows:
        rid = int(recipe_id)
        bucket = hits.setdefault(rid, [])
        if name not in bucket:
            bucket.append(str(name))
    return {rid: sorted(bucket, key=lambda n: rank.get(n, 0)) for rid, bucket in hits.items()}


def _load_candidates(session: Session, recipe_ids: dict[int, list[str]]) -> list[dict]:
    """查询已发布菜谱构造硬过滤候选（函数）。

    说明：
        字段口径对齐 day_menu._load_candidates（id/title/time_minutes/difficulty/
        calories_kcal/equipment/allergen_codes/ingredient_allergen_codes/
        cover_image_url/source_label）；候选额外携带 seasonal_names（主料命中的
        当季食材名，供 covered_ingredients 与 rank_reasons 消费）。

    参数：
        session：数据库会话。
        recipe_ids：{recipe_id: 命中当季食材名列表}。

    返回值：
        list[dict]：候选字典列表（含 recipe_id/equipment 键，hard_filter 可直接消费）。

    异常：
        查询异常向上抛出（由端点统一降级）。
    """
    rows = session.execute(
        select(
            Recipe.id,
            Recipe.title,
            Recipe.time_minutes,
            Recipe.difficulty,
            Recipe.calories_kcal,
            Recipe.equipment,
            Recipe.allergen_codes,
            Recipe.ingredient_allergen_codes,
            Recipe.cover_image_url,
            Recipe.source_label,
        ).where(Recipe.status == "published", Recipe.id.in_(list(recipe_ids)))
    ).all()
    return [
        {
            "recipe_id": int(row.id),
            "title": str(row.title or ""),
            "time_minutes": row.time_minutes,
            "difficulty": int(row.difficulty) if row.difficulty is not None else None,
            "calories_kcal": row.calories_kcal,
            "equipment": list(row.equipment or []),
            "allergen_codes": list(row.allergen_codes or []),
            "ingredient_allergen_codes": list(row.ingredient_allergen_codes or []),
            "cover_image_url": row.cover_image_url,
            "source_label": str(row.source_label or ""),
            "seasonal_names": list(recipe_ids.get(int(row.id)) or []),
        }
        for row in rows
    ]


def _load_difficulty_cap(session: Session, user_id: int) -> int | None:
    """读取用户难度上限（函数）。

    说明：
        load_profile_from_db 仅合并家庭档案三段与设备清单（不含难度上限），
        难度上限存于 user_skill_profile.difficulty_cap（一人一份）——单独
        只读查询，供 hard_filter 难度维度布尔过滤（同 day_menu 惯例）。

    参数：
        session：数据库会话。
        user_id：用户数据库 ID。

    返回值：
        int | None：难度上限（1~5）；无档案/查询异常返回 None（难度维度不生效）。

    异常：
        不抛出（查询异常告警后返回 None，不阻断响应）。
    """
    try:
        return session.execute(
            select(UserSkillProfile.difficulty_cap).where(UserSkillProfile.user_id == int(user_id))
        ).scalar_one_or_none()
    except Exception as exc:  # noqa: BLE001 —— 难度上限读取失败按「未设置」处理
        logger.warning("seasonal load difficulty cap failed (user_id=%s): %s", user_id, exc)
        return None


def _build_rank_reasons(cand: dict) -> list[str]:
    """构造单条当季菜谱的排序理由（函数）。

    说明：
        至少 1 条可解释理由；只描述食材构成与耗时（RL-3：不做可食性/优劣
        判定），绝不出现「更营养 / 养生 / 滋补」等功效表述。

    参数：
        cand：候选字典（消费 seasonal_names/time_minutes）。

    返回值：
        list[str]：理由文案列表（≥1 条）。

    异常：
        无。
    """
    reasons: list[str] = []
    seasonal_names = list(cand.get("seasonal_names") or [])
    if seasonal_names:
        reasons.append(f"当季食材 {'、'.join(seasonal_names[:3])} 做成的菜")
    time_minutes = int(cand.get("time_minutes") or 0)
    if time_minutes > 0:
        reasons.append(f"约 {time_minutes} 分钟即可上桌")
    if not reasons:
        reasons.append("用当季食材烹制")
    return reasons


def _load_seasonal_recipes(session: Session, request: Request, names: list[str]) -> list[RecommendResultItem]:
    """加载当季菜谱结果列表（函数）。

    说明：
        全链路：主料命中查询 → published 候选 → 家庭档案 + user_skill_profile
        构建 SafetyProfile → hard_filter 布尔硬过滤（🔴 不绕过）→ 按
        (time_minutes or 9999, difficulty, recipe_id) 升序取 ≤8 → 组装
        RecommendResultItem 条目（match_level 固定 can_cook_now，含
        cover_image_url；若 schema 尚未落地该字段，Pydantic extra=ignore
        静默忽略，不报错）。

    参数：
        session：数据库会话。
        request：FastAPI 请求对象（解析 X-Anonymous-Id 头）。
        names：当月白名单食材名称列表。

    返回值：
        list[RecommendResultItem]：当季菜谱结果（≤8 条）。

    异常：
        查询/组装异常向上抛出（由端点统一降级）。
    """
    recipe_ids = _load_seasonal_recipe_ids(session, names)
    if not recipe_ids:
        return []
    candidates = _load_candidates(session, recipe_ids)

    # 安全档案：家庭档案三段（过敏原/忌口/特殊人群）+ 本人设备与难度上限
    #（只读解析既有用户，无头/无档案时按空档案处理——硬过滤各维度空集不生效）
    user_id = resolve_existing_user_id(session, None, request)
    db_profile: dict = {}
    difficulty_cap: int | None = None
    if user_id:
        db_profile = load_profile_from_db(session, user_id)
        difficulty_cap = _load_difficulty_cap(session, user_id)
    profile = SafetyProfile(
        user_allergen_codes=[str(c) for c in (db_profile.get("allergen_codes") or [])],
        dietary_restrictions=[str(c) for c in (db_profile.get("dietary_restrictions") or [])],
        special_population=[str(c) for c in (db_profile.get("special_population") or [])],
        difficulty_cap=difficulty_cap,
        equipment=[str(e) for e in (db_profile.get("equipment") or [])],
    )

    # 🔴 布尔硬过滤（过敏原/忌口/难度上限/设备），时令推荐同样不绕过风控
    filtered, _counts = hard_filter(session, candidates, profile)

    ordered = sorted(
        filtered,
        key=lambda c: (
            int(c.get("time_minutes") or 9999),
            int(c.get("difficulty") or 0),
            int(c.get("recipe_id") or 0),
        ),
    )[:_MAX_RESULTS]

    items: list[RecommendResultItem] = []
    for idx, cand in enumerate(ordered):
        allergens = sorted(
            set(list(cand.get("allergen_codes") or []) + list(cand.get("ingredient_allergen_codes") or []))
        )
        items.append(
            RecommendResultItem.model_validate(
                {
                    "recipe_id": int(cand["recipe_id"]),
                    "title": str(cand.get("title") or ""),
                    "match_level": "can_cook_now",
                    "covered_ingredients": list(cand.get("seasonal_names") or []),
                    "missing_ingredients": [],
                    "time_minutes": int(cand["time_minutes"]) if cand.get("time_minutes") else None,
                    "difficulty": difficulty_label(cand.get("difficulty")),
                    "calories_kcal": cand.get("calories_kcal"),
                    "allergens": allergens,
                    "required_equipment": list(cand.get("equipment") or []),
                    "rank_score": round(1.0 - idx * 0.01, 4),
                    "rank_reasons": _build_rank_reasons(cand),
                    "source": str(cand.get("source_label") or "") or None,
                    "cover_image_url": cand.get("cover_image_url"),
                }
            )
        )
    return items


@router.get("", response_model=SeasonalResponse, summary="时令（当月当季食材 + 用当季食材做的菜谱）")
def get_seasonal(
    request: Request,
    session: Session = Depends(get_db),
) -> SeasonalResponse:
    """时令端点（函数）。

    说明：
        两个子项（食材/菜谱）独立 try/except 降级：失败子项记 warning 日志并
        取空数组，整页恒 200；月份无映射（names 为空）时直接空返回。

    参数：
        request：FastAPI 请求对象（读 X-Anonymous-Id 头）。
        session：请求级数据库会话。

    返回值：
        SeasonalResponse：{month, ingredients, recipes}（子项失败降级为空数组）。

    异常：
        不向外抛业务异常（子项级降级；致命异常由全局处理器兜底）。
    """
    month = _current_month()
    names = list(_SEASONAL_INGREDIENTS.get(month, []))

    ingredients: list[SeasonalIngredient] = []
    recipes: list[RecommendResultItem] = []
    if names:
        # 子项 1：当季食材（失败降级空数组）
        try:
            ingredients = _load_seasonal_ingredients(session, names)
        except Exception as exc:  # noqa: BLE001 —— 食材查询失败降级空数组
            logger.warning("seasonal load ingredients failed: %s", exc)
            ingredients = []

        # 子项 2：当季菜谱（失败降级空数组）
        try:
            recipes = _load_seasonal_recipes(session, request, names)
        except Exception as exc:  # noqa: BLE001 —— 菜谱链路失败降级空数组
            logger.warning("seasonal load recipes failed: %s", exc)
            recipes = []

    return SeasonalResponse(month=month, ingredients=ingredients, recipes=recipes)
