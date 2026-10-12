"""菜谱混合召回模块（Task 8 升级：pgvector 混合检索 R-1 收敛；向量模型升级扩展）。

职责：
    实现阶段一默认检索（spec D5：不下载向量模型）+ 向量混合召回（spec D3）：
    ① 有食材输入时按 recipe_ingredient 覆盖数降序召回（食材覆盖率优先）；
    ② query_text 非空时按菜名 ILIKE 与食材名/别名匹配召回（搜索/自然语言路径）；
    ③ 向量路径（use_vector 且查询文本非空）：查询文本 → 嵌入 → 双分支检索——
       - pgvector 可用（probe_pgvector）→ raw SQL `<=>` 余弦距离 Top-20；
       - 不可用 → 从 embedding_json 读出（≤800 行）纯 Python 点积 Top-20（无 numpy）；
       两分支均按当前嵌入空间（provider.space_name → embedding_model 列）过滤，
       不同空间的向量绝不通算余弦（GAP-4）；
    合成查询（C4）：RETRIEVAL_VECTOR_FOR_INGREDIENTS 开启且「无文本有食材」时，
    用食材名空格拼接构造查询文本走向量，纯食材推荐获得语义召回；
    三路并集按 recipe_id 合并去重，向量命中但关键词未命中的加 matched_by_vector
    来源标记；
    RRF 融合（C5）：RETRIEVAL_FUSION=rrf 时按 ①覆盖 / ②文本 / ③向量 三路排名做
    Reciprocal Rank Fusion（score = Σ 1/(60+rank)），候选携带 _fusion_ranks 内部键
    标注各路排名；缺省 fixed 模式保持升级前四段固定优先级排序（行为逐字节一致）；
    Top-8（top_k）截断返回，返回结构与既有一致，下游 hard_filter/rank 无感。

分区红线（spec D3）：
    默认调用（推荐链路）只查 source='verified'——AI 私有向量行（source='ai_private'）
    绝不出现在默认推荐结果中（代码断言：查询 WHERE 显式限定 source）；
    创新链路经 include_private_owner=<user_id> 显式开启「verified + 该用户 ai_private」。

降级保证：
    probe 失败 / 向量路径任何异常 → logger.warning 降级走既有关键词路径，绝不抛错。
"""

from __future__ import annotations

from sqlalchemy import func, or_, select, text
from sqlalchemy.orm import Session

from app.ability.embedding import (
    ensure_embeddings,
    get_embedding_provider,
    lazy_backfill,
    probe_pgvector,
)
from app.ability.ranking import is_valid_ingredient_name
from app.core.config import settings
from app.core.db import engine
from app.core.logging import get_logger
from app.models import Ingredient, IngredientAlias, Recipe, RecipeEmbedding, RecipeIngredient

logger = get_logger(__name__)

# 默认候选上限（中间召回池规模）
DEFAULT_LIMIT = 200

# 默认返回条数（spec：推荐链路最终 Top-8，下游 hard_filter/rank 在此集合内工作）
DEFAULT_TOP_K = 8

# 向量召回条数（混合合并前的向量 Top-N）
VECTOR_TOP_N = 20

# Python 点积分支单次扫描的向量行上限（阶段一 published ≤400，留倍余量）
VECTOR_SCAN_MAX = 800


def match_ingredients_in_text(session: Session, text_value: str) -> tuple[list[int], list[str]]:
    """从自然语言文本中匹配食材库内的食材（函数）。

    说明：
        阶段一无 NER 模型，采用「食材名/别名为文本子串」的确定性匹配；
        食材库（256 条）与别名（202 条）规模小，全量载入内存匹配即可。

    参数：
        session：数据库会话。
        text_value：用户自然语言输入。

    返回值：
        tuple[list[int], list[str]]：(匹配到的 ingredient_id 列表, 匹配到的食材名列表)。

    异常：
        不抛出（查询异常返回空列表并告警）。
    """
    if not text_value:
        return [], []
    try:
        rows = session.execute(select(Ingredient.id, Ingredient.name)).all()
    except Exception as exc:  # noqa: BLE001 —— 召回失败不阻断，交由上层兜底
        logger.warning("match ingredients in text failed: %s", exc)
        return [], []
    try:
        alias_rows = session.execute(
            select(IngredientAlias.alias, IngredientAlias.ingredient_id)
        ).all()
    except Exception:  # noqa: BLE001
        alias_rows = []

    matched_ids: list[int] = []
    matched_names: list[str] = []
    # 先精确匹配食材名（长名优先，避免「土豆」误吞「土豆泥」类短名歧义）
    for ing_id, name in rows:
        if name and name in text_value:
            matched_ids.append(int(ing_id))
            matched_names.append(name)
    for alias, ing_id in alias_rows:
        if alias and alias in text_value and int(ing_id) not in matched_ids:
            matched_ids.append(int(ing_id))
            matched_names.append(alias)
    return matched_ids, matched_names


# 问句文本并入食材的默认上限（OBS-03：命中 ≤10 个去重食材名）
TEXT_MATCH_LIMIT = 10


def _match_terms_longest_first(
    text_value: str, terms: list[tuple[str, str]], limit: int = TEXT_MATCH_LIMIT
) -> list[str]:
    """词表最长匹配纯函数（函数，OBS-03 核心）。

    说明：
        按词长倒序逐一尝试子串匹配，命中区间标记为「已消费」——长词
        （如「土豆淀粉」）优先于其子串短词（如「土豆」），避免同一文本区间
        被长短两词重复命中；别名命中归一到主名后按食材名去重。
        纯函数不依赖数据库，便于单测直接构造词表验证。

    参数：
        text_value：用户输入文本（调用方保证非空）。
        terms：(匹配词, 归一食材名) 元组列表（词表）。
        limit：返回食材名上限（默认 10）。

    返回值：
        list[str]：去重后的食材名列表（≤limit，按首次命中顺序）。

    异常：
        无。
    """
    matched_names: list[str] = []
    consumed: list[tuple[int, int]] = []
    # 词长倒序（同长按归一名稳定排序）：长词优先消费文本区间
    ordered = sorted(terms, key=lambda pair: (-len(pair[0]), pair[1]))
    for term, display in ordered:
        if len(matched_names) >= limit:
            break
        if not term or term not in text_value or not display:
            continue
        start = text_value.find(term)
        while start != -1:
            end = start + len(term)
            # 该出现位置与已消费区间重叠 → 已被更长词覆盖，尝试下一个出现位置
            if any(start < c_end and c_start < end for c_start, c_end in consumed):
                start = text_value.find(term, start + 1)
                continue
            consumed.append((start, end))
            if display not in matched_names:
                matched_names.append(display)
            break  # 同一词只消费一处区间（避免重复计入）
    return matched_names


def extract_ingredient_names_from_text(
    session: Session, text_value: str, limit: int = TEXT_MATCH_LIMIT
) -> list[str]:
    """从自然语言问句中提取食材名（最长匹配优先，OBS-03）（函数）。

    说明：
        与 match_ingredients_in_text 的「全量收集」口径不同，本函数按最长匹配
        消费文本区间：「土豆淀粉」命中后不再让「土豆」在同一区间重复命中；
        别名命中归一到主名；结果去重且上限 limit（默认 10），供推荐检索
        把问句食材并入 ingredients 入参。

    参数：
        session：数据库会话。
        text_value：用户自然语言输入。
        limit：返回食材名上限（默认 10）。

    返回值：
        list[str]：去重食材名列表（≤limit；查询异常返回空列表并告警）。

    异常：
        不抛出（数据库异常告警后返回空列表，不阻断推荐链路）。
    """
    if not text_value or not text_value.strip():
        return []
    try:
        terms: list[tuple[str, str]] = [
            (str(name).strip(), str(name).strip())
            for (name,) in session.execute(select(Ingredient.name)).all()
            if name and str(name).strip()
        ]
        alias_rows = session.execute(
            select(IngredientAlias.alias, Ingredient.name)
            .join(Ingredient, Ingredient.id == IngredientAlias.ingredient_id)
        ).all()
        for alias, ing_name in alias_rows:
            alias_text = str(alias or "").strip()
            if alias_text:
                display = str(ing_name or "").strip() or alias_text
                terms.append((alias_text, display))
        return _match_terms_longest_first(text_value.strip(), terms, limit)
    except Exception as exc:  # noqa: BLE001 —— 提取失败并入空集，不阻断主链路
        logger.warning("extract ingredient names from text failed: %s", exc)
        return []


def _vector_search_pgvector(
    query_vector: list[float], include_private_owner: int | None, space_name: str
) -> dict[int, float]:
    """pgvector raw SQL 余弦检索分支（函数）。

    说明：
        向量列 embedding(vector(1024)) 仅存在于迁移中，raw SQL 以 `<=>` 余弦距离
        排序取 Top-20；使用独立 engine 连接，失败不污染调用方事务。
        空间过滤（GAP-4）：每个分支都限定 embedding_model = 当前嵌入空间，
        不同空间向量绝不通算余弦。
        分区红线：默认仅 source='verified'；include_private_owner 时追加该用户
        source='ai_private' 行（代码断言，AI 私有菜谱不进默认推荐）。

    参数：
        query_vector：查询向量（1024 维，已归一化）。
        include_private_owner：创新链路归属用户 ID；None 仅查 verified。
        space_name：当前嵌入空间标识（与 embedding_model 列匹配）。

    返回值：
        dict[int, float]：recipe_id → 余弦相似度（Top-20，降序）。

    异常：
        SQL 异常向上抛出（由 _vector_search 统一捕获降级）。
    """
    q_literal = "[" + ",".join(f"{x:.6f}" for x in query_vector) + "]"
    # 🔴 OR 分支必须括号包裹：空间过滤 AND 进每个分支（否则 verified 行会绕过空间过滤）
    sql = (
        "SELECT recipe_id, 1 - (embedding <=> CAST(:q AS vector)) AS sim "
        "FROM recipe_embedding "
        "WHERE (source = 'verified' AND embedding_model = :m)"
    )
    params: dict = {"q": q_literal, "m": space_name}
    if include_private_owner is not None:
        sql += " OR (source = 'ai_private' AND owner_user_id = :owner AND embedding_model = :m)"
        params["owner"] = int(include_private_owner)
    sql += " ORDER BY embedding <=> CAST(:q AS vector) LIMIT :n"
    params["n"] = VECTOR_TOP_N
    with engine.connect() as conn:
        rows = conn.execute(text(sql), params).all()
    return {int(rid): float(sim) for rid, sim in rows if rid is not None}


def _vector_search_json(
    session: Session, query_vector: list[float], include_private_owner: int | None, space_name: str
) -> dict[int, float]:
    """embedding_json 便携列 Python 点积检索分支（函数，无 numpy）。

    说明：
        无 pgvector 扩展环境（本机）走此分支：读「当前嵌入空间」的 verified 行
        （≤800 行）+（创新链路）指定用户的 ai_private 行，embedding_json 均已
        L2 归一化，纯 Python 点积即余弦相似度（1024 维 × 数百行，毫秒级）。
        空间过滤（GAP-4）：两个 select 分支均限定 embedding_model = 当前空间。

    参数：
        session：数据库会话。
        query_vector：查询向量（1024 维，已归一化）。
        include_private_owner：创新链路归属用户 ID；None 仅查 verified（分区红线）。
        space_name：当前嵌入空间标识（与 embedding_model 列匹配）。

    返回值：
        dict[int, float]：recipe_id → 余弦相似度（Top-20，降序）。

    异常：
        查询异常向上抛出（由 _vector_search 统一捕获降级）。
    """
    base_cols = (RecipeEmbedding.recipe_id, RecipeEmbedding.embedding_json)
    stmt = select(*base_cols).where(RecipeEmbedding.source == "verified")  # 🔴 默认仅 verified
    stmt = stmt.where(RecipeEmbedding.embedding_model == space_name)  # 空间过滤（GAP-4）
    if include_private_owner is not None:
        # 创新链路分区：verified + 指定用户的 ai_private（其余用户私有行绝不出现）
        stmt = select(*base_cols).where(
            or_(
                RecipeEmbedding.source == "verified",
                (RecipeEmbedding.source == "ai_private")
                & (RecipeEmbedding.owner_user_id == int(include_private_owner)),
            )
        )
        stmt = stmt.where(RecipeEmbedding.embedding_model == space_name)  # 空间过滤（GAP-4）
    rows = session.execute(stmt.limit(VECTOR_SCAN_MAX)).all()
    dim = len(query_vector)
    scored: list[tuple[int, float]] = []
    for rid, vec in rows:
        if rid is None or not vec or len(vec) != dim:
            continue
        similarity = sum(a * b for a, b in zip(query_vector, vec, strict=True))
        scored.append((int(rid), similarity))
    scored.sort(key=lambda item: -item[1])
    return dict(scored[:VECTOR_TOP_N])


def _vector_search(
    session: Session, query_text: str, include_private_owner: int | None
) -> dict[int, float]:
    """向量路径总入口：惰性回填 → 嵌入 → pgvector/JSON 双分支（函数）。

    参数：
        session：数据库会话。
        query_text：查询文本（非空）。
        include_private_owner：创新链路归属用户 ID；None 仅查 verified。

    返回值：
        dict[int, float]：recipe_id → 余弦相似度（Top-20）。

    异常：
        向上游传播（由 retrieve_candidates 捕获降级，绝不抛给接口层）。
    """
    # verified 向量缺失时惰性回填一次（幂等 + 进程锁防并发重复）
    lazy_backfill(session)
    provider = get_embedding_provider()
    query_vector = provider.embed([query_text])[0]
    if probe_pgvector(engine):
        return _vector_search_pgvector(query_vector, include_private_owner, provider.space_name)
    return _vector_search_json(session, query_vector, include_private_owner, provider.space_name)


def retrieve_candidates(
    session: Session,
    ingredient_ids: list[int],
    query_text: str | None = None,
    limit: int = DEFAULT_LIMIT,
    *,
    top_k: int = DEFAULT_TOP_K,
    use_vector: bool = True,
    include_private_owner: int | None = None,
) -> list[dict]:
    """混合召回菜谱候选集（函数）。

    说明：
        - 有 ingredient_ids：按「候选菜谱引用的用户食材数（覆盖数）」降序召回；
        - 有 query_text：追加菜名 ILIKE 召回 + 按文本中解析出的食材召回；
        - use_vector 且查询文本非空：追加向量语义召回（Top-20），
          pgvector 可用走 raw SQL `<=>`，否则 embedding_json 纯 Python 点积；
        - 合成查询（C4）：RETRIEVAL_VECTOR_FOR_INGREDIENTS 开启且「无文本有食材」
          时，用食材名空格拼接构造查询文本走向量（上限 TEXT_MATCH_LIMIT 个名称）；
        - 三路并集按 recipe_id 合并去重；向量命中但关键词未命中的候选标记
          matched_by_vector=True（下游排序在菜名命中之后、其余之前）；
        - 排序（RETRIEVAL_FUSION）：'rrf' 时按 ①覆盖/②文本/③向量 三路排名做
          Reciprocal Rank Fusion（score = Σ 1/(60+rank)）排序，候选携带
          _fusion_ranks 内部键标注各路排名；缺省 fixed 为固定优先级排序
          （覆盖数降序 → 菜名命中 → 向量相似度 → id 升序，与升级前一致）；
        - 三路皆空：回退全部已发布菜谱（保证冷启动可演示）；
        - 🔴 分区红线：默认（include_private_owner=None）向量查询只查
          source='verified'，AI 私有菜谱绝不进入默认推荐；
        - 最终 top_k（默认 8）截断返回，字段结构与既有一致，下游无感。

    参数：
        session：数据库会话。
        ingredient_ids：用户食材 ID 列表（可为空）。
        query_text：查询文本（可为空）。
        limit：中间召回池上限，默认 200。
        top_k：最终返回条数，默认 8。
        use_vector：是否启用向量路径（默认 True；recommend 节点经
          RETRIEVAL_VECTOR 环境变量控制）。
        include_private_owner：创新链路归属用户 ID（默认 None=仅 verified）。

    返回值：
        list[dict]：候选菜谱字典列表（≤top_k 条），每条含：
            recipe_id/title/difficulty/time_minutes/calories_kcal/allergen_codes/
            ingredient_allergen_codes/dietary_flags/equipment/covered_count/
            covered_names/main_ingredient_names/seasoning_names/matched_by_title/
            matched_by_vector（rrf 融合时另含内部键 _fusion_ranks）。

    异常：
        不抛出（查询/向量异常时降级或返回空列表，由 compose 标注「暂时无法检索」）。
    """
    try:
        id_score: dict[int, int] = {}          # recipe_id → 覆盖数
        title_matched: set[int] = set()        # 菜名命中集合
        path_coverage: list[int] = []          # ① 覆盖路的 recipe_id 排名序（SQL 已降序）
        text_rank_extra: dict[int, int] = {}   # ② 文本扩展路 recipe_id → 该路覆盖数
        path_vector: list[int] = []            # ③ 向量路命中序（③ 后由 dict 保序赋值）

        # ① 食材覆盖召回：引用了用户食材的已发布菜谱，按覆盖数降序
        if ingredient_ids:
            stmt = (
                select(RecipeIngredient.recipe_id, func.count(RecipeIngredient.id).label("covered"))
                .join(Recipe, Recipe.id == RecipeIngredient.recipe_id)
                .where(Recipe.status == "published")
                .where(RecipeIngredient.ingredient_id.in_(ingredient_ids))
                .group_by(RecipeIngredient.recipe_id)
                .order_by(func.count(RecipeIngredient.id).desc())
                .limit(limit)
            )
            for recipe_id, covered in session.execute(stmt).all():
                id_score[int(recipe_id)] = int(covered)
                path_coverage.append(int(recipe_id))  # ① 覆盖路排名序（SQL 已按覆盖数降序）

        # ② 文本召回：菜名 ILIKE + 文本解析出的食材引用
        if query_text:
            keyword = f"%{query_text.strip()}%"
            title_rows = session.execute(
                select(Recipe.id).where(Recipe.status == "published").where(Recipe.title.ilike(keyword))
            ).all()
            for (recipe_id,) in title_rows:
                title_matched.add(int(recipe_id))
                id_score.setdefault(int(recipe_id), 0)
            # 文本中解析出的食材 → 引用这些食材的菜谱
            text_ids, _ = match_ingredients_in_text(session, query_text)
            extra_ids = [i for i in text_ids if i not in (ingredient_ids or [])]
            if extra_ids:
                stmt2 = (
                    select(RecipeIngredient.recipe_id, func.count(RecipeIngredient.id))
                    .join(Recipe, Recipe.id == RecipeIngredient.recipe_id)
                    .where(Recipe.status == "published")
                    .where(RecipeIngredient.ingredient_id.in_(extra_ids))
                    .group_by(RecipeIngredient.recipe_id)
                    .limit(limit)
                )
                for recipe_id, covered in session.execute(stmt2).all():
                    id_score[int(recipe_id)] = max(id_score.get(int(recipe_id), 0), int(covered))
                    # ② 文本扩展路排名序的覆盖数（id_score 的 max 逻辑不变，另存供 RRF 排名）
                    text_rank_extra[int(recipe_id)] = int(covered)

        # ③ 向量语义召回（异常降级走既有路径，绝不抛错）
        vector_sims: dict[int, float] = {}     # 仅向量命中的 recipe_id → 余弦相似度
        # 合成查询（C4）：开关开启且「无文本有食材」时，用食材名空格拼接构造查询文本走向量
        synthetic_query: str | None = None
        if (
            use_vector
            and not query_text
            and ingredient_ids
            and settings.RETRIEVAL_VECTOR_FOR_INGREDIENTS.strip().lower() in ("on", "true", "1")
        ):
            name_rows = session.execute(
                select(Ingredient.id, Ingredient.name).where(Ingredient.id.in_(ingredient_ids))
            ).all()
            name_by_id = {int(i): str(n).strip() for i, n in name_rows if n and str(n).strip()}
            names = [name_by_id[int(i)] for i in ingredient_ids if int(i) in name_by_id][:TEXT_MATCH_LIMIT]
            synthetic_query = " ".join(names) or None
        effective_query = query_text or synthetic_query
        if use_vector and effective_query:
            try:
                vector_hits = _vector_search(session, effective_query, include_private_owner)
                path_vector = list(vector_hits.keys())  # ③ 向量路命中序（dict 保序，供 RRF）
                for recipe_id in vector_hits:
                    if recipe_id not in id_score:
                        id_score[recipe_id] = 0
                        vector_sims[recipe_id] = float(vector_hits[recipe_id])
            except Exception as exc:  # noqa: BLE001 —— 向量路径异常降级为关键词路径
                logger.warning("vector retrieval failed, fallback to keyword path: %s", exc)

        # ④ 冷启动/全空回退：无任何命中 → 返回全部已发布菜谱
        if not id_score:
            rows = session.execute(
                select(Recipe.id).where(Recipe.status == "published").limit(limit)
            ).all()
            for (recipe_id,) in rows:
                id_score[int(recipe_id)] = 0

        candidate_ids = list(id_score.keys())[:limit]
        if not candidate_ids:
            return []

        # ⑤ 装配候选字典：菜谱主字段 + 全部食材引用（供硬过滤/排序/展示）
        recipes = session.execute(
            select(Recipe).where(Recipe.id.in_(candidate_ids))
        ).scalars().all()
        ri_rows = session.execute(
            select(RecipeIngredient, Ingredient.name)
            .join(Ingredient, Ingredient.id == RecipeIngredient.ingredient_id)
            .where(RecipeIngredient.recipe_id.in_(candidate_ids))
        ).all()

        ri_by_recipe: dict[int, list] = {}
        for ri, ing_name in ri_rows:
            ri_by_recipe.setdefault(int(ri.recipe_id), []).append((ri, ing_name))

        id_set = set(ingredient_ids or [])
        candidates: list[dict] = []
        for recipe in recipes:
            rid = int(recipe.id)
            items = ri_by_recipe.get(rid, [])
            main_names: list[str] = []
            seasoning_names: list[str] = []
            covered_names: list[str] = []
            for ri, ing_name in items:
                if ri.amount_type == "seasoning":
                    seasoning_names.append(ing_name)
                elif is_valid_ingredient_name(ing_name):
                    # DEF-04：无名/纯数字脏名不入主料清单（源头杜绝「缺 1」类脏标签，
                    # 覆盖率分母随之干净；排序层 missing 生成处另有同口径防御过滤）
                    main_names.append(ing_name)
                if id_set and ri.ingredient_id in id_set:
                    covered_names.append(ing_name)
            # covered_count：主料/辅料中被用户食材命中的数量（调味料默认常备，不计入）
            covered_count = len({int(ri.ingredient_id) for ri, _ in items if ri.ingredient_id in id_set})
            candidates.append(
                {
                    "recipe_id": rid,
                    "title": recipe.title,
                    "difficulty": int(recipe.difficulty),
                    "time_minutes": recipe.time_minutes,
                    "calories_kcal": recipe.calories_kcal,
                    "allergen_codes": list(recipe.allergen_codes or []),
                    "ingredient_allergen_codes": list(recipe.ingredient_allergen_codes or []),
                    "dietary_flags": list(recipe.dietary_flags or []),
                    "equipment": list(recipe.equipment or []),
                    "covered_count": covered_count,
                    "covered_names": covered_names,
                    "main_ingredient_names": main_names,
                    "seasoning_names": seasoning_names,
                    "matched_by_title": rid in title_matched,
                    "matched_by_vector": rid in vector_sims,
                    # 内部键：向量相似度仅参与召回内排序，下游 hard_filter/rank 不消费
                    "_vector_sim": round(vector_sims.get(rid, 0.0), 6),
                }
            )
        if settings.RETRIEVAL_FUSION.strip().lower() == "rrf":
            # RRF 三路融合（C5）：score = Σ 1/(60+rank)，仅用排名不用原始分数（免调权、量纲无关）
            fusion_ranks: dict[int, dict[str, int]] = {}
            rrf_score: dict[int, float] = {}
            # 文本路排名序：菜名命中（② 前半，命中即标题精确匹配）在前，
            # 其余按「该路覆盖数降序 → recipe_id 升序」补全（稳定）
            text_ranked = sorted(title_matched) + sorted(
                (rid for rid in text_rank_extra if rid not in title_matched),
                key=lambda rid: (-text_rank_extra[rid], rid),
            )
            for path_name, ranked_ids in (
                ("coverage", path_coverage),
                ("text", text_ranked),
                ("vector", path_vector),
            ):
                for rank, rid in enumerate(ranked_ids, start=1):
                    rrf_score[rid] = rrf_score.get(rid, 0.0) + 1.0 / (60 + rank)
                    fusion_ranks.setdefault(rid, {})[path_name] = rank
            candidates.sort(key=lambda c: (-rrf_score.get(c["recipe_id"], 0.0), c["recipe_id"]))
            for c in candidates:
                c["_fusion_ranks"] = fusion_ranks.get(c["recipe_id"], {})
        else:
            # 固定优先级（缺省，行为与升级前逐字节一致）：覆盖数降序 → 菜名命中 → 向量相似度 → id 升序
            candidates.sort(
                key=lambda c: (
                    -c["covered_count"],
                    not c["matched_by_title"],
                    -c["_vector_sim"],
                    c["recipe_id"],
                )
            )
        # Top-K 截断（spec：默认 ≤8 条返回，下游 hard_filter/rank 在此集合内工作）
        return candidates[:top_k]
    except Exception as exc:  # noqa: BLE001 —— 召回失败返回空集，由上层标注降级
        logger.error("retrieve candidates failed: %s", exc)
        return []


__all__ = [
    "DEFAULT_LIMIT",
    "DEFAULT_TOP_K",
    "TEXT_MATCH_LIMIT",
    "ensure_embeddings",
    "extract_ingredient_names_from_text",
    "match_ingredients_in_text",
    "retrieve_candidates",
]
