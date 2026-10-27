"""「今天吃什么」零输入直出推荐端点测试。

覆盖：
    - POST /v1/recommend/day-menu 空请求体 200 正常：results 非空且 ≤6 条、
      每条含 cover_image_url 键、difficulty 为三档文案之一、match_level
      固定 can_cook_now、rank_reasons 非空；
    - 🔴 硬过滤不绕过：家庭档案设置过敏原（Family/FamilyMember 行）后，
      结果全部不含该过敏原，且 filtered_by['allergen'] 计数 ≥1；
    - exclude_ids 换一换：第二次请求排除上一批全部 recipe_id，两批无交集；
    - 空结果：exclude 掉全部已发布菜谱 → results=[] 且 notice 非空；
    - filtered_by 结构：恒含 allergen/dietary_restriction/difficulty/equipment 四键。

清理约定：
    自建唯一后缀匿名用户及其家庭档案（自建自清理，禁删种子）。
"""

from __future__ import annotations

import uuid

from fastapi.testclient import TestClient
from sqlalchemy import delete, select

from app.api.v1 import day_menu as day_menu_api
from app.core.db import SessionLocal
from app.main import app as main_app
from app.models import Family, FamilyMember, Recipe, User
from tests.conftest import ensure_router_registered

# 测试用过敏原 code（GB 7718 八类之一；种子菜谱含蛋样本 ≥1，保证区分度）
_TEST_ALLERGEN = "egg"


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
        (day_menu_api.router,),
        flag="_day_menu_routes_registered",
        prefix="/v1",
        probe_paths=("/v1/recommend/day-menu",),
    )


_ensure_routes_registered()


def _unique_anon() -> str:
    """生成测试专用匿名 ID（函数）。

    返回值：
        str：anon_day_menu_ 前缀唯一串（自建自清理，不碰种子）。

    异常：
        无。
    """
    return f"anon_day_menu_{uuid.uuid4().hex[:12]}"


def _delete_user_cascade(anon_id: str) -> None:
    """清理测试用户及其级联数据（函数）。

    说明：
        仅删除本测试自建匿名用户的家庭档案三行（member/family/user），禁删种子。

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


def _create_user_with_allergen(anon_id: str, allergen_codes: list[str]) -> int:
    """创建测试用户并写入家庭档案过敏原（函数）。

    说明：
        直建 User → Family → FamilyMember（allergen_codes 命中表级
        chk_allergen_required 约束：勾过敏原即合法），返回 user_id。

    参数：
        anon_id：匿名 ID（唯一后缀）。
        allergen_codes：成员过敏原 code 列表（如 ["egg"]）。

    返回值：
        int：用户数据库 ID。

    异常：
        数据库异常向上抛出（环境前置条件）。
    """
    with SessionLocal() as session:
        user = User(anonymous_id=anon_id)
        session.add(user)
        session.flush()
        uid = int(user.id)
        family = Family(user_id=uid, name=f"测试家庭{anon_id[-4:]}")
        session.add(family)
        session.flush()
        session.add(
            FamilyMember(
                family_id=int(family.id),
                nickname="测试成员",
                age_group="18-59",
                allergen_codes=list(allergen_codes),
            )
        )
        session.commit()
        return uid


def test_day_menu_normal_returns_up_to_six(client: TestClient) -> None:
    """空请求体 200 正常：≤6 条候选、字段契约齐全（函数）。

    说明：
        results 非空且 ≤6；每条含 cover_image_url 键（None 合法）、difficulty
        为 easy/medium/hard 之一、match_level 固定 can_cook_now、rank_reasons
        非空、required_equipment/allergens 为列表。

    参数：
        client：TestClient fixture。

    返回值：
        None。

    异常：
        断言失败即测试失败。
    """
    resp = client.post("/v1/recommend/day-menu", json={})
    assert resp.status_code == 200
    body = resp.json()
    results = body["results"]
    assert 1 <= len(results) <= 6
    assert body["safe_mode"] is False
    for item in results:
        assert "cover_image_url" in item
        assert item["difficulty"] in ("easy", "medium", "hard")
        assert item["match_level"] == "can_cook_now"
        assert item["rank_reasons"]
        assert isinstance(item["allergens"], list)
        assert isinstance(item["required_equipment"], list)
        assert item["recipe_id"] > 0
        assert item["title"]


def test_day_menu_hard_filter_allergen(client: TestClient) -> None:
    """硬过滤不绕过：档案过敏原菜谱 0 条出现在结果（函数）。

    说明：
        测试用户家庭档案设 egg 过敏原 → 结果全部不含 egg（布尔排除非降权）；
        filtered_by['allergen'] 计数 ≥1（种子含蛋菜谱，保证断言区分度）。

    参数：
        client：TestClient fixture。

    返回值：
        None。

    异常：
        断言失败即测试失败（清理逻辑在 finally 中执行）。
    """
    anon = _unique_anon()
    _create_user_with_allergen(anon, [_TEST_ALLERGEN])
    try:
        resp = client.post("/v1/recommend/day-menu", json={"anonymous_id": anon})
        assert resp.status_code == 200
        body = resp.json()
        results = body["results"]
        assert results, "过滤后应仍有可做菜谱（种子规模足够）"
        for item in results:
            assert _TEST_ALLERGEN not in (item["allergens"] or []), (
                f"结果 {item.get('title')} 命中过敏原 egg，硬过滤被绕过"
            )
        assert (body["filtered_by"] or {}).get("allergen", 0) >= 1
    finally:
        _delete_user_cascade(anon)


def test_day_menu_exclude_ids_no_overlap(client: TestClient) -> None:
    """exclude_ids 换一换：两批结果无交集（函数）。

    说明：
        第一次请求返回的全部 recipe_id 作为 exclude_ids 再请求，
        第二批不允许出现第一批任何 ID（换一换语义）。

    参数：
        client：TestClient fixture。

    返回值：
        None。

    异常：
        断言失败即测试失败。
    """
    first = client.post("/v1/recommend/day-menu", json={})
    assert first.status_code == 200
    first_ids = [item["recipe_id"] for item in first.json()["results"]]
    assert first_ids, "首批结果不应为空（种子已发布菜谱存在）"

    second = client.post("/v1/recommend/day-menu", json={"exclude_ids": first_ids})
    assert second.status_code == 200
    second_results = second.json()["results"]
    assert second_results, "排除 6 道后种子仍有候选"
    overlapped = {item["recipe_id"] for item in second_results} & set(first_ids)
    assert overlapped == set(), f"换一换结果与上一批重叠：{overlapped}"


def test_day_menu_empty_results_notice(client: TestClient) -> None:
    """排除全部已发布菜谱：results=[] 且 notice 非空（函数）。

    说明：
        exclude_ids 覆盖全部 published recipe_id → 无候选可出，返回空列表
        并附带引导文案（HTTP 仍 200，降级约定）。

    参数：
        client：TestClient fixture。

    返回值：
        None。

    异常：
        断言失败即测试失败。
    """
    with SessionLocal() as session:
        all_ids = [
            int(rid)
            for rid in session.execute(
                select(Recipe.id).where(Recipe.status == "published")
            ).scalars()
        ]
    assert all_ids, "种子已发布菜谱为空，请先执行 python -m app.seed"

    resp = client.post("/v1/recommend/day-menu", json={"exclude_ids": all_ids})
    assert resp.status_code == 200
    body = resp.json()
    assert body["results"] == []
    assert body.get("notice"), "空结果必须附带 notice 引导文案"


def test_day_menu_filtered_by_keys(client: TestClient) -> None:
    """filtered_by 恒含四维过滤计数键（函数）。

    说明：
        counts 由 hard_filter 产出：allergen / dietary_restriction /
        difficulty / equipment 四键恒存在（未启用的维度计数为 0）。

    参数：
        client：TestClient fixture。

    返回值：
        None。

    异常：
        断言失败即测试失败。
    """
    resp = client.post("/v1/recommend/day-menu", json={})
    assert resp.status_code == 200
    filtered_by = resp.json()["filtered_by"]
    assert filtered_by is not None
    for key in ("allergen", "dietary_restriction", "difficulty", "equipment"):
        assert key in filtered_by, f"filtered_by 缺少维度键：{key}"
        assert isinstance(filtered_by[key], int)
