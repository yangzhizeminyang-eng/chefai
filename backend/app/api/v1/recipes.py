"""菜谱路由模块。

职责：
    GET /v1/recipes?q=&page=&page_size=：菜谱列表搜索（q 模糊匹配菜名 + 食材名/别名，
    仅 published，分页返回 {items, total}；查询类接口豁免幂等，错误走统一 api_error）；
    GET /v1/recipes/{id}：菜谱详情（servings 缩放重算用量）；
    GET /v1/recipes/{id}/nutrition：营养估算（缺失标注 excluded_items，不按 0 计）；
    POST /v1/recipes/{id}/feedback：菜谱反馈（like/dislike/cooked，写 recipe_feedback，
    E.9 反馈立即生效——排序侧由 ability.ranking.load_feedback_penalty 消费）。
    响应结构对齐前端 types.ts RecipeDetail / NutritionResult / RecipeSearchResponse。
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy import case, func, or_, select
from sqlalchemy.orm import Session

from app.ability.nutrition import estimate_recipe_nutrition, resolve_per_serving_kcal
from app.api.v1.deps import (
    ERR_NOT_FOUND,
    api_error,
    difficulty_label,
    format_amount,
    get_or_create_user,
    resolve_anonymous_id,
)
from app.core.db import get_db
from app.models import Ingredient, IngredientAlias, Recipe, RecipeFeedback, RecipeIngredient, RecipeStep
from app.schemas.recipes import NutritionOut, NutritionTotalOut, RecipeIngredientItem, RecipeStepItem

router = APIRouter(prefix="/recipes", tags=["recipes"])

# 份数合法范围（缩放系数 = servings / 菜谱基准份数）
_MIN_SERVINGS = 1
_MAX_SERVINGS = 50


def _load_recipe_or_404(session: Session, recipe_id: int) -> Recipe:
    """加载已发布菜谱或抛 404（函数）。

    参数：
        session：数据库会话。
        recipe_id：菜谱 ID。

    返回值：
        Recipe：菜谱 ORM 实例。

    异常：
        HTTPException 404：菜谱不存在或未发布。
    """
    recipe = session.execute(select(Recipe).where(Recipe.id == recipe_id)).scalar_one_or_none()
    if recipe is None or recipe.status != "published":
        raise api_error(404, ERR_NOT_FOUND, "菜谱不存在或未发布", f"recipe_id={recipe_id}")
    return recipe


def _build_ingredient_items(
    rows: list, allergen_map: dict[int, list[str]], ratio: float
) -> list[RecipeIngredientItem]:
    """构造食材行列表（函数）。

    说明：
        用量按 ratio 缩放后生成量化描述串；同时保留缩放后的原始数值字段。

    参数：
        rows：(RecipeIngredient, 食材名) 元组列表。
        allergen_map：{ingredient_id: 致敏原列表}。
        ratio：缩放系数（servings / 基准份数）。

    返回值：
        list[RecipeIngredientItem]：食材行列表（主料在前，按 sort_order 稳定排序）。

    异常：
        无（数值异常按原值处理）。
    """

    def _scale(value):
        """缩放单个用量值（内部函数）。

        参数：
            value：原始用量值（可 None）。

        返回值：
            float | None：缩放后用量（保留两位小数）。

        异常：
            无。
        """
        return round(float(value) * ratio, 2) if value is not None else None

    items: list[RecipeIngredientItem] = []
    for ri, ing_name in rows:
        ing_allergens = allergen_map.get(int(ri.ingredient_id), [])
        items.append(
            RecipeIngredientItem(
                name=ing_name,
                amount=format_amount(
                    _scale(ri.amount_value), _scale(ri.amount_min), _scale(ri.amount_max), ri.amount_unit
                ),
                is_main=(ri.amount_type == "main"),
                allergens=list(ing_allergens),
                substitute=None,
                amount_type=ri.amount_type,
                amount_value=_scale(ri.amount_value),
                amount_min=_scale(ri.amount_min),
                amount_max=_scale(ri.amount_max),
                amount_unit=ri.amount_unit,
                amount_note=ri.amount_note,
            )
        )
    return items


@router.get("", summary="菜谱搜索（q 模糊匹配菜名与食材名/别名，仅 published，分页）")
def search_recipes(
    q: str | None = Query(default=None, max_length=50, description="搜索关键词（菜名/食材名/别名）"),
    page: int = Query(default=1, ge=1, description="页码（从 1 起）"),
    page_size: int = Query(default=10, ge=1, le=50, description="每页条数（1~50）"),
    session: Session = Depends(get_db),
) -> dict:
    """菜谱列表搜索端点（函数，DEF-02 后端配套）。

    说明：
        q 非空时：菜名 ILIKE 模糊匹配，或菜谱引用了名称/别名命中 q 的食材
        （「可含别名」口径）；菜名直接命中的条目排在食材命中的前面；
        q 为空/空白时返回全部已发布菜谱（分页）。
        查询类接口豁免幂等（无副作用，不做 request_id 缓存）；
        分页参数非法由 FastAPI 校验出 422（统一错误体结构）。

    参数：
        q：搜索关键词（可缺省）。
        page：页码（≥1，默认 1）。
        page_size：每页条数（1~50，默认 10）。
        session：请求级数据库会话。

    返回值：
        dict：{"items": [{id, title, difficulty, time_minutes, calories_kcal}],
        "total": 总命中数, "page": 页码, "page_size": 每页条数}。
        difficulty 为前端三档文案（easy/medium/hard）。

    异常：
        HTTPException 422：分页参数不合法（统一错误体）。
    """
    keyword = (q or "").strip()
    stmt = select(Recipe).where(Recipe.status == "published")
    count_stmt = select(func.count(Recipe.id)).where(Recipe.status == "published")
    if keyword:
        pattern = f"%{keyword}%"
        # 食材名或别名命中 q 的菜谱集合（「可含别名」口径）
        ing_match_subq = (
            select(RecipeIngredient.recipe_id)
            .join(Ingredient, Ingredient.id == RecipeIngredient.ingredient_id)
            .where(
                or_(
                    Ingredient.name.ilike(pattern),
                    Ingredient.id.in_(
                        select(IngredientAlias.ingredient_id).where(IngredientAlias.alias.ilike(pattern))
                    ),
                )
            )
        )
        condition = or_(Recipe.title.ilike(pattern), Recipe.id.in_(ing_match_subq))
        stmt = stmt.where(condition)
        count_stmt = count_stmt.where(condition)
        # 菜名直接命中优先于仅食材命中（同组按 id 升序稳定输出）
        stmt = stmt.order_by(case((Recipe.title.ilike(pattern), 0), else_=1), Recipe.id)
    else:
        stmt = stmt.order_by(Recipe.id)

    total = int(session.execute(count_stmt).scalar_one() or 0)
    rows = session.execute(
        stmt.offset((page - 1) * page_size).limit(page_size)
    ).scalars().all()
    items = [
        {
            "id": int(recipe.id),
            "title": recipe.title,
            "difficulty": difficulty_label(recipe.difficulty),
            "time_minutes": recipe.time_minutes,
            "calories_kcal": recipe.calories_kcal,
        }
        for recipe in rows
    ]
    return {"items": items, "total": total, "page": page, "page_size": page_size}


@router.get("/{recipe_id}", summary="菜谱详情（支持 servings 缩放重算）")
def get_recipe_detail(
    recipe_id: int,
    servings: int | None = Query(default=None, ge=_MIN_SERVINGS, le=_MAX_SERVINGS),
    session: Session = Depends(get_db),
) -> dict:
    """菜谱详情端点（函数）。

    说明：
        servings 缺省用菜谱基准份数；用量按 servings/base 比例线性缩放（营养另行估算）；
        tips 文本按行/分号拆分为列表（前端 tips: string[]）。

    参数：
        recipe_id：菜谱 ID。
        servings：目标份数（1~50，可缺省）。
        session：请求级数据库会话。

    返回值：
        dict：RecipeDetailResponse 结构（含附加 ingredients 原始量化字段）。

    异常：
        HTTPException 404：菜谱不存在或未发布。
    """
    recipe = _load_recipe_or_404(session, recipe_id)
    base_servings = int(recipe.servings or 2)
    target_servings = int(servings or base_servings)
    ratio = target_servings / base_servings

    # 食材行（主料/辅料/调味分组输出）+ 致敏原映射
    rows = session.execute(
        select(RecipeIngredient, Ingredient.name)
        .join(Ingredient, Ingredient.id == RecipeIngredient.ingredient_id)
        .where(RecipeIngredient.recipe_id == recipe_id)
        .order_by(RecipeIngredient.sort_order, RecipeIngredient.id)
    ).all()
    allergen_map: dict[int, list[str]] = {}
    ing_ids = [int(ri.ingredient_id) for ri, _ in rows]
    if ing_ids:
        for ing_id, codes in session.execute(
            select(Ingredient.id, Ingredient.allergen_codes).where(Ingredient.id.in_(ing_ids))
        ).all():
            allergen_map[int(ing_id)] = list(codes or [])

    all_items = _build_ingredient_items(rows, allergen_map, ratio)
    main_items = [i for i in all_items if i.amount_type == "main"]
    side_items = [i for i in all_items if i.amount_type == "minor"]
    seasoning_items = [i for i in all_items if i.amount_type == "seasoning"]

    # 步骤（按 step_no 升序）
    steps = session.execute(
        select(RecipeStep)
        .where(RecipeStep.recipe_id == recipe_id)
        .order_by(RecipeStep.step_no)
    ).scalars().all()
    step_items = [
        RecipeStepItem(
            no=int(step.step_no),
            description=step.description,
            duration_sec=int(step.duration_seconds or 0),
            tips=step.key_point,
            rescue=step.failure_tips,
            amount_hint=step.amount_hint,
            step_no=int(step.step_no),
            duration_seconds=int(step.duration_seconds or 0),
            key_point=step.key_point,
            failure_tips=step.failure_tips,
        )
        for step in steps
    ]

    # 小贴士文本拆行（DB tips 为 Text；空值安全）
    tips_list = [seg.strip() for seg in (recipe.tips or "").replace("；", "\n").splitlines() if seg.strip()]

    return {
        "id": int(recipe.id),
        "title": recipe.title,
        "description": None,
        "difficulty": difficulty_label(recipe.difficulty),
        "time_minutes": recipe.time_minutes,
        "servings": target_servings,
        # 🔴 每份口径（M5 收口）：DB calories_kcal 存储语义为全菜总量（seed 与 HowToCook
        # 语料一致），头部「X kcal/份」按基准份数折算，与 /nutrition 的每份 kcal 同源相等。
        "calories_kcal": round(float(recipe.calories_kcal) / base_servings, 1) if recipe.calories_kcal is not None else None,
        "allergen_codes": list(recipe.allergen_codes or []),
        "equipment": list(recipe.equipment or []),
        "main_ingredients": [i.model_dump() for i in main_items],
        "side_ingredients": [i.model_dump() for i in side_items],
        "seasoning_ingredients": [i.model_dump() for i in seasoning_items],
        "steps": [s.model_dump() for s in step_items],
        "substitutes": [str(x) for x in (recipe.substitutes or [])],
        "tips": tips_list,
        "source_label": recipe.source_label,
        "ingredients": [i.model_dump() for i in all_items],
    }


@router.get("/{recipe_id}/nutrition", response_model=NutritionOut, summary="营养估算（每份口径；缺失标注，不按 0 计）")
def get_recipe_nutrition(
    recipe_id: int,
    servings: int | None = Query(default=None, ge=_MIN_SERVINGS, le=_MAX_SERVINGS),
    session: Session = Depends(get_db),
) -> NutritionOut:
    """营养估算端点（函数）。

    说明：
        唯一口径 = 每份（M5/R4/S9 修复）：kcal 走 resolve_per_serving_kcal
        （DB calories_kcal 优先 → LLM 回退校验落定 → 食材聚合确定性回退），
        其余营养素沿用食材聚合每份值；total 为「每份 × 份数」同源换算，
        保证前端头部 kcal/份 与营养估算区口径一致、多次请求结果稳定。
        无营养数据食材列入 excluded_items 标「未纳入统计」（不按 0 计）。

    参数：
        recipe_id：菜谱 ID。
        servings：份数（缺省用菜谱基准份数）。
        session：请求级数据库会话。

    返回值：
        NutritionOut：每份营养 + 按份数合计 + 数据来源标注。

    异常：
        HTTPException 404：菜谱不存在或未发布。
    """
    recipe = _load_recipe_or_404(session, recipe_id)
    target_servings = int(servings or recipe.servings or 2)
    estimate = estimate_recipe_nutrition(session, recipe_id, target_servings)
    per = estimate.get("per_serving") or {}
    # 每份 kcal 唯一口径解析（DB → LLM 校验落定 → 确定性聚合）
    kcal, kcal_source = resolve_per_serving_kcal(session, recipe, target_servings)
    # 合计 = 每份 × 份数（同源换算：与每份值严格闭环，前端「按 N 份合计」展示一致）
    total = NutritionTotalOut(
        kcal=round(kcal * target_servings, 1) if kcal is not None else None,
        protein=round(float(per.get("protein_g") or 0) * target_servings, 1) if per.get("protein_g") is not None else None,
        fat=round(float(per.get("fat_g") or 0) * target_servings, 1) if per.get("fat_g") is not None else None,
        carbs=round(float(per.get("carbs_g") or 0) * target_servings, 1) if per.get("carbs_g") is not None else None,
        sodium=round(float(per.get("sodium_mg") or 0) * target_servings, 1) if per.get("sodium_mg") is not None else None,
    )
    return NutritionOut(
        kcal=kcal,
        protein=per.get("protein_g"),
        fat=per.get("fat_g"),
        carbs=per.get("carbs_g"),
        sodium=per.get("sodium_mg"),
        per_serving=target_servings,
        total=total,
        kcal_source=kcal_source,
        excluded_items=list(estimate.get("excluded_items") or []),
        estimate_note=estimate.get("estimate_note") or "估算值，非实测值，误差约 ±15%",
    )


class RecipeFeedbackIn(BaseModel):
    """菜谱反馈请求体（模型类）。

    说明：
        action 为反馈类型（like 赞 / dislike 踩 / cooked 做过）；rating 仅 1~5；
        comment 为可选文字反馈（recipe_feedback 模型无 comment 列，入库到 tags JSONB）。

    属性：
        action：反馈类型（like / dislike / cooked）。
        rating：评分 1~5（可缺省）。
        comment：文字反馈（可缺省，≤200 字）。
    """

    action: str = Field(pattern="^(like|dislike|cooked)$", description="反馈类型")
    rating: int | None = Field(default=None, ge=1, le=5, description="评分 1~5（可缺省）")
    comment: str | None = Field(default=None, max_length=200, description="文字反馈（可缺省）")


@router.post(
    "/{recipe_id}/feedback",
    status_code=201,
    summary="菜谱反馈（like/dislike/cooked，E.9 反馈立即生效）",
)
def post_recipe_feedback(
    recipe_id: int,
    payload: RecipeFeedbackIn,
    request: Request,
    session: Session = Depends(get_db),
) -> dict:
    """菜谱反馈端点（函数）。

    说明：
        写入 recipe_feedback 表（feedback_type=action，rating 1~5，comment 入
        tags JSONB）；用户按 X-Anonymous-Id → user 现有惯例解析（缺省自动建
        匿名用户）。反馈立即生效：ranking.load_feedback_penalty 会把该用户的
        dislike 菜谱在推荐排序中扣 0.5 分（subgraphs/recommend.py 接线由后续
        graph 阶段完成）。允许重复提交（模型无唯一约束，多条反馈均入库）。

    参数：
        recipe_id：菜谱 ID。
        payload：反馈请求体（action 必填，rating/comment 可选）。
        request：FastAPI 请求对象（解析 X-Anonymous-Id）。
        session：请求级数据库会话。

    返回值：
        dict：201 {id, recipe_id, feedback_type, rating, comment}。

    异常：
        HTTPException 404：菜谱不存在或未发布；422：action/rating 不合法。
    """
    recipe = _load_recipe_or_404(session, recipe_id)
    anonymous_id = resolve_anonymous_id(None, request)
    user = get_or_create_user(session, anonymous_id)
    feedback = RecipeFeedback(
        user_id=int(user.id),
        recipe_id=int(recipe.id),
        feedback_type=payload.action,
        rating=payload.rating,
        tags=[payload.comment] if payload.comment else [],  # 模型无 comment 列，文字反馈入 tags
    )
    session.add(feedback)
    session.commit()
    return {
        "id": int(feedback.id),
        "recipe_id": int(recipe.id),
        "feedback_type": payload.action,
        "rating": payload.rating,
        "comment": payload.comment,
    }
