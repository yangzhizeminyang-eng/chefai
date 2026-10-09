"""阶段二数据层扩展测试（Task 1：b8d3f5a21c60 迁移 + 模块 O 种子数据）。

覆盖：
    - 5 张新表存在且可插入查询：favorite_recipe / ingredient_property /
      flavor_pairing_rule / technique_library / innovation_recipe；
    - favorite_recipe 软删唯一约束生效（未删行 (user_id, recipe_id) 唯一，
      软删后允许重新收藏）；
    - innovation_recipe CHECK 约束生效（非法 status 报 IntegrityError）；
    - recipe_embedding 升级后结构可用：verified 行 / ai_private 行插入查询，
      source 枚举与 ai_private→owner_user_id 非空一致性 CHECK 生效；
    - user.preferences JSONB 读写正常；
    - 种子规模：ingredient_property ≥150、flavor_pairing_rule ≥60
      （taboo ≥8 / conflict ≥15 / recommend ≥35）、technique_library ≥20。

数据自洽：
    每个用例自建独立 user（anonymous_id 前缀 t_v2_）/ recipe，测后清理，
    重复执行互不影响（幂等）。
"""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import func, inspect
from sqlalchemy.exc import IntegrityError

from app.core.db import SessionLocal
from app.models import (
    FavoriteRecipe,
    FlavorPairingRule,
    IngredientProperty,
    InnovationRecipe,
    Recipe,
    RecipeEmbedding,
    TechniqueLibrary,
    User,
)

# 测试用户 anonymous_id 前缀（清理依据，避免误删真实数据）
_TEST_ANON_PREFIX = "t_v2_"


def _make_user(session) -> User:
    """创建测试用户（函数）。

    参数：
        session：SQLAlchemy 会话。

    返回值：
        User：已加入会话（未提交）的用户对象。

    异常：
        数据库异常向上抛出。
    """
    user = User(anonymous_id=f"{_TEST_ANON_PREFIX}{uuid.uuid4().hex[:16]}")
    session.add(user)
    return user


def _make_recipe(session) -> Recipe:
    """创建测试菜谱（函数）。

    参数：
        session：SQLAlchemy 会话。

    返回值：
        Recipe：已加入会话（未提交）的菜谱对象。

    异常：
        数据库异常向上抛出。
    """
    recipe = Recipe(
        title=f"__v2测试菜谱_{uuid.uuid4().hex[:10]}",
        difficulty=1,
        servings=1,
        source_label="unit-test",
        source_license="test",
    )
    session.add(recipe)
    return recipe


def _cleanup_user(session, user_id: int) -> None:
    """清理测试用户及其级联数据（函数）。

    说明：
        依赖 DB 级 CASCADE：删除 user 级联清理 favorite_recipe /
        innovation_recipe；测试菜谱为独立行，需显式删除。

    参数：
        session：SQLAlchemy 会话。
        user_id：测试用户 id。

    返回值：
        None。

    异常：
        数据库异常向上抛出。
    """
    session.rollback()
    session.query(FavoriteRecipe).filter(FavoriteRecipe.user_id == user_id).delete()
    session.query(InnovationRecipe).filter(InnovationRecipe.user_id == user_id).delete()
    session.query(RecipeEmbedding).filter(
        RecipeEmbedding.owner_user_id == user_id
    ).delete(synchronize_session=False)
    session.query(Recipe).filter(
        Recipe.title.like("__v2测试菜谱_%"), Recipe.source_label == "unit-test"
    ).delete(synchronize_session=False)
    session.query(User).filter(User.id == user_id).delete()
    session.commit()


def test_new_tables_exist(client) -> None:
    """5 张新表在库中存在（测试）。

    参数：
        client：conftest 提供的 TestClient fixture（真实库）。

    异常：
        表缺失时断言失败。
    """
    inspector = inspect(SessionLocal().bind)
    for table in (
        "favorite_recipe", "ingredient_property", "flavor_pairing_rule",
        "technique_library", "innovation_recipe",
    ):
        assert inspector.has_table(table), f"表 {table} 不存在"


def test_favorite_recipe_crud_and_unique(client) -> None:
    """favorite_recipe 可插入查询且软删唯一约束生效（测试）。

    流程：
        1. 建 user/recipe，插入收藏行可查询；
        2. 同一 (user_id, recipe_id) 二次插入（均未软删）报 IntegrityError；
        3. 软删首行后允许重新收藏（partial unique index 语义）。

    参数：
        client：conftest 提供的 TestClient fixture。

    异常：
        唯一约束未生效或软删重藏失败时断言失败。
    """
    session = SessionLocal()
    user = _make_user(session)
    recipe = _make_recipe(session)
    session.flush()
    user_id, recipe_id = user.id, recipe.id
    try:
        first = FavoriteRecipe(user_id=user_id, recipe_id=recipe_id, note="收藏一")
        session.add(first)
        session.commit()
        got = (
            session.query(FavoriteRecipe)
            .filter(FavoriteRecipe.user_id == user_id, FavoriteRecipe.recipe_id == recipe_id)
            .one()
        )
        assert got.group_name == "默认分组"  # server_default 生效
        assert got.note == "收藏一"

        # 未删行重复收藏 → 唯一约束拦截
        session.add(FavoriteRecipe(user_id=user_id, recipe_id=recipe_id))
        with pytest.raises(IntegrityError):
            session.commit()
        session.rollback()

        # 软删后允许重新收藏
        first.deleted_at = func.now()
        session.commit()
        again = FavoriteRecipe(user_id=user_id, recipe_id=recipe_id, group_name="宵夜")
        session.add(again)
        session.commit()
        assert (
            session.query(FavoriteRecipe)
            .filter(FavoriteRecipe.user_id == user_id, FavoriteRecipe.deleted_at.is_(None))
            .count()
        ) == 1
    finally:
        _cleanup_user(session, user_id)


def test_innovation_recipe_check_status(client) -> None:
    """innovation_recipe 非法 status 被 CHECK 约束拦截（测试）。

    参数：
        client：conftest 提供的 TestClient fixture。

    异常：
        CHECK 约束未生效时断言失败。
    """
    session = SessionLocal()
    user = _make_user(session)
    session.flush()
    user_id = user.id
    try:
        # 合法行可插入查询
        ok = InnovationRecipe(
            user_id=user_id, name="__v2创新菜",
            ingredients=[{"ingredient_id": 1, "name": "番茄", "amount": 2, "unit": "个"}],
            steps=[{"no": 1, "description": "切块", "duration_sec": 30, "tips": None}],
            nutrition={"kcal": 100}, basis={"texture": ["软嫩"]},
        )
        session.add(ok)
        session.commit()
        assert session.query(InnovationRecipe).filter(
            InnovationRecipe.user_id == user_id).one().status == "generated"

        # 非法 status → CHECK 拦截
        bad = InnovationRecipe(
            user_id=user_id, name="__v2非法状态",
            ingredients=[], steps=[], nutrition={}, basis={},
            status="published",  # 不在 CHECK 枚举内
        )
        session.add(bad)
        with pytest.raises(IntegrityError):
            session.commit()
        session.rollback()
    finally:
        _cleanup_user(session, user_id)


def test_recipe_embedding_sources(client) -> None:
    """recipe_embedding 升级后两种来源行可用且一致性 CHECK 生效（测试）。

    说明：
        pgvector 向量列不在 ORM 中（仅存在于迁移），本用例验证 ORM 可见的
        embedding_json 便携列与溯源列语义。

    参数：
        client：conftest 提供的 TestClient fixture。

    异常：
        结构异常或 CHECK 未生效时断言失败。
    """
    session = SessionLocal()
    user = _make_user(session)
    recipe = _make_recipe(session)
    session.flush()
    user_id, recipe_id = user.id, recipe.id
    try:
        # verified 行：recipe_id 指向官方菜谱
        session.add(RecipeEmbedding(
            recipe_id=recipe_id, source="verified",
            embedding_json=[0.1] * 1024,
        ))
        # ai_private 行：须携带 owner_user_id
        innovation = InnovationRecipe(
            user_id=user_id, name="__v2向量测试创新菜",
            ingredients=[], steps=[], nutrition={}, basis={},
        )
        session.add(innovation)
        session.flush()
        session.add(RecipeEmbedding(
            source="ai_private", owner_user_id=user_id,
            innovation_recipe_id=innovation.id,
            embedding_json=[0.2] * 1024,
        ))
        session.commit()

        verified_row = (
            session.query(RecipeEmbedding)
            .filter(RecipeEmbedding.recipe_id == recipe_id, RecipeEmbedding.source == "verified")
            .one()
        )
        assert len(verified_row.embedding_json) == 1024
        assert (
            session.query(RecipeEmbedding)
            .filter(RecipeEmbedding.owner_user_id == user_id,
                    RecipeEmbedding.source == "ai_private")
            .count()
        ) == 1

        # ai_private 缺 owner_user_id → CHECK 拦截
        session.add(RecipeEmbedding(source="ai_private", embedding_json=[0.0] * 1024))
        with pytest.raises(IntegrityError):
            session.commit()
        session.rollback()

        # 非法 source 枚举 → CHECK 拦截
        session.add(RecipeEmbedding(recipe_id=recipe_id, source="unknown"))
        with pytest.raises(IntegrityError):
            session.commit()
        session.rollback()
    finally:
        _cleanup_user(session, user_id)


def test_user_preferences_roundtrip(client) -> None:
    """user.preferences JSONB 写入后读取一致（测试）。

    参数：
        client：conftest 提供的 TestClient fixture。

    异常：
        读写不一致时断言失败。
    """
    session = SessionLocal()
    user = _make_user(session)
    session.flush()
    user_id = user.id
    try:
        prefs = {"font_size": "large", "unit": "metric",
                 "remind": True, "voice": False}
        user.preferences = prefs
        session.commit()
        got = session.query(User).filter(User.id == user_id).one()
        assert got.preferences == prefs
    finally:
        _cleanup_user(session, user_id)


def test_seed_scale_counts(client) -> None:
    """模块 O 种子规模达标（测试）。

    断言：
        - ingredient_property ≥150；
        - flavor_pairing_rule ≥60（taboo ≥8 / conflict ≥15 / recommend ≥35）；
        - technique_library ≥20。

    参数：
        client：conftest 提供的 TestClient fixture。

    异常：
        规模不足时断言失败。
    """
    session = SessionLocal()
    try:
        assert session.query(func.count(IngredientProperty.id)).scalar() >= 150
        assert session.query(func.count(TechniqueLibrary.id)).scalar() >= 20

        total = session.query(func.count(FlavorPairingRule.id)).scalar()
        assert total >= 60
        by_relation = dict(
            session.query(FlavorPairingRule.relation,
                          func.count(FlavorPairingRule.id))
            .group_by(FlavorPairingRule.relation)
            .all()
        )
        assert by_relation.get("taboo", 0) >= 8
        assert by_relation.get("conflict", 0) >= 15
        assert by_relation.get("recommend", 0) >= 35
    finally:
        session.close()


def test_technique_library_query(client) -> None:
    """technique_library 可查询且白名单标注正确（测试）。

    参数：
        client：conftest 提供的 TestClient fixture。

    异常：
        查询异常或白名单缺失时断言失败。
    """
    session = SessionLocal()
    try:
        names = {row[0] for row in session.query(TechniqueLibrary.name).all()}
        assert {"炒", "蒸", "煮", "炖", "烤"} <= names
        assert (
            session.query(func.count(TechniqueLibrary.id))
            .filter(TechniqueLibrary.in_whitelist.is_(True)).scalar()
        ) >= 20
    finally:
        session.close()
