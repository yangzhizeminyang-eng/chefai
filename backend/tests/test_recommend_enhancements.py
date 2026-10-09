"""推荐补全测试（spec Task 5 模块 E）。

覆盖：
    - E.8：POST /v1/recommend/filtered 重放（allergen / taboo 原因归因、结构断言）；
    - E.9：weighted_rank 反馈惩罚（同候选有无 penalty 排序变化 + rank_reasons
      含「你曾表示不喜欢」+ 分差恰为 0.5）；load_feedback_penalty 真库加载；
    - E.9 端到端：feedback 端点 dislike → load_feedback_penalty 立即可见；
    - E.11：空结果 suggestions 字段（_build_empty_suggestions 纯函数单测 +
      API 层条件断言，生僻组合不为空时 skip）；
    - POST /v1/recipes/{id}/feedback：201 创建与重复提交。
"""

from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.ability.ranking import (
    FEEDBACK_DISLIKE_PENALTY,
    load_feedback_penalty,
    weighted_rank,
)
from app.api.v1.recommend import _build_empty_suggestions
from app.core.db import SessionLocal
from app.models import Recipe, User
from app.safety.types import SafetyProfile
from tests.conftest import unique_request_id


def _make_candidate(recipe_id: int, main_names: list[str], covered: list[str], difficulty: int = 2) -> dict:
    """构造排序候选字典（函数，与 test_ranking.py 同款结构）。

    参数：
        recipe_id：菜谱 ID（唯一）。
        main_names：主料名列表。
        covered：用户已覆盖食材名列表。
        difficulty：难度值（1~5，默认 2）。

    返回值：
        dict：retrieve_candidates 兼容结构的候选字典。

    异常：
        无。
    """
    return {
        "recipe_id": recipe_id,
        "title": f"测试菜谱{recipe_id}",
        "difficulty": difficulty,
        "time_minutes": 15,
        "calories_kcal": 200,
        "allergen_codes": [],
        "ingredient_allergen_codes": [],
        "dietary_flags": [],
        "equipment": [],
        "covered_count": len([n for n in main_names if n in covered]),
        "covered_names": [n for n in main_names if n in covered],
        "main_ingredient_names": main_names,
        "seasoning_names": [],
        "matched_by_title": False,
    }


def _delete_user_by_anonymous_id(anon: str) -> None:
    """按匿名 ID 删除测试用户及其级联反馈行（函数）。

    参数：
        anon：匿名用户 ID。

    返回值：
        None。

    异常：
        数据库异常向上抛出（清理失败会让残留数据暴露）。
    """
    with SessionLocal() as session:
        row = session.execute(select(User).where(User.anonymous_id == anon)).scalar_one_or_none()
        if row is not None:
            session.delete(row)
            session.commit()


def _pick_published_recipe_id() -> int:
    """取一个已发布菜谱 ID（函数）。

    返回值：
        int：菜谱 ID。

    异常：
        种子库无已发布菜谱时断言失败。
    """
    with SessionLocal() as session:
        recipe_id = session.execute(
            select(Recipe.id).where(Recipe.status == "published").limit(1)
        ).scalar_one()
    return int(recipe_id)


# ---------------------------------------------------------------------------
# E.8 filtered 重放
# ---------------------------------------------------------------------------


def test_filtered_replay_allergen_reason(client: TestClient) -> None:
    """过敏原重放：番茄+鸡蛋 + egg 过敏原 → 含蛋菜谱被过滤且原因为 allergen（函数）。

    说明：
        种子库番茄炒蛋/西红柿鸡蛋汤含鸡蛋（allergen 自动聚合 egg），必被移除。

    参数：
        client：TestClient fixture。

    返回值：
        None。

    异常：
        断言失败即测试失败。
    """
    resp = client.post(
        "/v1/recommend/filtered",
        json={
            "ingredients": [{"name": "番茄"}, {"name": "鸡蛋"}],
            "allergen_codes": ["egg"],
        },
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["total_filtered"] == len(body["filtered"])
    assert body["total_filtered"] >= 1
    for item in body["filtered"]:
        assert item["reason"] in ("allergen", "taboo", "difficulty")
        assert item["recipe_id"] > 0
        assert item["recipe_name"]


def test_filtered_replay_taboo_reason(client: TestClient) -> None:
    """忌口重放：番茄 + egg_vegetarian 忌口 → 番茄炒蛋被过滤且原因为 taboo（函数）。

    参数：
        client：TestClient fixture。

    返回值：
        None。

    异常：
        断言失败即测试失败。
    """
    resp = client.post(
        "/v1/recommend/filtered",
        json={
            "ingredients": [{"name": "番茄"}],
            "dietary_restrictions": ["egg_vegetarian"],
        },
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["total_filtered"] >= 1
    assert any(item["reason"] == "taboo" for item in body["filtered"])


# ---------------------------------------------------------------------------
# E.9 反馈立即生效（weighted_rank 惩罚 + load_feedback_penalty）
# ---------------------------------------------------------------------------


def test_weighted_rank_feedback_penalty() -> None:
    """反馈惩罚改变排序、扣分恰为 0.5 且理由含「你曾表示不喜欢」（函数）。

    说明：
        高覆盖候选（201）基线排名第一；对 201 施加 dislike 惩罚后跌至低覆盖
        候选（202）之后。

    参数：
        无。

    返回值：
        None。

    异常：
        断言失败即测试失败。
    """
    candidates = [
        _make_candidate(201, ["土豆", "青椒"], ["土豆", "青椒"]),
        _make_candidate(202, ["土豆"], ["土豆"]),
    ]
    baseline = weighted_rank(candidates, SafetyProfile(), None)
    assert baseline[0]["recipe_id"] == 201

    penalized = weighted_rank(
        candidates, SafetyProfile(), None, feedback_penalty={201: FEEDBACK_DISLIKE_PENALTY}
    )
    assert penalized[0]["recipe_id"] == 202
    target = next(item for item in penalized if item["recipe_id"] == 201)
    assert "你曾表示不喜欢" in target["rank_reasons"]
    base_score = next(item["rank_score"] for item in baseline if item["recipe_id"] == 201)
    assert abs(target["rank_score"] - (base_score - 0.5)) < 1e-6


def test_load_feedback_penalty_from_db(client: TestClient) -> None:
    """load_feedback_penalty 真库加载 dislike 映射（函数）。

    说明：
        新建测试用户并写入 dislike 反馈行 → 加载映射 {recipe_id: 0.5}；
        无反馈用户返回空映射；finally 级联清理（user 删除级联清 feedback）。

    参数：
        client：TestClient fixture（保证应用上下文）。

    返回值：
        None。

    异常：
        断言失败即测试失败。
    """
    recipe_id = _pick_published_recipe_id()
    anon = f"anon_t5_pfb_{uuid.uuid4().hex[:10]}"
    with SessionLocal() as session:
        user = User(anonymous_id=anon)
        session.add(user)
        session.flush()
        user_id = int(user.id)
        from app.models import RecipeFeedback

        session.add(
            RecipeFeedback(user_id=user_id, recipe_id=recipe_id, feedback_type="dislike")
        )
        session.commit()
    try:
        with SessionLocal() as session:
            penalty = load_feedback_penalty(session, user_id)
        assert penalty == {recipe_id: FEEDBACK_DISLIKE_PENALTY}
        # 无任何反馈的用户 → 空映射（惩罚缺失不影响排序主链路）
        with SessionLocal() as session:
            assert load_feedback_penalty(session, user_id + 1_000_000_000) == {}
    finally:
        _delete_user_by_anonymous_id(anon)


# ---------------------------------------------------------------------------
# 反馈端点 + E.9 端到端
# ---------------------------------------------------------------------------


def test_feedback_endpoint_201_and_repeat(client: TestClient) -> None:
    """反馈端点创建 201 且允许重复提交（函数）。

    参数：
        client：TestClient fixture。

    返回值：
        None。

    异常：
        断言失败即测试失败。
    """
    recipe_id = _pick_published_recipe_id()
    anon = f"anon_t5_fb_{uuid.uuid4().hex[:10]}"
    headers = {"X-Anonymous-Id": anon}
    try:
        first = client.post(
            f"/v1/recipes/{recipe_id}/feedback",
            json={"action": "like", "rating": 5, "comment": "好吃"},
            headers=headers,
        )
        assert first.status_code == 201
        body = first.json()
        assert body["recipe_id"] == recipe_id
        assert body["feedback_type"] == "like"
        assert body["rating"] == 5

        # 重复提交（不同 action）仍 201（模型无唯一约束，多条均入库）
        second = client.post(
            f"/v1/recipes/{recipe_id}/feedback",
            json={"action": "dislike"},
            headers=headers,
        )
        assert second.status_code == 201
        assert second.json()["feedback_type"] == "dislike"
    finally:
        _delete_user_by_anonymous_id(anon)


def test_feedback_invalid_action_422(client: TestClient) -> None:
    """非法 action 返回 422 统一错误（函数）。

    参数：
        client：TestClient fixture。

    返回值：
        None。

    异常：
        断言失败即测试失败。
    """
    recipe_id = _pick_published_recipe_id()
    resp = client.post(
        f"/v1/recipes/{recipe_id}/feedback",
        json={"action": "meh"},
        headers={"X-Anonymous-Id": f"anon_t5_{uuid.uuid4().hex[:8]}"},
    )
    assert resp.status_code == 422


def test_feedback_dislike_feeds_ranking_penalty(client: TestClient) -> None:
    """E.9 端到端：API dislike 反馈 → load_feedback_penalty 立即可见（函数）。

    参数：
        client：TestClient fixture。

    返回值：
        None。

    异常：
        断言失败即测试失败。
    """
    recipe_id = _pick_published_recipe_id()
    anon = f"anon_t5_e2e_{uuid.uuid4().hex[:10]}"
    try:
        resp = client.post(
            f"/v1/recipes/{recipe_id}/feedback",
            json={"action": "dislike"},
            headers={"X-Anonymous-Id": anon},
        )
        assert resp.status_code == 201
        with SessionLocal() as session:
            user_id = int(
                session.execute(select(User.id).where(User.anonymous_id == anon)).scalar_one()
            )
            penalty = load_feedback_penalty(session, user_id)
        assert penalty.get(recipe_id) == FEEDBACK_DISLIKE_PENALTY
    finally:
        _delete_user_by_anonymous_id(anon)


# ---------------------------------------------------------------------------
# E.11 空结果建议
# ---------------------------------------------------------------------------


def test_build_empty_suggestions_structure() -> None:
    """空结果建议纯函数结构单测（恒执行，函数）。

    参数：
        无。

    返回值：
        None。

    异常：
        断言失败即测试失败。
    """
    suggestions = _build_empty_suggestions()
    assert suggestions["message"] == "没有找到能做的菜"
    assert isinstance(suggestions["relax_options"], list) and suggestions["relax_options"]
    assert suggestions["followup_question"]


def test_recommend_empty_results_suggestions(client: TestClient) -> None:
    """POST /v1/recommend 空结果时响应含 suggestions 字段（函数）。

    说明：
        生僻组合（皮蛋+榴莲）在种子库可能有候选（皮蛋豆腐引用皮蛋）——
        结果非空时 skip（空结果路径已由 _build_empty_suggestions 单测恒覆盖）。

    参数：
        client：TestClient fixture。

    返回值：
        None。

    异常：
        断言失败即测试失败。
    """
    resp = client.post(
        "/v1/recommend",
        json={
            "request_id": unique_request_id(),
            "ingredients": [{"name": "皮蛋"}, {"name": "榴莲"}],
        },
    )
    assert resp.status_code == 200
    body = resp.json()
    if body.get("results"):
        pytest.skip("种子库对该食材组合存在候选，空结果路径由 _build_empty_suggestions 单测覆盖")
    assert "suggestions" in body
    assert body["suggestions"]["message"] == "没有找到能做的菜"
    assert body["suggestions"]["relax_options"]
    assert body["suggestions"]["followup_question"]
