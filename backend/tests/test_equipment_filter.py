"""设备维度硬过滤测试（缺陷 M2/P6/S8 修复回归）。

覆盖：
    - 设备硬过滤：档案仅持炒锅时，需要燃气灶的菜谱 0 条出现在过滤后结果
      （布尔语义完全排除，非降权）；
    - filtered_by['equipment'] 计数准确 = 候选中缺设备菜谱数；
    - 既有过敏原维度与设备维度叠加过滤互不破坏（过敏原/忌口断言保持全绿）；
    - 档案设备为空（未设置）时设备维度不生效（避免新用户全空结果）；
    - POST /v1/recommend/filtered 重放清单含设备原因条目
      （reasons 元素 {type: "equipment", detail: "缺少设备：燃气灶"}）；
    - 端到端：runner 从 user_skill_profile 载入设备档案 → 推荐结果排除缺灶具菜谱。
"""

from __future__ import annotations

import uuid

from fastapi.testclient import TestClient
from sqlalchemy import delete

from app.ability.ranking import find_missing_equipment, hard_filter
from app.ability.retrieval import retrieve_candidates
from app.core.db import SessionLocal
from app.graph.runner import run_recommend
from app.models import User, UserSkillProfile
from app.safety.types import SafetyProfile


def _load_all_candidates() -> list[dict]:
    """加载全量已发布菜谱候选（函数）。

    说明：
        空食材 + 空文本 → 冷启动全量召回（retrieve_candidates 保证）。

    参数：
        无。

    返回值：
        list[dict]：候选菜谱字典列表。

    异常：
        数据库异常向上抛出（环境前置条件）。
    """
    with SessionLocal() as session:
        return retrieve_candidates(session, [], query_text=None, limit=200)


def test_find_missing_equipment_semantics() -> None:
    """设备差集核心语义：豁免集 / 空档案 / 双向包含（函数）。

    说明：
        - 碗/盘/刀/砧板/勺等基础工具与耗材不参与差集（豁免集）；
        - 用户档案为空 → 恒返回空列表（设备维度不生效）；
        - 双向包含：用户「炒锅」覆盖菜谱「普通的炒锅」/泛化「锅」等语料变体；
        - 灶具/电器/锅具类缺失照常产出（燃气灶/微波炉）。

    参数：
        无。

    返回值：
        None。

    异常：
        断言失败即测试失败。
    """
    # 仅灶具/电器/锅具类参与差集；基础工具（菜刀/砧板/碗）恒豁免
    assert find_missing_equipment(["炒锅", "燃气灶", "菜刀", "砧板", "大碗"], ["炒锅"]) == ["燃气灶"]
    # 空档案（未设置设备）→ 不启用设备过滤
    assert find_missing_equipment(["燃气灶", "烤箱"], []) == []
    assert find_missing_equipment(["燃气灶"], None) == []
    # 双向包含：语料变体写法不误滤
    assert find_missing_equipment(["普通的炒锅", "锅"], ["炒锅"]) == []
    assert find_missing_equipment(["不粘平底锅"], ["平底锅"]) == []
    # 耗材/误判词（保鲜膜/火锅底料）豁免
    assert find_missing_equipment(["保鲜膜", "火锅底料", "北京二锅头酒"], ["汤锅"]) == []
    # 电器缺失照常过滤
    assert find_missing_equipment(["微波炉"], ["炒锅"]) == ["微波炉"]


def test_equipment_filter_excludes_missing_stove() -> None:
    """档案仅持炒锅：需燃气灶菜谱 0 条出现在过滤后结果（函数）。

    说明：
        SafetyProfile(equipment=['炒锅']) 过滤后：
        - 结果集中不存在「缺失燃气灶」的菜谱（布尔排除，🔴 非降权）；
        - 候选中确实存在需燃气灶菜谱（保证断言区分度，种子含燃气灶菜谱 ≥1）；
        - 过滤后集合中每条菜谱的缺失设备列表为空。

    参数：
        无。

    返回值：
        None。

    异常：
        断言失败即测试失败。
    """
    candidates = _load_all_candidates()
    assert candidates, "种子菜谱为空，请先执行 python -m app.seed"

    with SessionLocal() as session:
        filtered, _counts = hard_filter(session, candidates, SafetyProfile(equipment=["炒锅"]))

    # 候选必须含需燃气灶菜谱（否则断言无区分度）
    stove_candidates = [
        c for c in candidates
        if find_missing_equipment(c.get("equipment") or [], ["炒锅"])
        and any(e == "燃气灶" for e in (c.get("equipment") or []))
    ]
    assert stove_candidates, "种子菜谱缺少「需燃气灶」样本，请先执行 python -m app.seed"

    # 过滤后集合不允许出现任何缺失设备的菜谱（含燃气灶菜谱 0 条出现）
    leaked = [c for c in filtered if find_missing_equipment(c.get("equipment") or [], ["炒锅"])]
    assert leaked == []
    # 被排除的菜谱确实覆盖了全部需燃气灶样本
    filtered_ids = {int(c["recipe_id"]) for c in filtered}
    assert all(int(c["recipe_id"]) not in filtered_ids for c in stove_candidates)


def test_equipment_filter_counts() -> None:
    """filtered_by['equipment'] 计数准确（函数）。

    说明：
        counts['equipment'] = 候选中缺设备菜谱数；无其他过滤条件时
        过滤后数量 = 候选总数 − 缺设备数。

    参数：
        无。

    返回值：
        None。

    异常：
        断言失败即测试失败。
    """
    candidates = _load_all_candidates()
    assert candidates, "种子菜谱为空，请先执行 python -m app.seed"

    with SessionLocal() as session:
        filtered, counts = hard_filter(session, candidates, SafetyProfile(equipment=["炒锅"]))

    expected = sum(1 for c in candidates if find_missing_equipment(c.get("equipment") or [], ["炒锅"]))
    assert expected >= 1
    assert counts["equipment"] == expected
    # 无其他条件叠加时数量守恒
    assert len(filtered) == len(candidates) - expected


def test_equipment_filter_skipped_when_profile_empty() -> None:
    """档案设备为空（未设置）时设备维度不生效（函数）。

    说明：
        equipment=[] 与未设 equipment 的 SafetyProfile 过滤行为完全一致：
        counts['equipment']=0、过滤集合相同——避免新用户全空结果。

    参数：
        无。

    返回值：
        None。

    异常：
        断言失败即测试失败。
    """
    candidates = _load_all_candidates()
    assert candidates, "种子菜谱为空，请先执行 python -m app.seed"

    with SessionLocal() as session:
        filtered_empty, counts_empty = hard_filter(session, candidates, SafetyProfile(equipment=[]))
        filtered_none, counts_none = hard_filter(session, candidates, SafetyProfile())

    assert counts_empty["equipment"] == 0
    assert counts_none["equipment"] == 0
    assert {int(c["recipe_id"]) for c in filtered_empty} == {int(c["recipe_id"]) for c in filtered_none}
    # 未启用设备过滤时数量守恒（全部候选保留）
    assert len(filtered_empty) == len(candidates)


def test_allergen_and_equipment_combined() -> None:
    """过敏原与设备维度叠加过滤互不破坏（函数）。

    说明：
        既有过敏原/忌口硬过滤语义保持：叠加 equipment 后结果集既不含蛋、
        也无缺失设备；两维度计数各自独立准确（单条件口径）。

    参数：
        无。

    返回值：
        None。

    异常：
        断言失败即测试失败。
    """
    candidates = _load_all_candidates()
    assert candidates, "种子菜谱为空，请先执行 python -m app.seed"
    profile = SafetyProfile(user_allergen_codes=["egg"], equipment=["炒锅"])

    with SessionLocal() as session:
        filtered, counts = hard_filter(session, candidates, profile)

    leaked_egg = [
        c for c in filtered
        if "egg" in (c.get("allergen_codes") or []) or "egg" in (c.get("ingredient_allergen_codes") or [])
    ]
    assert leaked_egg == []
    leaked_equipment = [c for c in filtered if find_missing_equipment(c.get("equipment") or [], ["炒锅"])]
    assert leaked_equipment == []
    expected_egg = sum(
        1 for c in candidates
        if "egg" in (c.get("allergen_codes") or []) or "egg" in (c.get("ingredient_allergen_codes") or [])
    )
    expected_equipment = sum(
        1 for c in candidates if find_missing_equipment(c.get("equipment") or [], ["炒锅"])
    )
    assert counts["allergen"] == expected_egg
    assert counts["equipment"] == expected_equipment


def test_filtered_replay_equipment_reason(client: TestClient) -> None:
    """过滤重放清单含设备原因条目（函数）。

    说明：
        POST /v1/recommend/filtered 携带 equipment=["炒锅"]：
        - 条目 reason 类型码扩展为含 equipment（allergen/taboo/difficulty/equipment）；
        - 存在 reason="equipment" 的条目，其 reasons 数组含
          {"type": "equipment", "detail": 以「缺少设备：」开头且含「燃气灶」}；
        - 请求不携带 equipment 时不产生设备原因（向后兼容）。

    参数：
        client：TestClient fixture。

    返回值：
        None。

    异常：
        断言失败即测试失败。
    """
    resp = client.post(
        "/v1/recommend/filtered",
        json={"ingredients": [{"name": "土豆"}], "equipment": ["炒锅"]},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["total_filtered"] == len(body["filtered"])
    assert body["total_filtered"] >= 1
    for item in body["filtered"]:
        assert item["reason"] in ("allergen", "taboo", "difficulty", "equipment")
        assert item["recipe_id"] > 0
        assert item["recipe_name"]
        assert isinstance(item["reasons"], list) and item["reasons"]
        for r in item["reasons"]:
            assert r["type"] in ("allergen", "taboo", "difficulty", "equipment")
            assert r["detail"]
    equipment_items = [item for item in body["filtered"] if item["reason"] == "equipment"]
    assert equipment_items, "土豆候选应存在仅缺设备的菜谱（种子含燃气灶菜谱）"
    assert any(
        any(
            r["type"] == "equipment" and r["detail"].startswith("缺少设备：") and "燃气灶" in r["detail"]
            for r in item["reasons"]
        )
        for item in equipment_items
    ), "设备原因明细应为「缺少设备：燃气灶」格式"

    # 不携带 equipment → 不产生设备原因（向后兼容既有契约）
    resp_plain = client.post("/v1/recommend/filtered", json={"ingredients": [{"name": "土豆"}]})
    assert resp_plain.status_code == 200
    for item in resp_plain.json()["filtered"]:
        assert item["reason"] in ("allergen", "taboo", "difficulty")
        assert all(r["type"] != "equipment" for r in item["reasons"])


def test_recommend_e2e_excludes_missing_stove(client: TestClient) -> None:
    """端到端：档案设备经 runner 载入，推荐结果排除缺灶具菜谱（函数）。

    说明：
        新建用户 + user_skill_profile(equipment=['炒锅']) → run_recommend：
        - 推荐结果不含任何需燃气灶菜谱（缺陷 M2/P6/S8 主场景）；
        - filtered_by 携带 equipment 维度计数且 ≥1；
        - finally 清理测试用户（级联清理 skill profile）。

    参数：
        client：TestClient fixture（保证应用上下文）。

    返回值：
        None。

    异常：
        断言失败即测试失败。
    """
    anon = f"anon_eq_filter_{uuid.uuid4().hex[:10]}"
    with SessionLocal() as session:
        user = User(anonymous_id=anon)
        session.add(user)
        session.flush()
        user_id = int(user.id)
        session.add(
            UserSkillProfile(
                user_id=user_id, skill_level="beginner", difficulty_cap=1, equipment=["炒锅"]
            )
        )
        session.commit()
    try:
        # 食材按名称字符串传入（与 API 层 _resolve_ingredient_names 归一口径一致，
        # supervisor 空文本 + 有食材 → recommend_by_ingredients 关键词兜底）
        response = run_recommend({"ingredients": ["黄瓜"], "user_id": user_id})
        assert not response.get("blocked"), "纯食材推荐不应触发一票否决"
        results = list(response.get("results") or [])
        assert results, "黄瓜候选中应有可做的菜（凉拌黄瓜仅需菜刀/砧板，豁免）"
        # 推荐结果不含需燃气灶菜谱（布尔排除，非降权）
        for item in results:
            missing = find_missing_equipment(item.get("equipment") or [], ["炒锅"])
            assert missing == [], f"结果 {item.get('title')} 缺失设备 {missing}，不应出现在推荐中"
        # 过滤统计含设备维度计数
        filtered_by = response.get("filtered_by") or {}
        assert filtered_by.get("equipment", 0) >= 1, "需燃气灶菜谱应计入设备维度过滤统计"
    finally:
        with SessionLocal() as session:
            session.execute(delete(UserSkillProfile).where(UserSkillProfile.user_id == user_id))
            session.execute(delete(User).where(User.id == user_id))
            session.commit()


def test_recommend_e2e_empty_equipment_keeps_results(client: TestClient) -> None:
    """端到端：无设备档案用户推荐行为与既有链路一致（函数）。

    说明：
        新建用户但【不写】user_skill_profile → runner 设备档案为空 →
        设备维度不生效：需燃气灶菜谱正常出现在推荐结果（向后兼容回归）。

    参数：
        client：TestClient fixture（保证应用上下文）。

    返回值：
        None。

    异常：
        断言失败即测试失败。
    """
    anon = f"anon_eq_empty_{uuid.uuid4().hex[:10]}"
    with SessionLocal() as session:
        user = User(anonymous_id=anon)
        session.add(user)
        session.flush()
        user_id = int(user.id)
        session.commit()
    try:
        response = run_recommend({"ingredients": ["土豆"], "user_id": user_id})
        results = list(response.get("results") or [])
        assert results, "无设备档案用户应保持既有推荐行为"
        assert any(
            "燃气灶" in (item.get("equipment") or []) for item in results
        ), "设备档案为空时设备维度不生效，需燃气灶菜谱应正常出现"
        assert (response.get("filtered_by") or {}).get("equipment", 0) == 0
    finally:
        with SessionLocal() as session:
            session.execute(delete(User).where(User.id == user_id))
            session.commit()
