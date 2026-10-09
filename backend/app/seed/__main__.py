"""种子数据执行入口（python -m app.seed）。

职责：
    1. 连接系统库 postgres，检查并创建 aicook 业务库（不存在则 CREATE DATABASE）；
    2. 调用 app.core.migrations.ensure_schema() 以 Alembic 管理表结构
       （空库 upgrade 全量建表 / create_all 存量库 stamp 兼容，见 02-V1.1 §10.1；
       禁止在本脚本手工改表，create_all 已废弃）；
    3. 依次执行各种子模块，幂等策略：
       - remote_config：按 config_key upsert；
       - risk_rule：按 (rule_code, version) upsert；
       - risk_message：按 message_id upsert；
       - ingredient：按 name 存在则跳过（连带别名/营养）；
       - recipe：按 title 存在则跳过（连带食材/步骤）；
       - HowToCook 语料菜谱：按 title 存在则跳过（连带食材行/步骤行）；
       - admin_user：按 username 存在则跳过（哈希非 passlib 格式时平滑升级）；
       - technique_library：按 name 存在则跳过（阶段二模块 O）；
       - ingredient_property：按 ingredient_id 存在则跳过（阶段二模块 O）；
       - flavor_pairing_rule：按 (a_id, b_id, relation) 存在则跳过（阶段二模块 O）。
    重复执行不重复插入、不报错（第二次运行新增统计为 0）。
"""

import sys

from sqlalchemy import create_engine, text

from app.core.config import settings
from app.core.db import SessionLocal
from app.core.logging import configure_logging, get_logger
from app.core.migrations import ensure_schema
from app.models import AdminUser, Ingredient, Recipe, RemoteConfig, RiskMessage, RiskRule

# 装配日志与 logger（种子脚本独立于 FastAPI 启动）
configure_logging()
logger = get_logger("app.seed")

# 全局新增计数器（幂等验证证据）
counters = {
    "ingredient": 0, "alias": 0, "nutrition": 0,
    "recipe": 0, "recipe_ingredient": 0, "recipe_step": 0,
    "corpus_recipe": 0, "corpus_recipe_ingredient": 0, "corpus_recipe_step": 0,
    "corpus_ingredient_new": 0,
    "risk_rule": 0, "risk_message": 0, "remote_config": 0, "admin_user": 0,
    "technique_library": 0, "ingredient_property": 0, "flavor_pairing_rule": 0,
}


def ensure_database() -> None:
    """确保业务库 aicook 存在（函数）。

    说明：
        连接 postgres 系统库查询 pg_database，不存在则 CREATE DATABASE aicook。

    异常：
        数据库连接失败时向上抛出（用户需先启动 PostgreSQL 服务）。
    """
    admin_engine = create_engine(settings.admin_database_url, isolation_level="AUTOCOMMIT")
    try:
        with admin_engine.connect() as conn:
            exists = conn.execute(
                text("SELECT 1 FROM pg_database WHERE datname = :name"), {"name": settings.DB_NAME}
            ).scalar()
            if not exists:
                # 标识符已按约定由 .env 提供（内部演示环境），使用 f-string 仅为 CREATE DATABASE 语法所需
                conn.execute(text(f'CREATE DATABASE "{settings.DB_NAME}"'))
                print(f"[seed] 数据库 {settings.DB_NAME} 不存在，已创建。")
            else:
                print(f"[seed] 数据库 {settings.DB_NAME} 已存在。")
    finally:
        admin_engine.dispose()


def seed_ingredients(session) -> None:
    """填充食材 / 别名 / 营养数据（函数）。

    幂等：
        ingredient 按 name 存在则跳过（连带别名与营养行）。

    异常：
        数据库操作异常向上抛出并回滚。
    """
    # 延迟导入种子数据模块
    from app.seed.ingredients import (
        ALIASES,
        INGREDIENTS,
        NUTRITION,
        NUTRITION_DATA_SOURCE,
        NUTRITION_SOURCE_LICENSE,
    )

    existing = {row[0] for row in session.query(Ingredient.name).all()}
    name_to_obj: dict[str, Ingredient] = {}
    for name, category, codes, verified in INGREDIENTS:
        if name in existing:
            # 已存在 → 跳过（含别名/营养），保持幂等
            name_to_obj[name] = session.query(Ingredient).filter(Ingredient.name == name).one()
            continue
        ingredient = Ingredient(
            name=name, category=category, allergen_codes=list(codes), allergen_verified=verified
        )
        for alias in ALIASES.get(name, []):
            from app.models import IngredientAlias

            ingredient.aliases.append(IngredientAlias(alias=alias))
        if name in NUTRITION:
            kcal, protein, fat, carbs, sodium = NUTRITION[name]
            from app.models import IngredientNutrition

            ingredient.nutrition = IngredientNutrition(
                kcal_100g=kcal, protein_g=protein, fat_g=fat, carbs_g=carbs, sodium_mg=sodium,
                data_source=NUTRITION_DATA_SOURCE, source_license=NUTRITION_SOURCE_LICENSE,
            )
        session.add(ingredient)
        name_to_obj[name] = ingredient
        counters["ingredient"] += 1
        counters["alias"] += len(ALIASES.get(name, []))
        if name in NUTRITION:
            counters["nutrition"] += 1
    session.commit()
    print(f"[seed] 食材新增 {counters['ingredient']} 条 / 别名新增 {counters['alias']} 条 / 营养新增 {counters['nutrition']} 条")
    # 供菜谱构建使用：全量名称 → ORM 映射（含历史已存在食材）
    all_map = {obj.name: obj for obj in session.query(Ingredient).all()}
    seed_recipes_map_cache = all_map  # noqa: F841 —— 显式命名说明用途
    globals()["_INGREDIENT_MAP"] = all_map


def seed_recipes(session) -> None:
    """填充菜谱 / 菜谱食材 / 步骤（函数）。

    幂等：
        recipe 按 title 存在则跳过（连带食材与步骤）。

    异常：
        引用未定义食材时抛 KeyError；数据库异常向上抛出并回滚。
    """
    from app.seed.recipes import RECIPES, build_recipes

    existing = {row[0] for row in session.query(Recipe.title).all()}
    new_defs = [r for r in RECIPES if r[0] not in existing]
    if not new_defs:
        print("[seed] 菜谱新增 0 道（全部已存在）")
        return
    # build_recipes 需要食材映射（含 id），由上一个模块写入 globals
    ingredient_map = globals()["_INGREDIENT_MAP"]
    recipes = build_recipes(ingredient_map)
    for recipe in recipes:
        if recipe.title in existing:
            continue
        counters["recipe_ingredient"] += len(recipe.ingredients)
        counters["recipe_step"] += len(recipe.steps)
        session.add(recipe)
        counters["recipe"] += 1
    session.commit()
    print(
        f"[seed] 菜谱新增 {counters['recipe']} 道 / 食材引用新增 {counters['recipe_ingredient']} 条 / "
        f"步骤新增 {counters['recipe_step']} 条"
    )


def seed_corpus(session) -> None:
    """导入 HowToCook 公开菜谱语料（函数，05-V1.1 §5.1④/§5.6 对齐）。

    说明：
        - 语料缓存目录（backend/data/HowToCook）不存在时自动按
          「GitHub 直连 → 镜像加速」克隆；下载失败则告警跳过（不阻断 seed）；
        - 解析 md → 用量清洗（CT-6 全量化，适量按调料映射表量化）→
          title 幂等去重 → 导入 published 菜谱（来源标注、封面留空）；
        - 未命中食材库的原料自动建 minimal ingredient（allergen_verified=false）；
        - 末尾输出库级质量断言：语料菜规模 / source_label 一致性 /
          recipe_ingredient 双缺用量行（全库口径应为 0）。

    参数：
        session：SQLAlchemy 会话。

    返回值：
        None。

    异常：
        数据库操作异常向上抛出并回滚（由 main 统一处理）。
    """
    from sqlalchemy import func

    from app.seed import corpus_howtocook

    stats = corpus_howtocook.import_corpus(session)
    if not stats.get("corpus_ready"):
        print("[seed] 语料未就绪（下载失败），跳过语料导入。")
        return
    counters["corpus_recipe"] += stats["imported"]
    counters["corpus_ingredient_new"] += stats["ing_new"]
    session.commit()
    print(
        f"[seed][corpus] md 总数 {stats['md_total']} / 解析成功 {stats['parsed']} / "
        f"导入 {stats['imported']} / 跳过 {len(stats['skipped'])}"
    )
    hit_rate = (stats["ing_hits"] / stats["ing_refs"] * 100) if stats["ing_refs"] else 0.0
    print(
        f"[seed][corpus] 食材引用 {stats['ing_refs']}（命中既有 {stats['ing_hits']} / "
        f"自动新建 {stats['ing_new']}，命中率 {hit_rate:.1f}%）"
    )
    print(
        f"[seed][corpus] 用量清洗：区间 {stats['amount_interval']} / 单值 {stats['amount_value']} / "
        f"量词 {stats['amount_count']} / 勺 {stats['amount_spoon']} / "
        f"适量量化 {stats['amount_quantize']} / 无法解析 {stats['amount_skipped']} / "
        f"水类忽略 {stats['water_ignored']}"
    )
    if stats.get("new_ingredient_names"):
        print(f"[seed][corpus] 自动新建食材示例：{stats['new_ingredient_names'][:15]}")
    if stats.get("skipped_samples"):
        print("[seed][corpus] 跳过示例（≤10 条）：")
        for name, reason in stats["skipped_samples"]:
            print(f"[seed][corpus]   - {name}：{reason}")

    # ---- 库级质量断言（任务 4.5 口径） ----
    # 语料菜识别：source_label 相同（与手写 45 道同值），以手写标题集排除区分
    from app.seed.recipes import RECIPES as _HAND_RECIPES
    hand_titles = [r[0] for r in _HAND_RECIPES]
    corpus_count = session.query(func.count(Recipe.id)).filter(
        Recipe.source_label == corpus_howtocook.SOURCE_LABEL,
        Recipe.status == "published",
        Recipe.title.notin_(hand_titles),
    ).scalar()
    total_recipes = session.query(func.count(Recipe.id)).scalar()
    published_total = session.query(func.count(Recipe.id)).filter(Recipe.status == "published").scalar()
    from app.models import RecipeIngredient as _RI
    double_missing = session.query(func.count(_RI.id)).filter(
        _RI.amount_value.is_(None),
        _RI.amount_min.is_(None),
    ).scalar()
    print(
        f"[seed][corpus][断言] recipe 总数 {total_recipes}（published {published_total}）；"
        f"语料来源 published {corpus_count} 篇（目标 ≥{corpus_howtocook.CORPUS_TARGET_MIN}）；"
        f"双缺用量行（全库）= {double_missing}（要求 0）"
    )


def seed_safety(session) -> None:
    """填充风控话术与规则（函数）。

    幂等：
        risk_message 按 message_id upsert；risk_rule 按 (rule_code, version) upsert。

    异常：
        数据库操作异常向上抛出并回滚。
    """
    from app.seed.safety import DISCLAIMER_ID, RISK_MESSAGES, RISK_RULES, RULE_VERSION

    # 话术先于规则（risk_rule 外键依赖 risk_message.message_id）
    for item in RISK_MESSAGES:
        obj = session.query(RiskMessage).filter(RiskMessage.message_id == item["message_id"]).one_or_none()
        if obj is None:
            session.add(RiskMessage(
                message_id=item["message_id"], category=item["category"], title=item["title"],
                body=item["body"], correct_action=item["correct_action"],
                after_consumption_advice=item["after_consumption_advice"],
                disclaimer_id=DISCLAIMER_ID,
            ))
            counters["risk_message"] += 1
        else:
            # upsert：更新内容字段
            obj.category, obj.title, obj.body = item["category"], item["title"], item["body"]
            obj.correct_action, obj.after_consumption_advice = (
                item["correct_action"], item["after_consumption_advice"],
            )
    session.flush()

    for item in RISK_RULES:
        obj = (
            session.query(RiskRule)
            .filter(RiskRule.rule_code == item["rule_code"], RiskRule.version == RULE_VERSION)
            .one_or_none()
        )
        if obj is None:
            session.add(RiskRule(
                rule_code=item["rule_code"], category=item["category"],
                stage_scope=item["stage_scope"], trigger_condition=item["trigger_condition"],
                response_message_id=item["response_message_id"], block=item["block"],
                risk_level=item["risk_level"], evidence_ref=item["evidence_ref"],
                signed_by_expert=False, version=RULE_VERSION, enabled=True,
            ))
            counters["risk_rule"] += 1
        else:
            # upsert：更新规则内容
            obj.category, obj.stage_scope = item["category"], item["stage_scope"]
            obj.trigger_condition, obj.response_message_id = item["trigger_condition"], item["response_message_id"]
            obj.block, obj.risk_level, obj.evidence_ref = item["block"], item["risk_level"], item["evidence_ref"]
    session.commit()
    print(f"[seed] 风控话术新增/更新 {len(RISK_MESSAGES)} 条（新增 {counters['risk_message']}）；"
          f"规则新增/更新 {len(RISK_RULES)} 条（新增 {counters['risk_rule']}）")


def seed_innovation(session) -> None:
    """填充模块 O（AI 菜品创新）三表数据（函数）。

    说明：
        - technique_library：24 条经典技法白名单（按 name 幂等跳过）；
        - ingredient_property：对 10 分类每类取 id 升序前 16 条（共约 160 条）
          按三级规则（精确表 → 子串规则 → 分类默认）启发式标注五属性，
          按 ingredient_id 幂等跳过；
        - flavor_pairing_rule：63 条搭配规则（recommend 40 / conflict 15 / taboo 8），
          名称解析失败的条目告警跳过，按 (a_id, b_id, relation) 幂等跳过；
          rationale 全部为烹饪学表述，不含中医性味归经与中毒类断言。

    参数：
        session：SQLAlchemy 会话。

    返回值：
        None。

    异常：
        数据库操作异常向上抛出并回滚（由 main 统一处理）。
    """
    from app.models import FlavorPairingRule, IngredientProperty, TechniqueLibrary
    from app.seed.innovation import (
        PAIRING_RULES,
        PER_CATEGORY_LIMIT,
        SOURCE_NOTE,
        TECHNIQUES,
        derive_property,
    )

    # ---- 技法白名单（按 name 幂等）----
    existing_techniques = {row[0] for row in session.query(TechniqueLibrary.name).all()}
    for name, description, in_whitelist in TECHNIQUES:
        if name in existing_techniques:
            continue
        session.add(TechniqueLibrary(name=name, description=description,
                                     in_whitelist=in_whitelist))
        counters["technique_library"] += 1
    session.flush()

    # ---- 食材五属性（每分类取前 N 条，按 ingredient_id 幂等）----
    existing_property_ids = {
        row[0] for row in session.query(IngredientProperty.ingredient_id).all()
    }
    from app.models import Ingredient

    for category in (
        "veg", "meat", "seafood", "egg_milk", "soy",
        "staple", "seasoning", "dry", "frozen", "other",
    ):
        rows = (
            session.query(Ingredient)
            .filter(Ingredient.category == category, Ingredient.is_active.is_(True))
            .order_by(Ingredient.id)
            .limit(PER_CATEGORY_LIMIT)
            .all()
        )
        for ing in rows:
            if ing.id in existing_property_ids:
                continue
            props = derive_property(ing.name, ing.category)
            session.add(IngredientProperty(
                ingredient_id=ing.id,
                texture=props.get("texture"),
                moisture=props.get("moisture"),
                flavor=props.get("flavor"),
                heat_tolerance=props.get("heat_tolerance"),
                oil_absorption=props.get("oil_absorption"),
                source_note=SOURCE_NOTE,
            ))
            existing_property_ids.add(ing.id)
            counters["ingredient_property"] += 1
    session.flush()

    # ---- 食材搭配规则（按 (a_id, b_id, relation) 幂等）----
    from sqlalchemy import func

    # 收集全部规则引用的食材名，一次查询建 name→id 映射（不存在的告警跳过）
    referenced_names = {item[0] for item in PAIRING_RULES} | {item[1] for item in PAIRING_RULES}
    name_to_id = {
        row[0]: row[1]
        for row in session.query(Ingredient.name, Ingredient.id)
        .filter(Ingredient.name.in_(referenced_names))
        .all()
    }
    missing = sorted(referenced_names - set(name_to_id))
    if missing:
        print(f"[seed][innovation] 搭配规则引用的食材不在库中（跳过相关条目）：{missing}")

    existing_pairs = {
        (row[0], row[1], row[2])
        for row in session.query(
            FlavorPairingRule.ingredient_a_id,
            FlavorPairingRule.ingredient_b_id,
            FlavorPairingRule.relation,
        ).all()
    }
    for name_a, name_b, relation, technique, rationale, weight in PAIRING_RULES:
        id_a, id_b = name_to_id.get(name_a), name_to_id.get(name_b)
        if id_a is None or id_b is None:
            continue
        if (id_a, id_b, relation) in existing_pairs:
            continue
        session.add(FlavorPairingRule(
            ingredient_a_id=id_a, ingredient_b_id=id_b, relation=relation,
            technique_suggestion=technique, rationale=rationale, weight=weight,
            signed_by_expert=False,
        ))
        existing_pairs.add((id_a, id_b, relation))
        counters["flavor_pairing_rule"] += 1
    session.commit()

    rule_count = session.query(func.count(FlavorPairingRule.id)).scalar()
    print(
        f"[seed][innovation] 技法白名单新增 {counters['technique_library']} 条 / "
        f"食材属性新增 {counters['ingredient_property']} 条 / "
        f"搭配规则新增 {counters['flavor_pairing_rule']} 条（库内合计 {rule_count} 条）"
    )


def seed_configs(session) -> None:
    """填充远程开关配置与内置管理员（函数）。

    幂等：
        remote_config 按 config_key upsert；admin_user 按 username 存在则跳过
        （password_hash 非 passlib pbkdf2_sha256 格式的历史账号平滑升级为新哈希）。

    异常：
        数据库操作异常向上抛出并回滚。
    """
    from app.seed.configs import (
        ADMIN_DEFAULT_PASSWORD,
        ADMIN_ROLE,
        ADMIN_USERNAME,
        REMOTE_CONFIGS,
        hash_password,
        is_passlib_hash,
    )

    for key, value in REMOTE_CONFIGS:
        obj = session.query(RemoteConfig).filter(RemoteConfig.config_key == key).one_or_none()
        if obj is None:
            session.add(RemoteConfig(config_key=key, value=value, version=1))
            counters["remote_config"] += 1
        else:
            # upsert：仅更新值（版本号保留为回滚指针）
            obj.value = value
    admin = session.query(AdminUser).filter(AdminUser.username == ADMIN_USERNAME).one_or_none()
    if admin is None:
        session.add(AdminUser(
            username=ADMIN_USERNAME,
            # passlib pbkdf2_sha256 加盐哈希（阶段二认证体系直接消费）
            password_hash=hash_password(ADMIN_DEFAULT_PASSWORD),
            role=ADMIN_ROLE,
        ))
        counters["admin_user"] += 1
    elif not is_passlib_hash(admin.password_hash):
        # 历史库中旧格式哈希（阶段一 hashlib 手写 pbkdf2）→ 升级为 passlib 格式
        admin.password_hash = hash_password(ADMIN_DEFAULT_PASSWORD)
        print("[seed] 管理员 password_hash 已从旧格式升级为 passlib pbkdf2_sha256。")
    session.commit()
    print(f"[seed] 远程配置新增 {counters['remote_config']} 条；管理员新增 {counters['admin_user']} 个")


def print_summary(session) -> None:
    """输出库内抽样统计（函数）。

    说明：
        展示各核心表行数，用于任务自验（Task 2 验证）。

    异常：
        查询异常向上抛出。
    """
    from sqlalchemy import func

    from app.models import (
        AgentTrace,
        CookingSession,
        FlavorPairingRule,
        IngredientAlias,
        IngredientNutrition,
        IngredientProperty,
        RecipeIngredient,
        RecipeStep,
        RiskLog,
        TechniqueLibrary,
    )

    stats = {
        "食材总数": session.query(func.count(Ingredient.id)).scalar(),
        "别名数": session.query(func.count(IngredientAlias.id)).scalar(),
        "营养数": session.query(func.count(IngredientNutrition.id)).scalar(),
        "菜谱数": session.query(func.count(Recipe.id)).scalar(),
        "菜谱食材数": session.query(func.count(RecipeIngredient.id)).scalar(),
        "步骤数": session.query(func.count(RecipeStep.id)).scalar(),
        "风险规则数": session.query(func.count(RiskRule.id)).scalar(),
        "话术数": session.query(func.count(RiskMessage.id)).scalar(),
        "remote_config数": session.query(func.count(RemoteConfig.id)).scalar(),
        "烹饪会话数": session.query(func.count(CookingSession.id)).scalar(),
        "风控日志数": session.query(func.count(RiskLog.id)).scalar(),
        "trace数": session.query(func.count(AgentTrace.id)).scalar(),
        "管理员数": session.query(func.count(AdminUser.id)).scalar(),
        "技法白名单数": session.query(func.count(TechniqueLibrary.id)).scalar(),
        "食材五属性数": session.query(func.count(IngredientProperty.id)).scalar(),
        "搭配规则数": session.query(func.count(FlavorPairingRule.id)).scalar(),
    }
    print("[seed] ============ 库内统计 ============")
    for key, value in stats.items():
        print(f"[seed] {key}: {value}")


def main() -> None:
    """种子脚本主流程（函数）。

    流程：
        建库检查 → ensure_schema（Alembic upgrade/stamp）→ 食材 → 手写菜谱 →
        HowToCook 语料菜谱 → 风控 → 模块 O 创新数据 → 配置 → 统计。

    异常：
        任何步骤失败时打印错误并以非 0 退出码结束。
    """
    print("[seed] ===== AI 厨娘 种子脚本开始 =====")
    # 1. 建库
    ensure_database()
    # 2. 表结构：Alembic 统一纳管（空库 upgrade 全量建 / 存量库 stamp 兼容），create_all 已废弃
    branch = ensure_schema()
    print("[seed] 表结构已由 Alembic 管理"
          f"（{'stamp 兼容存量库' if branch == 'stamp' else 'upgrade head'}）："
          "阶段一 28 张业务表 + recipe_embedding + 阶段二扩展表就绪。")
    # 3~8. 幂等填充
    with SessionLocal() as session:
        try:
            seed_ingredients(session)
            seed_recipes(session)
            seed_corpus(session)  # HowToCook 语料（依赖食材库映射，须在食材之后）
            seed_safety(session)
            seed_innovation(session)  # 模块 O：技法白名单/食材五属性/搭配规则（依赖食材库）
            seed_configs(session)
            print_summary(session)
        except Exception:
            session.rollback()
            logger.exception("seed_failed")
            print("[seed][error] 种子执行失败，已回滚本次变更。")
            sys.exit(1)
    print("[seed] ===== 种子脚本执行完成 =====")


if __name__ == "__main__":
    main()
