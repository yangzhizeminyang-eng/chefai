"""推荐主接口路由模块。

职责：
    POST /v1/recommend：推荐主接口（三档 + rank_reasons + filtered_by）；
    - 幂等：request_id 缺省自动生成；重复 request_id 直接返回缓存响应
      （响应头 X-Idempotent-Replay: true），不重复执行编排（spec 5.6）；
    - 一票否决短路响应原样透传（仅 blocked/overrides_all/risk/disclaimer_id/trace_id），
      🔴 绝不出现 results/candidates/nutrition 键（D9 红线）；
    - 正常响应做展示适配：allergens（菜谱∪食材致敏原）、required_equipment、source、
      difficulty 三档文案、cover_image_url 封面成品图（批量补齐，无图 None 回落
      前端占位封面）、Top 结果营养（nutrition，每份口径）；
    - E.11 空结果建议：results 为空时附加 suggestions（message/relax_options/
      followup_question），不影响幂等与否决路径。

    POST /v1/recommend/filtered：布尔硬过滤重放（W-02「显示被我过滤掉的菜」）。
    说明：agent_trace 仅落库节点 span（node_name/status/duration_ms），hard_filter
    的 filtered 明细【未落库】，GET trace 回放不可行——故采用重放语义：以请求体
    {ingredients, allergen_codes, ..., equipment} 现场执行 retrieve_candidates +
    hard_filter，返回会被过滤掉的菜谱及原因（allergen/taboo/difficulty/equipment；
    reasons 数组元素为 {type, detail} 结构，设备维度 detail 形如「缺少设备：燃气灶」）。
"""

from __future__ import annotations

import json

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ability.ranking import find_missing_equipment, hard_filter
from app.ability.retrieval import retrieve_candidates
from app.api.v1.deps import adapt_risk, difficulty_label, resolve_existing_user_id, resolve_request_id
from app.core.db import get_db
from app.core.idempotency import get_cached_response, store_response
from app.core.logging import get_logger
from app.core.recipe_covers import resolve_recipe_cover_url
from app.graph.runner import run_recommend
from app.models import Ingredient, IngredientAlias, Recipe
from app.safety import SafetyProfile
from app.schemas.recommend import RecommendIngredient, RecommendRequest
from app.schemas.vision import EmptyResultSuggestions, FilteredResponse

router = APIRouter(tags=["recommend"])

logger = get_logger(__name__)

# 幂等缓存使用的规范路径（与请求路径一致）
_IDEMPOTENT_PATH = "/v1/recommend"


def _load_source_labels(session: Session, recipe_ids: list[int]) -> dict[int, str]:
    """批量查询菜谱来源标注（函数）。

    说明：
        召回候选不携带 source_label，此处按结果 recipe_id 批量补齐（单次 IN 查询）。

    参数：
        session：数据库会话。
        recipe_ids：结果菜谱 ID 列表。

    返回值：
        dict[int, str]：{recipe_id: source_label}。

    异常：
        查询异常返回空映射（source 字段置 None，不阻断响应）。
    """
    if not recipe_ids:
        return {}
    try:
        rows = session.execute(
            select(Recipe.id, Recipe.source_label, Recipe.servings).where(Recipe.id.in_(recipe_ids))
        ).all()
        return {int(rid): (label or "") for rid, label, _servings in rows}
    except Exception as exc:  # noqa: BLE001 —— 来源标注缺失不影响主结果
        logger.warning("load source labels failed: %s", exc)
        return {}


def _load_cover_images(session: Session, recipe_ids: list[int]) -> dict[int, str | None]:
    """批量查询菜谱封面图 URL（函数）。

    说明：
        召回候选不携带 cover_image_url，此处按结果 recipe_id 批量补齐（单次 IN
        查询），供推荐卡片顶部成品图展示；无图条目值为 None，前端回落占位封面。
        🔴 取值须经 resolve_recipe_cover_url：封面资源按 md5(title) 落盘，
        数据库列可能尚未回填（历史数据），直接读列会让「文件已存在但列为 NULL」
        的菜谱在推荐页误显示为「暂无实拍」，与菜谱列表/详情页表现不一致。

    参数：
        session：数据库会话。
        recipe_ids：结果菜谱 ID 列表。

    返回值：
        dict[int, str | None]：{recipe_id: cover_image_url}（None 表示该菜无封面）。

    异常：
        查询异常返回空映射（cover_image_url 字段置 None，不阻断响应）。
    """
    if not recipe_ids:
        return {}
    try:
        rows = session.execute(
            select(Recipe.id, Recipe.title, Recipe.cover_image_url).where(
                Recipe.id.in_(recipe_ids)
            )
        ).all()
        return {
            int(rid): resolve_recipe_cover_url(title, url) for rid, title, url in rows
        }
    except Exception as exc:  # noqa: BLE001 —— 封面缺失不影响主结果
        logger.warning("load cover images failed: %s", exc)
        return {}


def _resolve_ingredient_names(session: Session, items: list) -> list[str]:
    """将推荐输入食材归一为名称字符串列表（函数）。

    说明：
        编排层 supervisor 的 has_ingredients 判定只消费字符串食材（子图解析字段
        在主图阶段尚未就绪），dict 形态 {ingredient_id} 会导致空文本输入被兜底为
        闲聊意图——故在 API 层完成 ID→名称解析：
        - name 非空：直接使用；
        - 仅 ingredient_id：批量查库解析（查不到的条目丢弃）；
        - 纯字符串：透传。
        归一结果同时惠及 intake_guard（食材名参与高危扫描，如「发芽土豆」）。

    参数：
        session：数据库会话。
        items：Pydantic 解析后的食材项列表（RecommendIngredient 或字符串）。

    返回值：
        list[str]：去重后的食材名称列表。

    异常：
        查询异常时降级为仅含显式名称的列表（不阻断响应）。
    """
    names: list[str] = []
    ids_to_resolve: list[tuple[int, int]] = []  # (items 下标, ingredient_id)
    for index, item in enumerate(items):
        if isinstance(item, str):
            if item.strip() and item.strip() not in names:
                names.append(item.strip())
            continue
        if item.name:
            if item.name not in names:
                names.append(item.name)
        elif item.ingredient_id:
            ids_to_resolve.append((index, item.ingredient_id))
    if ids_to_resolve:
        try:
            rows = session.execute(
                select(Ingredient.id, Ingredient.name).where(
                    Ingredient.id.in_([pid for _idx, pid in ids_to_resolve])
                )
            ).all()
            name_by_id = {int(rid): str(name) for rid, name in rows}
            for _index, pid in ids_to_resolve:
                resolved = name_by_id.get(int(pid))
                if resolved and resolved not in names:
                    names.append(resolved)
        except Exception as exc:  # noqa: BLE001 —— 名称解析失败按已解析子集继续
            logger.warning("resolve ingredient names failed: %s", exc)
    return names


def _load_recipe_servings(session: Session, recipe_id: int) -> int | None:
    """查询单个菜谱基准份数（函数）。

    参数：
        session：数据库会话。
        recipe_id：菜谱 ID。

    返回值：
        int | None：基准份数；查询失败返回 None。

    异常：
        不抛出。
    """
    try:
        return session.execute(
            select(Recipe.servings).where(Recipe.id == recipe_id)
        ).scalar_one_or_none()
    except Exception:  # noqa: BLE001
        return None


@router.post("/recommend", summary="推荐主接口（三档结果 + rank_reasons + filtered_by）")
def post_recommend(
    payload: RecommendRequest,
    request: Request,
    session: Session = Depends(get_db),
) -> JSONResponse:
    """推荐主接口端点（函数）。

    说明：
        编排执行由 app.graph.runner.run_recommend 完成（双侧闸门 + 一票否决 + trace 落库）；
        本端点负责幂等缓存与响应展示适配。
        排序侧契约（ability/ranking.py）：三档 match_level（can_cook_now /
        missing_1_2 / need_more）取 Top 8；DEF-12 缺料上限——missing 数量
        >MAX_MISSING_INGREDIENTS(8) 的菜谱在「需要多买几样」档档内截断前整条
        跳过，不入结果、不占 Top 8 名额；rank_reasons 逐条可解释。

    参数：
        payload：推荐请求体（ingredients ≥1 由 Pydantic 校验）。
        request：FastAPI 请求对象。
        session：请求级数据库会话。

    返回值：
        JSONResponse：200 正常体（含 results）/ 200 否决体（blocked=true，体纯净）。

    异常：
        编排层全捕获兜底（保守模式响应），本端点不向外抛业务异常。
    """
    # 幂等键：显式传入优先，否则复用中间件 request_id / 请求头，最后自动生成
    rid = resolve_request_id(payload.request_id, request)

    # 幂等命中：直接返回首次响应（不重复执行编排）
    cached = get_cached_response("POST", _IDEMPOTENT_PATH, rid)
    if cached is not None:
        return JSONResponse(
            content=cached,
            headers={"X-Idempotent-Replay": "true", "X-Request-Id": rid},
        )

    # 编排 payload：食材在 API 层归一为名称字符串（supervisor/闸门可消费），runner 再按
    # 名称/别名/ID 解析；过敏原/忌口集合为空数组占位（R-2：runner 侧按「payload 非空
    # 覆盖档案」合并——空占位回退用户档案，payload 显式非空时覆盖档案）
    ingredient_names = _resolve_ingredient_names(session, payload.ingredients)
    # R-2 传参：只读解析既有用户 ID（无身份/用户不存在为 None），供 runner 加载家庭档案
    user_id = resolve_existing_user_id(session, payload.anonymous_id, request)
    graph_payload = {
        "request_id": rid,
        "ingredients": ingredient_names,
        "text": payload.text or "",
        "allergen_codes": [],
        "dietary_restrictions": [],
        "user_id": user_id,
    }
    response = run_recommend(graph_payload)

    # 一票否决短路：原样透传（risk 补 rule_id），🔴 不附加任何业务字段
    if response.get("blocked"):
        body = {
            "request_id": response.get("request_id") or rid,
            "blocked": bool(response.get("blocked")),
            "overrides_all": bool(response.get("overrides_all")),
            "risk": adapt_risk(response.get("risk")),
            "disclaimer_id": response.get("disclaimer_id"),
            "trace_id": response.get("trace_id"),
        }
        store_response("POST", _IDEMPOTENT_PATH, rid, body)
        return JSONResponse(content=body, headers={"X-Request-Id": rid})

    # 正常响应：展示适配
    results = list(response.get("results") or [])
    source_map = _load_source_labels(session, [int(r.get("recipe_id")) for r in results if r.get("recipe_id")])
    cover_map = _load_cover_images(session, [int(r.get("recipe_id")) for r in results if r.get("recipe_id")])
    adapted_results: list[dict] = []
    for item in results:
        allergens = sorted(
            set(list(item.get("allergen_codes") or []) + list(item.get("ingredient_allergen_codes") or []))
        )
        adapted_results.append(
            {
                "recipe_id": item.get("recipe_id"),
                "title": item.get("title"),
                "match_level": item.get("match_level"),
                "covered_ingredients": list(item.get("covered_ingredients") or []),
                "missing_ingredients": list(item.get("missing_ingredients") or []),
                "time_minutes": item.get("time_minutes"),
                "difficulty": difficulty_label(item.get("difficulty")),
                "calories_kcal": item.get("calories_kcal"),
                "allergens": allergens,
                "required_equipment": list(item.get("equipment") or []),
                "rank_score": item.get("rank_score", 0.0),
                "rank_reasons": list(item.get("rank_reasons") or []),
                "source": source_map.get(int(item.get("recipe_id"))) if item.get("recipe_id") else None,
                # 封面成品图 URL（None 表示无图，前端回落程序化占位封面）
                "cover_image_url": cover_map.get(int(item.get("recipe_id"))) if item.get("recipe_id") else None,
            }
        )

    # Top 结果营养（每份口径；取自 compose 合并进首条结果的 nutrition 摘要）
    nutrition_top = None
    if adapted_results:
        first_raw = results[0] or {}
        raw_nutrition = first_raw.get("nutrition") or {}
        per_serving = (raw_nutrition.get("per_serving") or {}) if isinstance(raw_nutrition, dict) else {}
        if per_serving:
            base_servings = _load_recipe_servings(session, int(adapted_results[0]["recipe_id"])) or 2
            nutrition_top = {
                "kcal": per_serving.get("kcal"),
                "protein": per_serving.get("protein_g"),
                "fat": per_serving.get("fat_g"),
                "carbs": per_serving.get("carbs_g"),
                "sodium": per_serving.get("sodium_mg"),
                "per_serving": base_servings,
                "excluded_items": list(raw_nutrition.get("excluded_items") or []),
                "estimate_note": raw_nutrition.get("estimate_note") or "估算值，非实测值，误差约 ±15%",
            }

    body = {
        "request_id": response.get("request_id") or rid,
        "safe_mode": bool(response.get("safe_mode")),
        "results": adapted_results,
        "filtered_by": response.get("filtered_by") or {},
        "disclaimer_id": response.get("disclaimer_id"),
        "trace_id": response.get("trace_id"),
    }
    if nutrition_top is not None:
        body["nutrition"] = nutrition_top
    if response.get("partial_failures"):
        body["partial_failures"] = list(response["partial_failures"])
    if response.get("notice"):
        body["notice"] = response["notice"]
    # E.11 空结果建议：仅正常响应且 results 为空时附加（不影响否决/短路路径）
    if not adapted_results:
        body["suggestions"] = _build_empty_suggestions()

    store_response("POST", _IDEMPOTENT_PATH, rid, body)
    return JSONResponse(
        content=json.loads(json.dumps(body, ensure_ascii=False, default=str)),
        headers={"X-Request-Id": rid},
    )


class FilteredRecommendRequest(BaseModel):
    """硬过滤重放请求体（模型类）。

    说明：
        W-02「显示被我过滤掉的菜」：以用户食材 + 过敏原/忌口/难度上限 + 设备清单
        现场重放布尔硬过滤，返回会被移除的菜谱及原因。

    属性：
        ingredients：已选食材列表（≥1，形态同 /v1/recommend）。
        allergen_codes：过敏原 code 集合（GB 7718 八类，缺省空）。
        dietary_restrictions：忌口标记集合（缺省空）。
        difficulty_cap：难度上限 1~5（缺省 None 不过滤）。
        equipment：用户已有设备清单（对齐档案白名单编码，缺省空=不启用设备过滤）。
    """

    ingredients: list[RecommendIngredient] = Field(min_length=1)
    allergen_codes: list[str] = Field(default_factory=list)
    dietary_restrictions: list[str] = Field(default_factory=list)
    difficulty_cap: int | None = Field(default=None, ge=1, le=5)
    equipment: list[str] = Field(default_factory=list)


def _build_empty_suggestions() -> dict:
    """构造推荐空结果建议字段（E.11，函数）。

    说明：
        纯函数（无 IO）：给出固定放宽选项与追问话术，供前端在 results 为空时
        渲染引导卡片。

    参数：
        无。

    返回值：
        dict：{message, relax_options, followup_question}。

    异常：
        无。
    """
    return EmptyResultSuggestions(
        message="没有找到能做的菜",
        relax_options=["放宽到差 1-2 样", "移除忌口限制"],
        followup_question="要不要试试补充鸡蛋或西红柿？",
    ).model_dump()


def _lookup_ingredient_id(session: Session, name: str) -> int | None:
    """按名称/别名查询单个食材 ID（函数）。

    说明：
        食材名精确命中优先，别名次之（与推荐子图 assemble_context 同口径）。

    参数：
        session：数据库会话。
        name：食材名称或别名。

    返回值：
        int | None：ingredient_id；未命中返回 None。

    异常：
        查询异常向上抛出（由 _resolve_ingredient_ids 统一捕获降级）。
    """
    ing_id = session.execute(
        select(Ingredient.id).where(Ingredient.name == name)
    ).scalar_one_or_none()
    if ing_id is not None:
        return int(ing_id)
    row = session.execute(
        select(IngredientAlias.ingredient_id).where(IngredientAlias.alias == name).limit(1)
    ).first()
    return int(row[0]) if row else None


def _resolve_ingredient_ids(session: Session, items: list) -> list[int]:
    """将推荐输入食材解析为 ingredient_id 列表（函数）。

    说明：
        支持三种输入形态：名称字符串 / {ingredient_id} 字典 / {name} 字典；
        与 _resolve_ingredient_names 的展示名归一互补，此处产出召回所需 ID。

    参数：
        session：数据库会话。
        items：Pydantic 解析后的食材项列表（RecommendIngredient 或字符串）。

    返回值：
        list[int]：去重后的 ingredient_id 列表（未命中的条目丢弃）。

    异常：
        不抛出（查询异常时返回已解析子集，不阻断重放）。
    """
    ids: list[int] = []
    try:
        for item in items:
            if isinstance(item, str):
                name = item.strip()
            elif getattr(item, "ingredient_id", None):
                if int(item.ingredient_id) not in ids:
                    ids.append(int(item.ingredient_id))
                continue
            else:
                name = str(getattr(item, "name", "") or "").strip()
            if not name:
                continue
            resolved = _lookup_ingredient_id(session, name)
            if resolved is not None and resolved not in ids:
                ids.append(resolved)
    except Exception as exc:  # noqa: BLE001 —— 名称解析失败按已解析子集继续
        logger.warning("resolve ingredient ids failed: %s", exc)
    return ids


def _attribute_filter_reasons(
    session: Session, recipe_ids: list[int], profile: SafetyProfile
) -> dict[int, list[dict]]:
    """归因每道被过滤菜谱的全部过滤原因（函数）。

    说明：
        hard_filter 仅返回聚合计数，此处对被移除菜谱逐个复核命中条件，产出
        {type, detail} 原因数组（同菜谱多条件命中时全部列出）；类型优先级
        allergen（致敏原）> taboo（忌口）> difficulty（难度超限）> equipment（缺设备），
        供主原因 reason 字段取首项。设备维度仅对灶具/电器/锅具类词项做差集
        （复用 find_missing_equipment：基础工具豁免 + 档案为空不生效）。

    参数：
        session：数据库会话。
        recipe_ids：被过滤的菜谱 ID 列表。
        profile：重放用的安全档案（过敏原/忌口/难度上限/设备清单）。

    返回值：
        dict[int, list[dict]]：{recipe_id: [{"type": ..., "detail": ...}, ...]}，
        type ∈ {"allergen", "taboo", "difficulty", "equipment"}；设备 detail 形如
        「缺少设备：燃气灶」。理论上每条至少一项（被过滤必有命中条件）。

    异常：
        不抛出（查询异常时全部归因为 allergen 兜底，不阻断重放）。
    """
    reasons: dict[int, list[dict]] = {}
    if not recipe_ids:
        return reasons
    try:
        rows = session.execute(
            select(
                Recipe.id,
                Recipe.allergen_codes,
                Recipe.ingredient_allergen_codes,
                Recipe.dietary_flags,
                Recipe.difficulty,
                Recipe.equipment,
            ).where(Recipe.id.in_(recipe_ids))
        ).all()
    except Exception as exc:  # noqa: BLE001 —— 归因失败兜底 allergen
        logger.warning("attribute filter reasons failed: %s", exc)
        return {int(rid): [{"type": "allergen", "detail": "过滤归因失败，按致敏原兜底"}] for rid in recipe_ids}

    allergen_codes = set(profile.user_allergen_codes or [])
    restrictions = set(profile.dietary_restrictions or [])
    for rid, recipe_allergens, ing_allergens, flags, difficulty, equipment in rows:
        rid = int(rid)
        item_reasons: list[dict] = []
        allergen_hits: set[str] = set()
        if allergen_codes:
            allergen_hits = (
                allergen_codes & set(recipe_allergens or []) | allergen_codes & set(ing_allergens or [])
            )
            if allergen_hits:
                item_reasons.append(
                    {"type": "allergen", "detail": f"命中过敏原：{'、'.join(sorted(allergen_hits))}"}
                )
        taboo_hits = restrictions & set(flags or []) if restrictions else set()
        if taboo_hits:
            item_reasons.append(
                {"type": "taboo", "detail": f"命中忌口：{'、'.join(sorted(taboo_hits))}"}
            )
        if (
            profile.difficulty_cap
            and difficulty is not None
            and int(difficulty) > int(profile.difficulty_cap)
        ):
            item_reasons.append(
                {
                    "type": "difficulty",
                    "detail": f"难度 {int(difficulty)} 超过上限 {int(profile.difficulty_cap)}",
                }
            )
        missing_equipment = find_missing_equipment(equipment or [], profile.equipment or [])
        if missing_equipment:
            item_reasons.append(
                {"type": "equipment", "detail": f"缺少设备：{'、'.join(missing_equipment)}"}
            )
        if not item_reasons:
            # 理论不可达（被过滤必有命中条件），兜底归因为过敏原
            item_reasons.append({"type": "allergen", "detail": "过滤归因失败，按致敏原兜底"})
        reasons[rid] = item_reasons
    return reasons


@router.post(
    "/recommend/filtered",
    response_model=FilteredResponse,
    summary="布尔硬过滤重放（显示会被过滤掉的菜谱及原因：allergen/taboo/difficulty/equipment）",
)
def post_recommend_filtered(
    payload: FilteredRecommendRequest,
    session: Session = Depends(get_db),
) -> dict:
    """硬过滤重放端点（函数）。

    说明：
        agent_trace 未落库 filtered 明细，无法按 trace_id 回放——故为重放语义：
        retrieve_candidates 召回 → hard_filter 布尔过滤（含设备差集维度）→
        对被移除菜谱归因全部原因（{type, detail} 数组，主原因 reason 取首项）。
        候选为空时返回空列表（total_filtered=0）。

    参数：
        payload：重放请求体（ingredients ≥1 + 可选过敏原/忌口/难度上限/设备清单）。
        session：请求级数据库会话。

    返回值：
        dict：{filtered: [{recipe_id, recipe_name, reason, reasons}], total_filtered: int}。

    异常：
        召回/过滤内部全捕获（异常按空集降级），本端点不向外抛业务异常。
    """
    ingredient_ids = _resolve_ingredient_ids(session, payload.ingredients)
    candidates = retrieve_candidates(session, ingredient_ids, limit=200)
    profile = SafetyProfile(
        user_allergen_codes=[str(c) for c in payload.allergen_codes],
        dietary_restrictions=[str(c) for c in payload.dietary_restrictions],
        special_population=[],
        difficulty_cap=payload.difficulty_cap,
        equipment=[str(e) for e in payload.equipment],
    )
    filtered, _counts = hard_filter(session, candidates, profile)
    kept_ids = {int(c["recipe_id"]) for c in filtered}
    removed = [c for c in candidates if int(c["recipe_id"]) not in kept_ids]
    reason_map = _attribute_filter_reasons(session, [int(c["recipe_id"]) for c in removed], profile)
    items = [
        {
            "recipe_id": int(c["recipe_id"]),
            "recipe_name": str(c.get("title") or ""),
            "reason": (reason_map.get(int(c["recipe_id"])) or [{"type": "allergen"}])[0]["type"],
            "reasons": reason_map.get(int(c["recipe_id"])) or [],
        }
        for c in removed
    ]
    return {"filtered": items, "total_filtered": len(items)}
