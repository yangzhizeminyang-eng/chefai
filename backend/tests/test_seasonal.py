"""时令端点集成测试（GET /v1/seasonal）。

覆盖：
    - 200 结构：month ∈ 1~12、ingredients/recipes 为数组、≤8 条、按耗时升序；
    - 当月食材非空：白名单与 seed 食材库命中率 ≥90%（单元级）+ 接口返回
      ingredients 非空（测试库已 seed，环境前置条件同 test_hard_filter）；
    - 菜谱主料命中：接口返回 recipes 与「主料 ∈ 当季名单 + published」的手工
      同口径 SQL 结果一致（返回集 ⊆ 手工集）；
    - 降级 200：monkeypatch 查询函数抛异常 → 仍 200 且对应子项空数组；
    - 过敏原硬过滤：家庭档案登记 egg 过敏原后，当季菜谱不含含蛋菜谱
      （接口级断言 + DB 复核）。

清理约定：
    自建唯一后缀匿名用户及其级联数据（家庭/成员），禁删种子。
"""

from __future__ import annotations

import uuid

from fastapi.testclient import TestClient
from sqlalchemy import delete, select

from app.api.v1 import seasonal as seasonal_api
from app.core.db import SessionLocal
from app.main import app as main_app
from app.models import Family, FamilyMember, Ingredient, Recipe, RecipeIngredient, User
from app.schemas.recommend import RecommendResultItem
from app.seed.ingredients import INGREDIENTS
from tests.conftest import ensure_router_registered


def _ensure_routes_registered() -> None:
    """并行开发兜底：router.py 由其他任务负责注册（函数）。

    说明：
        router.py 属禁改文件；若其他任务尚未注册本模块路由，则在主应用上
        幂等挂载（已注册则跳过），保证本测试模块可独立运行。
        守卫统一复用 conftest.ensure_router_registered（防重复注册）。

    参数：
        无。

    返回值：
        None。

    异常：
        无。
    """
    ensure_router_registered(
        main_app,
        (seasonal_api.router,),
        flag="_seasonal_routes_registered",
        prefix="/v1",
        probe_paths=("/v1/seasonal",),
    )


_ensure_routes_registered()


def _unique_anon() -> str:
    """生成测试专用匿名 ID（函数）。

    返回值：
        str：anon_test_ 前缀唯一串（自建自清理，不碰种子）。

    异常：
        无。
    """
    return f"anon_test_{uuid.uuid4().hex[:12]}"


def _delete_user_cascade(anon_id: str) -> None:
    """清理测试用户及其级联数据（函数）。

    说明：
        仅删除本测试自建匿名用户（family/member），禁删种子。

    参数：
        anon_id：匿名 ID。

    返回值：
        None。

    异常：
        数据库异常向上抛出（清理失败即测试失败，避免脏数据残留）。
    """
    with SessionLocal() as session:
        user = session.execute(
            select(User).where(User.anonymous_id == anon_id)
        ).scalar_one_or_none()
        if user is None:
            return
        uid = int(user.id)
        session.execute(
            delete(FamilyMember).where(
                FamilyMember.family_id.in_(select(Family.id).where(Family.user_id == uid))
            )
        )
        session.execute(delete(Family).where(Family.user_id == uid))
        session.execute(delete(User).where(User.id == uid))
        session.commit()


def test_seasonal_structure(client: TestClient) -> None:
    """200 结构：month 1~12、子项为数组、菜谱 ≤8 条且按耗时升序（函数）。

    参数：
        client：TestClient fixture。

    返回值：
        None。

    异常：
        断言失败即测试失败。
    """
    resp = client.get("/v1/seasonal", headers={"X-Anonymous-Id": _unique_anon()})
    assert resp.status_code == 200
    body = resp.json()
    assert 1 <= body["month"] <= 12
    assert isinstance(body["ingredients"], list)
    assert isinstance(body["recipes"], list)
    assert len(body["recipes"]) <= 8
    for item in body["ingredients"]:
        assert set(item) >= {"id", "name", "category"}
    for item in body["recipes"]:
        assert item["match_level"] == "can_cook_now"
        assert item["rank_reasons"], "rank_reasons 至少 1 条"
        assert not any(
            word in "".join(item["rank_reasons"]) for word in ("营养", "养生", "滋补")
        ), "理由不得含功效表述"
    # 耗时升序（None 视为 9999 排在后）
    times = [(item["time_minutes"] or 9999) for item in body["recipes"]]
    assert times == sorted(times)
    # cover_image_url：并行任务落地 RecommendResultItem.cover_image_url 后
    # 响应条目必须携带该键（未落地时 Pydantic extra=ignore 静默省略，跳过）
    if "cover_image_url" in RecommendResultItem.model_fields:
        for item in body["recipes"]:
            assert "cover_image_url" in item
            assert item["cover_image_url"] is None or isinstance(item["cover_image_url"], str)


def test_seasonal_current_month_ingredients_nonempty(client: TestClient) -> None:
    """当月食材非空：白名单命中率 ≥90% + 接口 ingredients 非空（函数）。

    说明：
        单元级断言：当月白名单与 seed 食材库（app.seed.ingredients.INGREDIENTS）
        名称命中率 ≥90%（红线：白名单名称必须来自库内）；接口级断言：测试库
        已 seed，命中名称必然落库 → ingredients 非空。

    参数：
        client：TestClient fixture。

    返回值：
        None。

    异常：
        断言失败即测试失败（接口非空依赖种子数据，环境前置条件）。
    """
    seed_names = {str(row[0]) for row in INGREDIENTS}
    month = seasonal_api._current_month()
    names = seasonal_api._SEASONAL_INGREDIENTS[month]
    assert 15 <= len(names) <= 25, "每月白名单 15~25 种（口径约定）"
    hit = sum(1 for name in names if name in seed_names)
    assert hit / len(names) >= 0.9, f"当月白名单 seed 命中率 {hit}/{len(names)} 低于 90%"

    resp = client.get("/v1/seasonal")
    assert resp.status_code == 200
    body = resp.json()
    assert body["month"] == month
    assert len(body["ingredients"]) >= 1, "测试库已 seed，当月食材应非空（环境前置条件）"
    returned_names = {item["name"] for item in body["ingredients"]}
    assert returned_names <= set(names), "返回食材必须全部来自当月白名单"


def test_seasonal_recipes_consistent_with_main_ingredient_query(client: TestClient) -> None:
    """菜谱主料命中：返回 recipes 与手工同口径查询一致（函数）。

    说明：
        手工口径 = recipe_ingredient.amount_type='main' 且食材名命中当月白名单
        （join ingredient）的 published 菜谱；无档案请求下 hard_filter 各维度
        空集不生效，接口返回集应与手工 published 集一致（⊆ 断言 + 非空性一致）。

    参数：
        client：TestClient fixture。

    返回值：
        None。

    异常：
        断言失败即测试失败。
    """
    names = seasonal_api._SEASONAL_INGREDIENTS[seasonal_api._current_month()]
    with SessionLocal() as session:
        rows = session.execute(
            select(RecipeIngredient.recipe_id)
            .join(Ingredient, RecipeIngredient.ingredient_id == Ingredient.id)
            .where(RecipeIngredient.amount_type == "main", Ingredient.name.in_(names))
        ).all()
        main_hit_ids = {int(r[0]) for r in rows}
        expected_ids = set()
        if main_hit_ids:
            expected_ids = {
                int(r[0])
                for r in session.execute(
                    select(Recipe.id).where(Recipe.status == "published", Recipe.id.in_(main_hit_ids))
                ).all()
            }

    resp = client.get("/v1/seasonal")
    assert resp.status_code == 200
    returned_ids = {item["recipe_id"] for item in resp.json()["recipes"]}
    assert returned_ids <= expected_ids, "返回菜谱必须全部来自「主料 ∈ 当季名单」的 published 集"
    if expected_ids:
        assert returned_ids, "手工口径存在当季菜谱而接口返回为空（无档案下硬过滤不应误杀）"


def test_seasonal_degrade_on_exception(client: TestClient, monkeypatch: object) -> None:
    """降级 200：子项查询异常 → 仍 200 且对应子项空数组（函数）。

    说明：
        食材/菜谱两个子项独立降级（对齐 home.py 惯例）；month 正常返回。

    参数：
        client：TestClient fixture。
        monkeypatch：pytest monkeypatch fixture。

    返回值：
        None。

    异常：
        断言失败即测试失败。
    """
    def _boom(*_args: object, **_kwargs: object) -> None:
        """模拟数据库查询异常（函数）。

        参数：
            *_args：忽略位置参数。
            **_kwargs：忽略关键字参数。

        返回值：
            None。

        异常：
            恒抛 RuntimeError。
        """
        raise RuntimeError("simulated db failure")

    # 子项 1：食材查询异常 → ingredients=[]、recipes 不受影响（独立降级）
    monkeypatch.setattr(seasonal_api, "_load_seasonal_ingredients", _boom)
    resp = client.get("/v1/seasonal")
    assert resp.status_code == 200
    body = resp.json()
    assert body["ingredients"] == []
    assert 1 <= body["month"] <= 12

    # 子项 2：菜谱主料查询异常 → recipes=[]
    monkeypatch.setattr(seasonal_api, "_load_seasonal_recipe_ids", _boom)
    resp = client.get("/v1/seasonal")
    assert resp.status_code == 200
    body = resp.json()
    assert body["recipes"] == []
    assert 1 <= body["month"] <= 12


def test_seasonal_allergen_hard_filter(client: TestClient) -> None:
    """过敏原硬过滤：档案登记 egg 后当季菜谱不含含蛋菜谱（函数）。

    说明：
        集成断言：家庭档案成员 allergen_codes=["egg"]（多成员最严格并集口径）
        → 接口返回 recipes 的 allergens 与 DB 复核均不含 egg（🔴 硬过滤不绕过）。

    参数：
        client：TestClient fixture。

    返回值：
        None。

    异常：
        断言失败即测试失败。
    """
    anon = _unique_anon()
    try:
        with SessionLocal() as session:
            user = User(anonymous_id=anon)
            session.add(user)
            session.flush()
            family = Family(user_id=int(user.id), name=f"测试家庭{anon[-4:]}")
            session.add(family)
            session.flush()
            session.add(
                FamilyMember(
                    family_id=family.id, nickname="爸爸", age_group="18-59",
                    allergen_codes=["egg"],
                )
            )
            session.commit()

        resp = client.get("/v1/seasonal", headers={"X-Anonymous-Id": anon})
        assert resp.status_code == 200
        recipes = resp.json()["recipes"]
        assert all("egg" not in item["allergens"] for item in recipes)

        # DB 复核：返回菜谱的自带/食材聚合致敏原均不含 egg
        with SessionLocal() as session:
            for item in recipes:
                row = session.execute(
                    select(Recipe.allergen_codes, Recipe.ingredient_allergen_codes).where(
                        Recipe.id == int(item["recipe_id"])
                    )
                ).one()
                assert "egg" not in (row[0] or []), f"菜谱 {item['recipe_id']} 自带致敏原泄漏"
                assert "egg" not in (row[1] or []), f"菜谱 {item['recipe_id']} 食材致敏原泄漏"
    finally:
        _delete_user_cascade(anon)
