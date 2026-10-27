"""用户档案 API 集成测试（Task 2 / 模块 C + A.6 + R-2 收敛）。

覆盖：
    - GET /v1/profile/family 自动建档（幂等同一 family_id）；
    - POST /v1/profile/members 过敏原三选一必选校验（缺过敏原 422 / 带 peanut 201）；
    - PUT /v1/profile/members/{id} 增量更新（口味）与 DELETE 204（允许删空）；
    - PUT /v1/profile/skill 13 项设备白名单（白名单外 422）；
    - PUT /v1/profile/diet-goal 疾病相关目标 warning 提示；
    - POST /v1/consent/sensitive 落库 consent_record（幂等复用同一 consent_id）；
    - R-2 档案过敏原驱动硬过滤：档案 peanut → /v1/recommend 过滤含花生候选；
    - R-2 payload 覆盖档案：payload egg > 档案 peanut（按 egg 过滤）；
    - 兜底单测：直接调 hard_filter 验证 SafetyProfile 过滤语义。

数据约定：
    真实库 aicook；每个测试用唯一 anon_ 前缀匿名用户自建数据，测试结束自清理
    （family → user 级联删除成员/技能/目标/同意行），不触碰共享种子数据。
"""

from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete, select, text

from app.ability import hard_filter, retrieve_candidates
from app.api.v1 import profile as _profile_router_module
from app.core.db import SessionLocal
from app.graph.runner import run_recommend
from app.main import app
from app.models import ConsentRecord, Family, User
from app.safety import SafetyProfile
from tests.conftest import ensure_router_registered

# 兜底注册（幂等）：profile 路由由主控在 app/api/v1/router.py 统一 include，
# 该注册完成前测试自行挂载到 app（检测到 /v1/profile/family 已存在即跳过），
# 主控注册后本段自动失效，不会产生重复路由。
ensure_router_registered(
    app,
    (_profile_router_module.router,),
    flag="_profile_routes_registered",
    prefix="/v1",
    probe_paths=("/v1/profile/family",),
)


def _unique_anon_id() -> str:
    """生成测试专用唯一匿名 ID（函数）。

    返回值：
        str：anon_test_ 前缀 + uuid4 短串（与生产 anon_ 前缀可区分）。

    异常：
        无。
    """
    return f"anon_test_{uuid.uuid4().hex[:10]}"


def _headers(anon_id: str) -> dict[str, str]:
    """构造携带匿名身份的请求头（函数）。

    参数：
        anon_id：匿名会话 ID。

    返回值：
        dict[str, str]：{X-Anonymous-Id: anon_id}。

    异常：
        无。
    """
    return {"X-Anonymous-Id": anon_id}


def _cleanup(anon_id: str) -> None:
    """清理测试用户及其档案数据（函数）。

    说明：
        先删 family（成员行经 FK ON DELETE CASCADE 级联清理），再删 user
        （disclaimer_consent/consent_record/user_skill_profile/diet_goal 均 CASCADE）；
        不触碰共享种子数据。

    参数：
        anon_id：待清理的匿名会话 ID。

    返回值：
        None。

    异常：
        不抛出（清理失败不影响测试结果判定，仅遗留数据）。
    """
    try:
        with SessionLocal() as session:
            user_id = session.execute(
                select(User.id).where(User.anonymous_id == anon_id)
            ).scalar_one_or_none()
            if user_id is None:
                return
            session.execute(delete(Family).where(Family.user_id == int(user_id)))
            user = session.get(User, int(user_id))
            if user is not None:
                session.delete(user)
            session.commit()
    except Exception:  # noqa: BLE001 —— 清理失败不掩盖测试断言结果
        pass


@pytest.fixture()
def anon_id(client: TestClient):
    """唯一匿名用户 fixture（函数）。

    说明：
        依赖 client 触发应用生命周期；yield 唯一匿名 ID，测试结束后清理该用户
        全部档案数据。

    参数：
        client：TestClient fixture。

    返回值：
        str：唯一匿名会话 ID。

    异常：
        无。
    """
    anon = _unique_anon_id()
    yield anon
    _cleanup(anon)


def _create_member(client: TestClient, anon: str, **overrides) -> tuple[int, dict]:
    """调用新增成员接口（函数）。

    参数：
        client：TestClient。
        anon：匿名会话 ID。
        **overrides：覆盖默认成员字段的键值。

    返回值：
        tuple[int, dict]：(HTTP 状态码, 响应 JSON)。

    异常：
        无。
    """
    body = {"name": "测试成员", "no_known_allergen": True}
    body.update(overrides)
    resp = client.post("/v1/profile/members", json=body, headers=_headers(anon))
    return resp.status_code, resp.json()


# ---------------------------------------------------------------------------
# 1. GET family 自动建档
# ---------------------------------------------------------------------------

def test_get_family_auto_create(client: TestClient, anon_id: str) -> None:
    """GET /v1/profile/family 自动建档且幂等（函数）。

    参数：
        client：TestClient fixture。
        anon_id：唯一匿名用户 fixture。

    返回值：
        None。

    异常：
        断言失败即测试失败。
    """
    resp1 = client.get("/v1/profile/family", headers=_headers(anon_id))
    assert resp1.status_code == 200
    body1 = resp1.json()
    assert body1["name"] == "我的家庭"
    assert body1["members"] == []
    first_family_id = body1["family_id"]
    assert isinstance(first_family_id, int)

    # 幂等：重复 GET 返回同一家庭（不重复建行）
    resp2 = client.get("/v1/profile/family", headers=_headers(anon_id))
    assert resp2.status_code == 200
    assert resp2.json()["family_id"] == first_family_id


# ---------------------------------------------------------------------------
# 2. POST member 缺过敏原 → 422
# ---------------------------------------------------------------------------

def test_post_member_missing_allergen_422(client: TestClient, anon_id: str) -> None:
    """过敏原三选一未满足 → 422（函数）。

    参数：
        client：TestClient fixture。
        anon_id：唯一匿名用户 fixture。

    返回值：
        None。

    异常：
        断言失败即测试失败。
    """
    status, body = _create_member(
        client,
        anon_id,
        allergen_codes=[],
        custom_allergens=[],
        no_known_allergen=False,
    )
    assert status == 422
    assert body["code"] == "VALIDATION_ERROR"
    assert "过敏原为必选" in body["detail"]


# ---------------------------------------------------------------------------
# 3. POST member 带 peanut → 201（含自定义过敏原回读）
# ---------------------------------------------------------------------------

def test_post_member_with_peanut_201(client: TestClient, anon_id: str) -> None:
    """带 peanut 编码建档 201，自定义过敏原拆分还原（函数）。

    参数：
        client：TestClient fixture。
        anon_id：唯一匿名用户 fixture。

    返回值：
        None。

    异常：
        断言失败即测试失败。
    """
    status, body = _create_member(
        client,
        anon_id,
        allergen_codes=["peanut"],
        custom_allergens=[],
        no_known_allergen=False,
        taste_spicy=2,
        relation="孩子",
        age_group="4-12",
    )
    assert status == 201
    assert isinstance(body["id"], int)
    assert body["allergen_codes"] == ["peanut"]
    assert body["custom_allergens"] == []
    assert body["no_known_allergen"] is False
    assert body["taste_spicy"] == 2
    assert body["relation"] == "孩子"
    assert body["age_group"] == "4-12"

    # 自定义过敏原：与八类编码分开存储、分开回读
    status, custom_body = _create_member(
        client,
        anon_id,
        allergen_codes=["egg", "milk"],
        custom_allergens=["芒果", "芒果", " "],
        no_known_allergen=False,
    )
    assert status == 201
    assert custom_body["allergen_codes"] == ["egg", "milk"]
    assert custom_body["custom_allergens"] == ["芒果"]

    # GET 回读一致
    resp = client.get("/v1/profile/family", headers=_headers(anon_id))
    assert resp.status_code == 200
    members = resp.json()["members"]
    assert len(members) == 2
    by_id = {m["id"]: m for m in members}
    assert by_id[body["id"]]["allergen_codes"] == ["peanut"]
    assert by_id[body["id"]]["relation"] == "孩子"
    assert by_id[body["id"]]["age_group"] == "4-12"
    assert by_id[custom_body["id"]]["allergen_codes"] == ["egg", "milk"]
    assert by_id[custom_body["id"]]["custom_allergens"] == ["芒果"]


# ---------------------------------------------------------------------------
# 4. PUT member 更新口味（增量语义）
# ---------------------------------------------------------------------------

def test_put_member_update_taste(client: TestClient, anon_id: str) -> None:
    """PUT /v1/profile/members/{id} 增量更新口味（函数）。

    参数：
        client：TestClient fixture。
        anon_id：唯一匿名用户 fixture。

    返回值：
        None。

    异常：
        断言失败即测试失败。
    """
    status, created = _create_member(
        client,
        anon_id,
        allergen_codes=["peanut"],
        no_known_allergen=False,
        taste_salt=1,
    )
    assert status == 201
    member_id = created["id"]

    resp = client.put(
        f"/v1/profile/members/{member_id}",
        json={"taste_spicy": 2, "taste_salt": 0, "relation": "父母", "age_group": "60+"},
        headers=_headers(anon_id),
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["taste_spicy"] == 2
    assert body["taste_salt"] == 0
    assert body["relation"] == "父母"
    assert body["age_group"] == "60+"
    # 未提供字段保持原值（过敏原不被增量更新清空）
    assert body["allergen_codes"] == ["peanut"]
    assert body["taste_sweet"] == created["taste_sweet"]

    # GET 回读一致
    resp = client.get("/v1/profile/family", headers=_headers(anon_id))
    member = next(m for m in resp.json()["members"] if m["id"] == member_id)
    assert member["taste_spicy"] == 2 and member["taste_salt"] == 0
    assert member["relation"] == "父母" and member["age_group"] == "60+"


# ---------------------------------------------------------------------------
# 5. DELETE member → 204（允许删空，重复删除 404）
# ---------------------------------------------------------------------------

def test_delete_member_204(client: TestClient, anon_id: str) -> None:
    """DELETE /v1/profile/members/{id} 204 且允许删空（函数）。

    参数：
        client：TestClient fixture。
        anon_id：唯一匿名用户 fixture。

    返回值：
        None。

    异常：
        断言失败即测试失败。
    """
    status, created = _create_member(client, anon_id)
    assert status == 201
    member_id = created["id"]

    resp = client.delete(f"/v1/profile/members/{member_id}", headers=_headers(anon_id))
    assert resp.status_code == 204

    # 家庭允许删空
    resp = client.get("/v1/profile/family", headers=_headers(anon_id))
    assert resp.status_code == 200
    assert resp.json()["members"] == []

    # 重复删除 → 404
    resp = client.delete(f"/v1/profile/members/{member_id}", headers=_headers(anon_id))
    assert resp.status_code == 404
    assert resp.json()["code"] == "NOT_FOUND"


# ---------------------------------------------------------------------------
# 6. skill 白名单外设备 → 422（合法设备正常保存）
# ---------------------------------------------------------------------------

def test_put_skill_equipment_whitelist(client: TestClient, anon_id: str) -> None:
    """PUT /v1/profile/skill 设备白名单校验（函数）。

    参数：
        client：TestClient fixture。
        anon_id：唯一匿名用户 fixture。

    返回值：
        None。

    异常：
        断言失败即测试失败。
    """
    # 白名单外设备 → 422
    resp = client.put(
        "/v1/profile/skill",
        json={"cooking_level": 2, "equipment": ["炒锅", "洗碗机"]},
        headers=_headers(anon_id),
    )
    assert resp.status_code == 422
    assert resp.json()["code"] == "VALIDATION_ERROR"

    # 合法保存：去重 + 回读
    resp = client.put(
        "/v1/profile/skill",
        json={"cooking_level": 3, "equipment": ["炒锅", "电饭煲", "炒锅"]},
        headers=_headers(anon_id),
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["cooking_level"] == 3
    assert body["equipment"] == ["炒锅", "电饭煲"]

    resp = client.get("/v1/profile/skill", headers=_headers(anon_id))
    assert resp.status_code == 200
    assert resp.json() == {"cooking_level": 3, "equipment": ["炒锅", "电饭煲"]}


# ---------------------------------------------------------------------------
# 7. diet-goal light_salt 返回 warning
# ---------------------------------------------------------------------------

def test_diet_goal_light_salt_warning(client: TestClient, anon_id: str) -> None:
    """疾病相关目标附加健康提示语（函数）。

    参数：
        client：TestClient fixture。
        anon_id：唯一匿名用户 fixture。

    返回值：
        None。

    异常：
        断言失败即测试失败。
    """
    resp = client.put(
        "/v1/profile/diet-goal",
        json={"goal": "light_salt", "note": "医生建议少盐"},
        headers=_headers(anon_id),
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["goal"] == "light_salt"
    assert body["note"] == "医生建议少盐"
    assert body["warning"] == "饮食目标涉及健康话题，如有疾病请遵医嘱"

    # GET 返回 {goal, note}（warning 为提示性附加字段，不随 GET 重复下发）
    resp = client.get("/v1/profile/diet-goal", headers=_headers(anon_id))
    assert resp.status_code == 200
    assert resp.json()["goal"] == "light_salt"
    assert resp.json()["note"] == "医生建议少盐"

    # 非疾病相关目标不返回 warning
    resp = client.put("/v1/profile/diet-goal", json={"goal": "balanced"}, headers=_headers(anon_id))
    assert resp.status_code == 200
    assert "warning" not in resp.json()
    assert resp.json()["goal"] == "balanced"


# ---------------------------------------------------------------------------
# 8. consent/sensitive 落库成功（幂等复用）
# ---------------------------------------------------------------------------

def test_consent_sensitive_recorded(client: TestClient, anon_id: str) -> None:
    """POST /v1/consent/sensitive 落库 consent_record 且幂等（函数）。

    参数：
        client：TestClient fixture。
        anon_id：唯一匿名用户 fixture。

    返回值：
        None。

    异常：
        断言失败即测试失败。
    """
    resp = client.post("/v1/consent/sensitive", json={"scene": "family_allergen"}, headers=_headers(anon_id))
    assert resp.status_code == 201
    consent_id = resp.json()["consent_id"]
    assert isinstance(consent_id, str) and consent_id

    with SessionLocal() as session:
        user_db_id = session.execute(
            select(User.id).where(User.anonymous_id == anon_id)
        ).scalar_one_or_none()
        assert user_db_id is not None
        rows = session.execute(
            select(ConsentRecord).where(ConsentRecord.user_id == int(user_db_id))
        ).scalars().all()
        assert len(rows) == 1
        assert rows[0].scope == "allergen"
        assert rows[0].version == "SENSITIVE_V1"
        assert rows[0].agreed is True

    # 幂等：重复提交返回同一 consent_id，不重复插行
    resp2 = client.post("/v1/consent/sensitive", json={"scene": "family_allergen"}, headers=_headers(anon_id))
    assert resp2.status_code == 201
    assert resp2.json()["consent_id"] == consent_id
    with SessionLocal() as session:
        count = session.execute(
            text("SELECT count(*) FROM consent_record WHERE id = :i"), {"i": int(consent_id)}
        ).scalar()
        assert count == 1

    # 未知场景 → 422
    resp = client.post("/v1/consent/sensitive", json={"scene": "no_such_scene"}, headers=_headers(anon_id))
    assert resp.status_code == 422


# ---------------------------------------------------------------------------
# 9. R-2：档案过敏原驱动硬过滤（/v1/recommend 全链路）
# ---------------------------------------------------------------------------

def test_profile_allergen_drives_hard_filter(client: TestClient, anon_id: str) -> None:
    """档案成员过敏原 peanut → 推荐(花生米)全部候选被硬过滤（函数）。

    说明：
        采用「有档案 vs 无档案」对照断言：同一输入（花生米），建档 peanut 的用户
        结果为空、无档案用户结果非空——证明过滤由档案驱动（compose 空结果分支
        不回传 filtered_by 计数，计数证据由 test_hard_filter_peanut_excludes_candidates
        直接调 hard_filter 兜底取证）。

    参数：
        client：TestClient fixture。
        anon_id：唯一匿名用户 fixture。

    返回值：
        None。

    异常：
        断言失败即测试失败。
    """
    # 前置：花生米确有已发布菜谱引用（保证对照断言非空转）
    with SessionLocal() as session:
        peanut_recipes = session.execute(
            text(
                "SELECT count(DISTINCT r.id) FROM recipe r "
                "JOIN recipe_ingredient ri ON ri.recipe_id = r.id "
                "JOIN ingredient i ON i.id = ri.ingredient_id "
                "WHERE i.name = '花生米' AND r.status = 'published'"
            )
        ).scalar()
    assert peanut_recipes >= 1, "前置失败：花生米无已发布菜谱引用"

    # 建档：成员过敏原 peanut（不带任何 payload 过敏原）
    status, _body = _create_member(
        client, anon_id, allergen_codes=["peanut"], no_known_allergen=False
    )
    assert status == 201

    resp = client.post(
        "/v1/recommend",
        json={"request_id": f"t_{uuid.uuid4().hex[:16]}", "ingredients": [{"name": "花生米"}]},
        headers=_headers(anon_id),
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body.get("blocked") is not True, "输入「花生米」不应触发一票否决"
    assert body.get("safe_mode") is not True, "不应落入保守模式"
    # 有档案：含花生候选全部被硬过滤（结果为空，无任何含花生菜谱漏出）
    for item in body["results"]:
        assert "peanut" not in (item.get("allergens") or [])
    assert body["results"] == []

    # 对照：无档案用户同一输入 → 未过滤，结果非空（证明过滤由档案驱动）
    bare_anon = _unique_anon_id()
    try:
        resp_bare = client.post(
            "/v1/recommend",
            json={"request_id": f"t_{uuid.uuid4().hex[:16]}", "ingredients": [{"name": "花生米"}]},
            headers=_headers(bare_anon),
        )
        assert resp_bare.status_code == 200
        bare_body = resp_bare.json()
        assert bare_body.get("blocked") is not True
        assert len(bare_body["results"]) >= 1, "无档案用户应能召回含花生菜谱（对照失败）"
    finally:
        _cleanup(bare_anon)


# ---------------------------------------------------------------------------
# 9b. 兜底单测：直接调 hard_filter 验证过滤语义
# ---------------------------------------------------------------------------

def test_hard_filter_peanut_excludes_candidates() -> None:
    """SafetyProfile(peanut) 直接过滤含花生候选=0（函数，兜底取证）。

    参数：
        无。

    返回值：
        None。

    异常：
        断言失败即测试失败。
    """
    with SessionLocal() as session:
        ing_id = session.execute(
            text("SELECT id FROM ingredient WHERE name = '花生米'")
        ).scalar()
        assert ing_id is not None
        candidates = retrieve_candidates(session, [int(ing_id)], limit=200)
        assert candidates, "前置失败：花生米无召回候选"
        filtered, counts = hard_filter(session, candidates, SafetyProfile(user_allergen_codes=["peanut"]))
        assert filtered == []
        assert counts["allergen"] >= 1


# ---------------------------------------------------------------------------
# 10. R-2：payload 覆盖档案（payload egg > 档案 peanut）
# ---------------------------------------------------------------------------

def test_payload_overrides_profile(client: TestClient, anon_id: str) -> None:
    """payload 显式过敏原 egg 覆盖档案 peanut（函数）。

    说明：
        直接调用 runner.run_recommend（/v1/recommend 请求体无 allergen_codes
        字段，覆盖语义在 runner 传参层生效）：档案 peanut、payload egg 时按
        egg 过滤——引用鸡蛋的菜谱（egg-no-peanut 占多数）应全部被排除。

    参数：
        client：TestClient fixture。
        anon_id：唯一匿名用户 fixture。

    返回值：
        None。

    异常：
        断言失败即测试失败。
    """
    # 前置：鸡蛋确有已发布菜谱引用
    with SessionLocal() as session:
        egg_recipes = session.execute(
            text(
                "SELECT count(DISTINCT r.id) FROM recipe r "
                "JOIN recipe_ingredient ri ON ri.recipe_id = r.id "
                "JOIN ingredient i ON i.id = ri.ingredient_id "
                "WHERE i.name = '鸡蛋' AND r.status = 'published'"
            )
        ).scalar()
    assert egg_recipes >= 1, "前置失败：鸡蛋无已发布菜谱引用"

    # 建档：档案过敏原 peanut（同时经 API 创建匿名用户行）
    status, _body = _create_member(
        client, anon_id, allergen_codes=["peanut"], no_known_allergen=False
    )
    assert status == 201

    with SessionLocal() as session:
        user_db_id = session.execute(
            select(User.id).where(User.anonymous_id == anon_id)
        ).scalar_one_or_none()
    assert user_db_id is not None

    base_payload = {
        "request_id": f"t_{uuid.uuid4().hex[:16]}",
        "ingredients": ["鸡蛋"],
        "text": "",
        "user_id": int(user_db_id),
    }

    # payload 显式 egg > 档案 peanut：按 egg 过滤 → 引用鸡蛋的候选全部排除
    response = run_recommend({**base_payload, "allergen_codes": ["egg"]})
    assert response.get("blocked") is not True
    assert response.get("safe_mode") is not True
    # 若误用档案 peanut 过滤，47 个「含蛋不含花生」菜谱会漏出 → 结果非空；
    # 按 egg 过滤则引用鸡蛋的候选全部排除 → 结果为空（payload 覆盖档案的判据；
    # compose 空结果分支不写 results 键，故用 .get 兜底）
    assert (response.get("results") or []) == []

    # 对照：同一用户不带 payload 过敏原 → 档案 peanut 过滤，含蛋不含花生的菜谱漏出
    response_bare = run_recommend({**base_payload, "allergen_codes": []})
    assert response_bare.get("blocked") is not True
    assert len(response_bare.get("results") or []) >= 1, "档案 peanut 过滤下应存在含蛋不含花生菜谱（对照失败）"
