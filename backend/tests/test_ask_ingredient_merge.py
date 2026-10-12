"""OBS-03 ask 自然语言问句食材并入测试。

覆盖：
    - 纯函数 _match_terms_longest_first：最长匹配优先（「土豆淀粉」不被「土豆」
      在同一区间重复命中）、别名归一去重、上限截断；
    - extract_ingredient_names_from_text：真实种子库词表下提取（土豆淀粉/牛肉）；
    - POST /v1/ask「土豆和牛肉能一起做什么」→ recipe_search 响应中存在含「牛肉」
      食材的菜谱（种子数据口径：土豆炖牛肉/西红柿土豆炖牛肉）。
"""

from __future__ import annotations

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.ability.retrieval import (
    TEXT_MATCH_LIMIT,
    _match_terms_longest_first,
    extract_ingredient_names_from_text,
)
from app.core.db import SessionLocal
from app.models import Ingredient, RecipeIngredient
from tests.conftest import unique_request_id


def test_longest_match_shadows_substring_term() -> None:
    """最长匹配优先：长词消费区间后其子串短词不再命中（函数）。

    说明：
        「土豆淀粉和牛肉」中，「土豆淀粉」命中后「土豆」不得在同一区间重复命中。

    参数：
        无。

    返回值：
        None。

    异常：
        断言失败即测试失败。
    """
    terms = [("土豆", "土豆"), ("土豆淀粉", "土豆淀粉"), ("牛肉", "牛肉")]
    matched = _match_terms_longest_first("土豆淀粉和牛肉", terms)
    assert matched == ["土豆淀粉", "牛肉"]
    # 无重叠区间的两个词都能命中
    assert _match_terms_longest_first("土豆炒牛肉", terms) == ["土豆", "牛肉"]


def test_longest_match_alias_dedup_and_limit() -> None:
    """别名归一去重与上限截断（函数）。

    参数：
        无。

    返回值：
        None。

    异常：
        断言失败即测试失败。
    """
    # 番茄（别名西红柿）与西红柿主名同现 → 归一去重为一个食材
    terms = [("西红柿", "番茄"), ("番茄", "番茄"), ("牛肉", "牛肉")]
    matched = _match_terms_longest_first("西红柿和番茄炖牛肉", terms)
    assert matched == ["番茄", "牛肉"]
    # 上限截断：limit=2 时只返回前 2 个命中
    many = [(f"食材{i}", f"食材{i}") for i in range(5)]
    assert len(_match_terms_longest_first("食材0食材1食材2食材3食材4", many, limit=2)) == 2
    # 默认上限与 TEXT_MATCH_LIMIT 一致（10）
    twelve = [(f"配料{i}", f"配料{i}") for i in range(12)]
    text_value = "".join(f"配料{i}" for i in range(12))
    assert len(_match_terms_longest_first(text_value, twelve)) == TEXT_MATCH_LIMIT


def test_extract_ingredients_from_seeded_db() -> None:
    """真实种子库词表提取：土豆淀粉不被土豆抢先，牛肉正常命中（函数）。

    参数：
        无。

    返回值：
        None。

    异常：
        断言失败即测试失败（需先执行 python -m app.seed）。
    """
    with SessionLocal() as session:
        matched = extract_ingredient_names_from_text(session, "土豆淀粉和牛肉能一起做什么")
    assert "土豆淀粉" in matched
    assert "牛肉" in matched
    assert "土豆" not in matched  # 同区间被长词消费，不得重复命中


def test_ask_nl_ingredients_merged_into_recommend(client: TestClient) -> None:
    """ask 自然语言问句食材并入推荐检索（函数）。

    说明：
        「土豆和牛肉能一起做什么」走 recommend 意图分支（测试环境 LLM 不可达 →
        关键词兜底判 recommend），问句命中的食材并入检索入参后，推荐结果中
        应存在含「牛肉」食材的菜谱（种子数据：西红柿土豆炖牛肉引用牛肉，
        土豆炖牛肉标题含牛肉）。

    参数：
        client：TestClient fixture。

    返回值：
        None。

    异常：
        断言失败即测试失败（需先执行 python -m app.seed）。
    """
    resp = client.post(
        "/v1/ask",
        json={"text": "土豆和牛肉能一起做什么", "request_id": unique_request_id()},
    )
    assert resp.status_code == 200
    data = resp.json()
    # LLM 不可达 → 关键词兜底判 recommend → 子图产出 results → 契约口径 recipe_search
    assert data.get("intent") == "recipe_search"
    recipe_ids = data.get("recipe_ids") or []
    assert recipe_ids, "推荐结果不应为空"

    # 召回候选仅来自「土豆 ∪ 牛肉」食材覆盖（向量路径在离线环境降级），且含牛肉菜谱在列
    with SessionLocal() as session:
        beef_recipe_ids = set(
            session.execute(
                select(RecipeIngredient.recipe_id)
                .join(Ingredient, Ingredient.id == RecipeIngredient.ingredient_id)
                .where(Ingredient.name == "牛肉")
            ).scalars().all()
        )
    assert beef_recipe_ids, "种子数据应存在引用「牛肉」食材的菜谱"
    # 逐条校验返回菜谱的食材归属：至少一条含牛肉食材，其余也只能来自土豆/牛肉覆盖
    with SessionLocal() as session:
        potato_id = session.execute(
            select(Ingredient.id).where(Ingredient.name == "土豆")
        ).scalar_one()
        beef_id = session.execute(
            select(Ingredient.id).where(Ingredient.name == "牛肉")
        ).scalar_one()
        allowed = {int(potato_id), int(beef_id)}
        for rid in recipe_ids:
            ing_ids = set(
                session.execute(
                    select(RecipeIngredient.ingredient_id).where(
                        RecipeIngredient.recipe_id == int(rid)
                    )
                ).scalars().all()
            )
            assert ing_ids & allowed, f"菜谱 {rid} 未引用问句命中的食材（土豆/牛肉）"
        hit_beef = [
            rid
            for rid in recipe_ids
            if session.execute(
                select(RecipeIngredient.id)
                .where(RecipeIngredient.recipe_id == int(rid))
                .where(RecipeIngredient.ingredient_id == int(beef_id))
                .limit(1)
            ).scalar_one_or_none()
            is not None
        ]
    assert hit_beef, "推荐结果中应存在含「牛肉」食材的菜谱"
