"""推荐排序模块（硬过滤先于排序，🔴 顺序不可颠倒）。

职责：
    - hard_filter：布尔硬过滤（过敏原/忌口/难度上限 + 设备），绝不实现为降权打分
      （spec D9 红线）：过敏原/忌口/难度在数据库层以 SQL 布尔 WHERE 完成（JSONB 数组
      用 `?|` 操作符 + bindparam）；设备维度在候选层以「差集非空即排除」的布尔语义
      完成（含基础工具豁免集，见 BASIC_TOOLS_EXEMPT / DEVICE_CLASS_HINTS）；含致敏原
      或缺设备的菜谱完全排除（完全不出现，非降权）；
    - weighted_rank：7 因子加权排序（coverage/expiring/taste/goal/difficulty/history/popularity），
      权重从 remote_config `rank.weights` 读取（缺失用默认值），冷启动时 history 权重按比例
      摊给 coverage/popularity；每条产出 ≥1 条中文 rank_reasons 与三档 match_level，取 Top 8；
    - E.9 反馈立即生效：weighted_rank 支持可选 feedback_penalty（recipe_id→扣分），
      dislike 的菜谱总分 -0.5 并追加理由「你曾表示不喜欢」；配套 load_feedback_penalty
      从 recipe_feedback 表加载该扣分映射。

结构防降权保证：
    weighted_rank 的输入集只能是 hard_filter 的输出集（过滤集合之外的对象根本不进入本函数）。
"""

from __future__ import annotations

from sqlalchemy import String, bindparam, select
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import Session
from sqlalchemy.sql.elements import ColumnElement

from app.core.db import SessionLocal
from app.core.logging import get_logger
from app.models import Recipe, RecipeFeedback, RemoteConfig
from app.safety.types import SafetyProfile

logger = get_logger(__name__)

# 7 因子默认权重（remote_config rank.weights 缺失时兜底，与 seed/configs 保持一致）
DEFAULT_WEIGHTS: dict[str, float] = {
    "coverage": 0.30,
    "expiring": 0.15,
    "taste": 0.15,
    "goal": 0.15,
    "difficulty": 0.10,
    "history": 0.10,
    "popularity": 0.05,
}

# 配置键
WEIGHTS_CONFIG_KEY = "rank.weights"

# 推荐结果条数上限（spec：默认 ≤8 条，不足时如实说明不填充）
TOP_N = 8

# 难度上限默认值（无档案时用于难度因子归一化的中性参照）
_DEFAULT_DIFFICULTY_CAP = 3

# E.9 dislike 反馈惩罚分值（反馈立即生效：dislike 菜谱总分 -0.5）
FEEDBACK_DISLIKE_PENALTY = 0.5

# ---------------------------------------------------------------------------
# 设备维度硬过滤（缺陷 M2/P6/S8 修复：用户档案仅持炒锅时，需燃气灶的菜谱必须完全不出现）
# ---------------------------------------------------------------------------

# 灶具/电器/锅具类判定词素（包含式）：菜谱 equipment 词项命中任一词素才参与
# 「菜谱设备 − 用户档案设备」差集判定，落实「仅对灶具/电器/锅具类过滤」的口径。
# 覆盖：锅类（炒锅/蒸锅/汤锅/炖锅/高压锅/平底锅/砂锅/电压力锅…）、灶具（燃气灶/
# 电磁炉/灶台）、电器（微波炉/烤箱/电饭煲/空气炸锅/破壁机/料理机/搅拌机…）。
DEVICE_CLASS_HINTS: tuple[str, ...] = ("锅", "灶", "炉", "煲", "机", "烤箱", "蒸箱")

# 基础工具豁免集（包含式词素）：菜谱 equipment 词表含碗/盘/碟/刀/砧板/勺/筷子等
# 几乎家家都有或可徒手替代的基础工具，以及锡纸/油纸/保鲜膜/模具等耗材——若参与差集
# 判定会把所有菜滤光；命中任一词素的设备词项不参与设备过滤（豁免优先于词素判定）。
# 另含少量语料误判为工具的非设备词（底料/调料/二锅头/用水）兜底。
BASIC_TOOLS_EXEMPT: frozenset[str] = frozenset({
    "碗", "盆", "盘", "碟", "刀", "砧板", "案板", "勺", "筷子", "铲", "杯",
    "筛", "网", "纸", "膜", "袋", "布", "手套", "模具", "温度计", "秤",
    "量杯", "打蛋器", "刮刀", "擀面杖", "锡纸", "蒸笼", "刷",
    "二锅头", "底料", "调料", "用水",
})


def load_weights(session: Session | None = None) -> dict[str, float]:
    """从 remote_config 读取排序权重（函数）。

    说明：
        读取 `rank.weights` 配置；表缺失/异常时返回默认权重（保证链路可降级）。
        阶段一不引入 Redis，进程内消费 60s 内生效语义由调用频率保证（spec D6）。

    参数：
        session：数据库会话；None 时自建短会话。

    返回值：
        dict[str, float]：7 因子权重字典。

    异常：
        不抛出（任何异常回退 DEFAULT_WEIGHTS）。
    """
    try:
        if session is None:
            with SessionLocal() as own_session:
                return load_weights(own_session)
        row = session.execute(
            select(RemoteConfig).where(RemoteConfig.config_key == WEIGHTS_CONFIG_KEY)
        ).scalar_one_or_none()
        if row and isinstance(row.value, dict):
            weights = dict(DEFAULT_WEIGHTS)
            for key in DEFAULT_WEIGHTS:
                value = row.value.get(key)
                if isinstance(value, (int, float)) and 0 <= float(value) <= 1:
                    weights[key] = float(value)
            return weights
        return dict(DEFAULT_WEIGHTS)
    except Exception as exc:  # noqa: BLE001 —— 配置读取失败回退默认权重
        logger.warning("load rank weights failed, fallback to defaults: %s", exc)
        return dict(DEFAULT_WEIGHTS)


def _is_filterable_device(name: str) -> bool:
    """判定菜谱设备词项是否参与设备硬过滤差集（函数）。

    说明：
        参与条件 = 命中灶具/电器/锅具类词素（DEVICE_CLASS_HINTS）且未命中基础工具
        豁免集（BASIC_TOOLS_EXEMPT，优先判定）；碗/盘/刀/砧板等基础工具与耗材恒不参与。

    参数：
        name：菜谱 equipment 中的单个设备词项（已去空白）。

    返回值：
        bool：True 表示参与差集判定；False 表示豁免。

    异常：
        无。
    """
    for token in BASIC_TOOLS_EXEMPT:
        if token in name:
            return False
    return any(hint in name for hint in DEVICE_CLASS_HINTS)


def find_missing_equipment(recipe_equipment: list, user_equipment: list) -> list[str]:
    """计算菜谱设备中用户缺失的灶具/电器/锅具类设备（函数）。

    说明：
        设备维度硬过滤的核心判定（布尔差集语义）：
        - 仅对灶具/电器/锅具类词项做差集（基础工具/耗材经豁免集自动豁免）；
        - 满足条件：词项在用户设备集合中精确命中，或与用户任一设备词构成
          双向包含（用户「炒锅」可覆盖菜谱「普通的炒锅」/泛化「锅」等语料变体，
          避免 406 道菜谱的语料长尾写法误滤）；
        - 菜谱设备顺序保持输出（供「缺少设备：燃气灶」类原因明细展示）。

    参数：
        recipe_equipment：菜谱 equipment 列表（JSONB 反序列化，可 None）。
        user_equipment：用户档案设备列表（可 None/空）。

    返回值：
        list[str]：用户缺失且参与判定的设备词项列表（保持菜谱顺序，去重）；
        用户设备为空时恒返回 []（未设置档案不启用设备过滤，避免新用户全空结果）。

    异常：
        无（元素非字符串时按 str() 容错处理）。
    """
    user_set = {str(u).strip() for u in (user_equipment or []) if str(u).strip()}
    if not user_set:
        return []
    missing: list[str] = []
    for item in recipe_equipment or []:
        name = str(item).strip()
        if not name or name in missing:
            continue
        if not _is_filterable_device(name):
            continue
        if name in user_set:
            continue
        if any(u in name or name in u for u in user_set):
            continue
        missing.append(name)
    return missing


def hard_filter(
    session: Session,
    candidates: list[dict],
    profile: SafetyProfile,
) -> tuple[list[dict], dict[str, int]]:
    """布尔硬过滤（函数）。

    说明：
        在数据库层以布尔 WHERE 完成（🔴 非打分、非降权）：
        - NOT (recipe.allergen_codes ?| :codes)：菜谱自带致敏原命中即排除；
        - NOT (recipe.ingredient_allergen_codes ?| :codes)：食材聚合致敏原命中即排除；
        - NOT (recipe.dietary_flags ?| :restrictions)：忌口标记命中即排除；
        - difficulty <= :cap：难度上限（无上限时跳过该条件）；
        - 设备维度（候选层布尔差集，在 SQL 过滤同层叠加）：仅当档案设备清单非空时
          生效——菜谱设备中存在用户缺失的灶具/电器/锅具类词项（差集非空）即整条
          排除，绝不降权；档案设备为空（未设置）时该维度不生效（避免新用户全空结果）。
        用户集合为空时对应条件自动跳过（空集合 `?|` 无命中语义，跳过以省查询）。

    参数：
        session：数据库会话。
        candidates：retrieve_candidates 产出的候选字典列表（使用 recipe_id 与 equipment）。
        profile：用户安全档案（过敏原/忌口/难度上限/设备清单）。

    返回值：
        tuple[list[dict], dict[str, int]]：
            (过滤后候选列表【保持原候选顺序】, filtered_by 计数)；
            counts={"allergen": n, "dietary_restriction": n, "difficulty": n, "equipment": n}。

    异常：
        不抛出（任何异常按「宁少不错」返回空集 + 已计维度计数，交由上层降级）。
    """
    counts = {"allergen": 0, "dietary_restriction": 0, "difficulty": 0, "equipment": 0}
    if not candidates:
        return [], counts
    candidate_ids = [int(c["recipe_id"]) for c in candidates]
    allergen_codes = [str(c) for c in (profile.user_allergen_codes or [])]
    restrictions = [str(c) for c in (profile.dietary_restrictions or [])]
    user_equipment = [str(e).strip() for e in (profile.equipment or []) if str(e).strip()]

    try:
        base = select(Recipe.id).where(Recipe.id.in_(candidate_ids))

        # 单条件计数（供前端「显示被我过滤掉的菜」与验收取证）
        if allergen_codes:
            hit_allergen = base.where(
                _overlap(Recipe.allergen_codes, allergen_codes)
                | _overlap(Recipe.ingredient_allergen_codes, allergen_codes)
            )
            counts["allergen"] = int(len(session.execute(hit_allergen).all()))
        if restrictions:
            hit_diet = base.where(_overlap(Recipe.dietary_flags, restrictions))
            counts["dietary_restriction"] = int(len(session.execute(hit_diet).all()))
        if profile.difficulty_cap:
            over_difficulty = base.where(Recipe.difficulty > int(profile.difficulty_cap))
            counts["difficulty"] = int(len(session.execute(over_difficulty).all()))
        # 设备维度单条件计数：候选字典自带 equipment 列表，纯 Python 差集判定
        missing_equipment: dict[int, list[str]] = {}
        if user_equipment:
            for cand in candidates:
                missing = find_missing_equipment(cand.get("equipment") or [], user_equipment)
                if missing:
                    missing_equipment[int(cand["recipe_id"])] = missing
            counts["equipment"] = len(missing_equipment)

        # 过滤后集合：全部条件叠加的布尔过滤（保持原候选顺序输出）
        stmt = base
        if allergen_codes:
            stmt = stmt.where(
                ~_overlap(Recipe.allergen_codes, allergen_codes)
            ).where(
                ~_overlap(Recipe.ingredient_allergen_codes, allergen_codes)
            )
        if restrictions:
            stmt = stmt.where(~_overlap(Recipe.dietary_flags, restrictions))
        if profile.difficulty_cap:
            stmt = stmt.where(Recipe.difficulty <= int(profile.difficulty_cap))
        filtered_ids = {int(row[0]) for row in session.execute(stmt).all()}

        filtered = [
            c for c in candidates
            if int(c["recipe_id"]) in filtered_ids and int(c["recipe_id"]) not in missing_equipment
        ]
        return filtered, counts
    except Exception as exc:  # noqa: BLE001 —— 硬过滤失败按致命降级：返回空结果集（宁少不错）
        logger.error("hard_filter failed, fallback to empty set: %s", exc)
        return [], counts


def _overlap(column: ColumnElement, values: list[str]) -> ColumnElement:
    """构造 JSONB 数组 `?|` 重叠表达式（函数）。

    说明：
        `?|` 操作符右侧为 text[]（bindparam + psycopg2 数组适配），
        语义：JSONB 数组与给定字符串数组存在任一交集即 True。

    参数：
        column：JSONB 数组列（allergen_codes / dietary_flags 等）。
        values：用户侧字符串集合（非空列表）。

    返回值：
        ColumnElement：可用于 WHERE 的布尔表达式。

    异常：
        无。
    """
    return column.op("?|")(
        bindparam("overlap_values", value=list(values), type_=ARRAY(String))
    )


def weighted_rank(
    filtered: list[dict],
    ctx: SafetyProfile | None = None,
    weights: dict[str, float] | None = None,
    feedback_penalty: dict[int, float] | None = None,
) -> list[dict]:
    """7 因子加权排序（函数）。

    说明：
        仅作用于 hard_filter 输出集（结构上无法给被过滤项打分）。
        因子实现（阶段一无档案/无库存，多项取中性值并在注释说明）：
        - coverage：主料覆盖数 / 主料总数；
        - expiring：0.0（无库存数据）；
        - taste：0.5（无口味档案，中性）；
        - goal：0.5（无饮食目标，中性）；
        - difficulty：1 − |菜谱难度 − 上限| / 上限（无上限时 0.5）；
        - history：0.0（冷启动无历史）→ 其权重按比例摊给 coverage 与 popularity；
        - popularity：0.5（无点击数据，中性）。
        E.9 反馈立即生效：feedback_penalty 命中的菜谱（用户 dislike 过）在总分上
        直接扣减对应分值（load_feedback_penalty 产出 dislike → -0.5），并在
        rank_reasons 追加「你曾表示不喜欢」。

    参数：
        filtered：hard_filter 输出的候选列表。
        ctx：用户安全档案（difficulty_cap 参与难度因子）。
        weights：7 因子权重（None 时使用默认权重）。
        feedback_penalty：反馈惩罚映射 {recipe_id: 扣分}（None/空时不惩罚）。

    返回值：
        list[dict]：排序后结果列表（≤Top 8），每条在候选字段基础上追加：
            rank_score/rank_reasons/match_level/covered_ingredients/missing_ingredients。

    异常：
        不抛出（单条排序异常跳过该条，不中断整体）。
    """
    w = dict(weights) if weights else dict(DEFAULT_WEIGHTS)
    penalty_map = feedback_penalty or {}
    # 冷启动：history 无数据，其权重按 coverage:popularity 的既有比例摊给两者（§7.3）
    hist_w = w.get("history", 0.10)
    if hist_w > 0:
        cov_p, pop_p = w.get("coverage", 0.0), w.get("popularity", 0.0)
        denom = cov_p + pop_p
        if denom > 0:
            w["coverage"] = cov_p + hist_w * cov_p / denom
            w["popularity"] = pop_p + hist_w * pop_p / denom
        else:
            w["coverage"] += hist_w
        w["history"] = 0.0

    cap = ctx.difficulty_cap if ctx and ctx.difficulty_cap else None
    results: list[dict] = []
    for cand in filtered:
        try:
            main_names = cand.get("main_ingredient_names") or []
            total_main = len(main_names)
            covered_count = int(cand.get("covered_count") or 0)
            missing_names = [n for n in main_names if n not in (cand.get("covered_names") or [])]
            coverage = (covered_count / total_main) if total_main > 0 else 0.0

            difficulty_score = (
                max(0.0, 1.0 - abs(int(cand["difficulty"]) - cap) / cap) if cap else 0.5
            )
            score = (
                w.get("coverage", 0.0) * coverage
                + w.get("expiring", 0.0) * 0.0          # 阶段一无临期数据
                + w.get("taste", 0.0) * 0.5             # 阶段一无口味档案
                + w.get("goal", 0.0) * 0.5              # 阶段一无饮食目标
                + w.get("difficulty", 0.0) * difficulty_score
                + w.get("history", 0.0) * 0.0           # 冷启动无历史
                + w.get("popularity", 0.0) * 0.5        # 阶段一无热度数据
            )

            # E.9 反馈立即生效：dislike 过的菜谱在总分上直接扣减（默认 -0.5）
            penalty = float(penalty_map.get(int(cand["recipe_id"]), 0.0))
            if penalty:
                score -= penalty

            # 三档划分：missing==0 现在就能做；1~2 差 1–2 样；≥3 需要多买（覆盖率≥0.3 才进 need_more 口径）
            missing_n = len(missing_names)
            if missing_n == 0:
                match_level = "can_cook_now"
            elif missing_n <= 2:
                match_level = "missing_1_2"
            else:
                match_level = "need_more"

            # 可解释理由（≥1 条）
            reasons: list[str] = []
            if covered_count > 0:
                reasons.append(f"用掉 {covered_count} 样你现有的食材")
            if match_level == "can_cook_now":
                reasons.append("现在就能做，无需额外购买")
            elif match_level == "missing_1_2":
                reasons.append(f"只差 {missing_n} 样食材即可做")
            if cand.get("matched_by_title"):
                reasons.append("菜名与你的搜索直接相关")
            if int(cand.get("difficulty") or 5) <= 2:
                reasons.append("做法简单，容易上手")
            time_minutes = cand.get("time_minutes")
            if time_minutes and int(time_minutes) <= 20:
                reasons.append(f"约 {int(time_minutes)} 分钟即可上桌")
            if penalty > 0:
                reasons.append("你曾表示不喜欢")
            if not reasons:
                reasons.append("综合匹配你的食材组合")

            item = dict(cand)
            item.update(
                {
                    "rank_score": round(score, 4),
                    "rank_reasons": reasons,
                    "match_level": match_level,
                    "covered_ingredients": cand.get("covered_names") or [],
                    "missing_ingredients": missing_names,
                }
            )
            results.append(item)
        except Exception as exc:  # noqa: BLE001 —— 单条异常不中断整体排序
            logger.warning("weighted_rank skip candidate %s: %s", cand.get("recipe_id"), exc)

    # 排序：分数降序 → 覆盖数降序 → recipe_id 升序（稳定）；取 Top 8
    results.sort(key=lambda r: (-r["rank_score"], -r["covered_count"], r["recipe_id"]))
    return results[:TOP_N]


def load_feedback_penalty(session: Session, user_id: int) -> dict[int, float]:
    """加载用户 dislike 菜谱的排序惩罚映射（E.9，函数）。

    说明：
        查询 recipe_feedback 表中该用户全部 feedback_type='dislike' 的菜谱，
        返回 {recipe_id: FEEDBACK_DISLIKE_PENALTY}，供 weighted_rank 的
        feedback_penalty 参数消费（反馈立即生效，无缓存延迟）。
        ⚠️ 接线备注：subgraphs/recommend.py 的 recipe_rank 节点属并行代理文件，
        本阶段不改——后续 graph 阶段在该节点中按 state 的 user_id 调用本函数并把
        结果传入 weighted_rank(..., feedback_penalty=...) 即可完成接线。

    参数：
        session：数据库会话。
        user_id：用户 ID（user 表主键）。

    返回值：
        dict[int, float]：{recipe_id: 扣分}；无 dislike 记录时为空映射。

    异常：
        不抛出（查询异常告警并返回空映射，惩罚缺失不影响排序主链路）。
    """
    try:
        rows = session.execute(
            select(RecipeFeedback.recipe_id).where(
                RecipeFeedback.user_id == int(user_id),
                RecipeFeedback.feedback_type == "dislike",
            )
        ).all()
    except Exception as exc:  # noqa: BLE001 —— 惩罚加载失败不影响排序主链路
        logger.warning("load_feedback_penalty failed: %s", exc)
        return {}
    return {int(rid): FEEDBACK_DISLIKE_PENALTY for (rid,) in rows}
