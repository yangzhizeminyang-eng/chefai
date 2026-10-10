"""AI 菜品创新集成测试（模块 O，Task 7）。

覆盖：
    - precheck：正常组合（鸡蛋+西红柿）ok 且 pairings 命中 recommend 依据；
      高危食材（发芽土豆）blocked + risk_log 留痕 + generate 同语义拦截；
      过敏原红线（建档 peanut 用户 + 含花生食材 → 直接拒绝）；
      taboo 查表拦截（韭菜+酸奶）；
    - generate：201、用量 100% 量化（无适量/少许/若干）、步骤含时长、
      is_ai_innovated=true、disclaimer 存在、basis 非空、status=generated
      （LLM 离线走本地模板降级路径）；
    - 状态机：adopt→index 合法流转；重复流转/非法流转（generated→index）422；
    - reuse：本人 200 / 他人 404（跨用户隔离）；
    - index：recipe_embedding 行存在且 source='ai_private'、owner 正确、
      recipe_id 为空（默认 verified 检索不含 AI 私有行）；
    - feedback 回流：rating 5 → 对应搭配规则权重 +0.1（DB 断言，try/finally 还原）；
    - switch.innovation=false → 全部 7 端点 503 维护态。

数据约定：
    真实本地库自建自清理：测试用户/家庭档案自建，fixture teardown 删用户行
    （innovation_recipe / recipe_embedding / family 均随 user 级联删除）；
    remote_config 开关与 flavor_pairing_rule.weight 修改均 try/finally 还原。
"""

from __future__ import annotations

import json
import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.api.v1 import innovation as innovation_api
from app.api.v1.router import api_router
from app.core.db import SessionLocal
from app.models import (
    Family,
    FamilyMember,
    FlavorPairingRule,
    InnovationRecipe,
    RecipeEmbedding,
    RemoteConfig,
    RiskLog,
    User,
)

# 并行开发约定：router.py 由集成步骤统一注册；未注册时此处补注册（进程级标记守卫，
# 避免 OpenAPI Duplicate Operation ID 告警；注册后本守卫自动跳过）。
if not getattr(api_router, "_t7_innovation_registered", False):
    api_router.include_router(innovation_api.router)
    api_router._t7_innovation_registered = True


def _headers(anon: str) -> dict:
    """构造带匿名身份的请求头（函数）。

    参数：
        anon：匿名会话 ID。

    返回值：
        dict：X-Anonymous-Id 请求头。

    异常：
        无。
    """
    return {"X-Anonymous-Id": anon}


def _anon() -> str:
    """生成唯一测试匿名 ID（函数）。

    返回值：
        str：anon_t7inv_ 前缀唯一 ID。

    异常：
        无。
    """
    return f"anon_t7inv_{uuid.uuid4().hex[:10]}"


def _delete_user(anon: str) -> None:
    """按匿名 ID 删除用户行（级联清理自建数据）（函数）。

    说明：
        family 外键无 DB 级联，需先删家庭行（members 随 ORM relationship
        cascade 删除）；innovation_recipe / recipe_embedding 随 user 的
        DB 级联（ondelete=CASCADE）删除。

    参数：
        anon：匿名会话 ID。

    返回值：
        None。

    异常：
        数据库异常向上抛出。
    """
    with SessionLocal() as db:
        user = db.execute(select(User).where(User.anonymous_id == anon)).scalar_one_or_none()
        if user is not None:
            families = db.execute(
                select(Family).where(Family.user_id == int(user.id))
            ).scalars().all()
            for family in families:
                db.delete(family)
            # 显式 flush：SQLAlchemy 未声明 user↔family 关系依赖，需先执行
            # DELETE FROM family 再删 user，否则 flush 顺序可能违反外键约束
            db.flush()
            db.delete(user)
            db.commit()


def _get_user_id(anon: str) -> int | None:
    """按匿名 ID 查询用户主键（函数）。

    参数：
        anon：匿名会话 ID。

    返回值：
        int | None：用户 ID；不存在返回 None。

    异常：
        数据库异常向上抛出。
    """
    with SessionLocal() as db:
        return db.execute(select(User.id).where(User.anonymous_id == anon)).scalar_one_or_none()


def _build_allergen_profile(anon: str, allergen_codes: list[str], special: list[str] | None = None) -> int:
    """直接建库档：用户 + 家庭 + 成员过敏原/特殊人群（函数）。

    说明：
        走 DB 直写（与 profile API 无耦合），供预检的档案类红线测试。

    参数：
        anon：匿名会话 ID（用户不存在时自建）。
        allergen_codes：成员过敏原 code 集合（GB 7718 八类）。
        special：特殊人群标记（可 None）。

    返回值：
        int：用户数据库 ID。

    异常：
        数据库异常向上抛出。
    """
    with SessionLocal() as db:
        user = db.execute(select(User).where(User.anonymous_id == anon)).scalar_one_or_none()
        if user is None:
            user = User(anonymous_id=anon)
            db.add(user)
            db.flush()
        family = Family(user_id=int(user.id), name="T7 创新测试家庭")
        db.add(family)
        db.flush()
        db.add(
            FamilyMember(
                family_id=int(family.id),
                nickname="测试成员",
                age_group="18-59",
                allergen_codes=list(allergen_codes),
                special_population=list(special or []),
            )
        )
        db.commit()
        return int(user.id)


def _generate_recipe(client: TestClient, anon: str, ingredients: tuple[str, ...] = ("鸡蛋", "西红柿")) -> int:
    """生成一道创新菜并返回其 ID（函数）。

    参数：
        client：TestClient fixture。
        anon：匿名身份。
        ingredients：食材名列表。

    返回值：
        int：innovation_recipe.id。

    异常：
        断言失败即测试失败。
    """
    resp = client.post(
        "/v1/innovation/generate", json={"ingredients": list(ingredients)}, headers=_headers(anon)
    )
    assert resp.status_code == 201, resp.text
    return int(resp.json()["recipe"]["id"])


@pytest.fixture()
def anon_id() -> str:
    """唯一匿名 ID fixture（函数，teardown 级联清理）。

    返回值：
        str：唯一匿名 ID。

    异常：
        清理失败向上抛出。
    """
    value = _anon()
    yield value
    _delete_user(value)


# ---------------------------------------------------------------------------
# 1) precheck 正常组合：ok=true 且 pairings 命中 recommend 依据
# ---------------------------------------------------------------------------
def test_precheck_normal_and_pairing_basis(client: TestClient, anon_id: str) -> None:
    """预检正常组合通过并给出推荐搭配依据（函数）。

    参数：
        client：TestClient fixture。
        anon_id：唯一匿名身份 fixture。

    返回值：
        None。

    异常：
        断言失败即测试失败。
    """
    resp = client.post(
        "/v1/innovation/precheck",
        json={"ingredients": ["鸡蛋", "西红柿"]},
        headers=_headers(anon_id),
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["ok"] is True
    assert body["blocked"] is False
    assert body["issues"] == []
    assert body["risk_log_written"] is False
    # pairings 命中 recommend 依据（番茄 × 鸡蛋 为 seed recommend 规则）
    pairings = body.get("pairings") or []
    assert pairings, "正常组合应命中推荐搭配依据"
    assert any(p["relation"] == "recommend" for p in pairings)
    assert all(p["rule_id"] for p in pairings)


# ---------------------------------------------------------------------------
# 2) precheck 高危食材：blocked + risk_log 留痕；generate 同语义拦截
# ---------------------------------------------------------------------------
def test_precheck_high_risk_blocks_and_logs(client: TestClient, anon_id: str) -> None:
    """高危食材拦截 + risk_log 留痕 + generate 复用同一拦截语义（函数）。

    参数：
        client：TestClient fixture。
        anon_id：唯一匿名身份 fixture。

    返回值：
        None。

    异常：
        断言失败即测试失败。
    """
    resp = client.post(
        "/v1/innovation/precheck",
        json={"ingredients": ["发芽土豆"]},
        headers=_headers(anon_id),
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["ok"] is False
    assert body["blocked"] is True
    assert any(issue["type"] == "high_risk" for issue in body["issues"])
    assert body["issues"][0]["message"]
    assert body["risk_log_written"] is True

    # risk_log 留痕：FS-003（发芽土豆）最新一条 action=blocked
    with SessionLocal() as db:
        row = db.execute(
            select(RiskLog).where(RiskLog.rule_code == "FS-003").order_by(RiskLog.id.desc()).limit(1)
        ).scalar_one()
        assert row.action == "blocked"
        assert row.input_digest

    # generate 生成前自动复用 precheck：同语义拦截（200 拦截体，非 201）
    gen = client.post(
        "/v1/innovation/generate",
        json={"ingredients": ["发芽土豆"]},
        headers=_headers(anon_id),
    )
    assert gen.status_code == 200
    gen_body = gen.json()
    assert gen_body["ok"] is False
    assert gen_body["blocked"] is True
    assert any(issue["type"] == "high_risk" for issue in gen_body["issues"])


# ---------------------------------------------------------------------------
# 3) precheck 过敏原红线：建档 peanut 用户 + 含花生食材 → 直接拒绝
# ---------------------------------------------------------------------------
def test_precheck_allergen_redline(client: TestClient, anon_id: str) -> None:
    """过敏原直接拒绝（🔴 核心红线断言）（函数）。

    参数：
        client：TestClient fixture。
        anon_id：唯一匿名身份 fixture。

    返回值：
        None。

    异常：
        断言失败即测试失败。
    """
    _build_allergen_profile(anon_id, ["peanut"])
    resp = client.post(
        "/v1/innovation/precheck",
        json={"ingredients": ["花生米"]},
        headers=_headers(anon_id),
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["ok"] is False
    assert body["blocked"] is True
    assert body["issues"], "过敏原命中必须有拦截原因"
    assert body["issues"][0]["type"] == "allergen"
    assert "过敏原" in body["issues"][0]["message"]
    assert body["risk_log_written"] is True
    # 留痕：自定义创新域规则 ID
    with SessionLocal() as db:
        row = db.execute(
            select(RiskLog)
            .where(RiskLog.rule_code == "INNOVATION_ALLERGEN")
            .where(RiskLog.user_id == int(_get_user_id(anon_id)))
            .order_by(RiskLog.id.desc())
            .limit(1)
        ).scalar_one_or_none()
        assert row is not None and row.action == "blocked"


# ---------------------------------------------------------------------------
# 3.1) precheck taboo 查表拦截（搭配结论必须查表）
# ---------------------------------------------------------------------------
def test_precheck_taboo_blocks(client: TestClient, anon_id: str) -> None:
    """taboo 组合查表直接拒绝（函数）。

    参数：
        client：TestClient fixture。
        anon_id：唯一匿名身份 fixture。

    返回值：
        None。

    异常：
        断言失败即测试失败。
    """
    resp = client.post(
        "/v1/innovation/precheck",
        json={"ingredients": ["韭菜", "酸奶"]},
        headers=_headers(anon_id),
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["blocked"] is True
    assert body["issues"][0]["type"] == "taboo"
    assert "不适合同烹" in body["issues"][0]["message"]


# ---------------------------------------------------------------------------
# 4) generate 成功：201 + 100% 量化 + 步骤时长 + 标识红线（LLM 离线走本地模板降级）
# ---------------------------------------------------------------------------
def test_generate_success_quantified_and_degraded(client: TestClient, anon_id: str) -> None:
    """生成成功：结构/量化/标识红线全量断言（函数）。

    说明：
        conftest 已将 LLM 指向不可达地址，本用例恰好覆盖「LLM 失败 → 本地模板
        降级」路径（generated_by=local_template，basis 可验证）。

    参数：
        client：TestClient fixture。
        anon_id：唯一匿名身份 fixture。

    返回值：
        None。

    异常：
        断言失败即测试失败。
    """
    resp = client.post(
        "/v1/innovation/generate",
        json={"ingredients": ["鸡蛋", "西红柿"]},
        headers=_headers(anon_id),
    )
    assert resp.status_code == 201
    body = resp.json()
    recipe = body["recipe"]

    # 红线标识
    assert recipe["is_ai_innovated"] is True
    assert recipe["disclaimer"]
    assert recipe["visibility"] == "private"
    assert recipe["status"] == "generated"

    # 依据非空且引用查表 recommend 规则
    basis = recipe["basis"]
    assert basis
    assert any(p["relation"] == "recommend" for p in basis["pairings"])
    assert basis["properties"], "性质依据应存在（缺失项标注待补充）"

    # 用量 100% 量化（数值 + 单位；全文无模糊词——降级模板同样受代码强制校验）
    for item in recipe["ingredients"]:
        assert isinstance(item["amount"], (int, float)) and not isinstance(item["amount"], bool)
        assert item["amount"] > 0
        assert item["unit"]
    recipe_text = json.dumps(recipe, ensure_ascii=False)
    for word in ("适量", "少许", "若干"):
        assert word not in recipe_text

    # 步骤可执行（含时长秒）
    assert recipe["steps"]
    for step in recipe["steps"]:
        assert isinstance(step["duration_sec"], (int, float)) and step["duration_sec"] > 0
        assert step["description"]

    # 营养估算口径（缺失 excluded 标注）
    assert recipe["nutrition"]["estimate_note"]
    assert "excluded_items" in recipe["nutrition"]

    # LLM 离线 → 本地模板降级（generated_by 可验证降级路径生效）
    assert basis["generated_by"] == "local_template"

    # DB 行核对
    with SessionLocal() as db:
        row = db.get(InnovationRecipe, int(recipe["id"]))
        assert row is not None
        assert row.status == "generated"
        assert row.is_ai_innovated is True
        assert row.user_id == int(_get_user_id(anon_id))
        assert row.source_pairing_rule_ids, "落库应记录引用的搭配规则 ID"


# ---------------------------------------------------------------------------
# 5) 状态机：adopt→index 合法流转；重复/非法流转 422
# ---------------------------------------------------------------------------
def test_adopt_index_state_machine(client: TestClient, anon_id: str) -> None:
    """adopt→index 状态机与非法流转（函数）。

    参数：
        client：TestClient fixture。
        anon_id：唯一匿名身份 fixture。

    返回值：
        None。

    异常：
        断言失败即测试失败。
    """
    recipe_id = _generate_recipe(client, anon_id)

    # generated → adopt
    adopt = client.post(f"/v1/innovation/recipes/{recipe_id}/adopt", headers=_headers(anon_id))
    assert adopt.status_code == 200
    assert adopt.json()["status"] == "adopted"
    assert adopt.json()["is_ai_innovated"] is True

    # 重复采纳 → 422
    assert client.post(f"/v1/innovation/recipes/{recipe_id}/adopt", headers=_headers(anon_id)).status_code == 422

    # adopted → indexed
    index = client.post(f"/v1/innovation/recipes/{recipe_id}/index", headers=_headers(anon_id))
    assert index.status_code == 200
    assert index.json()["status"] == "indexed"
    assert index.json()["embedding_id"]

    # 重复入索引 → 422
    assert client.post(f"/v1/innovation/recipes/{recipe_id}/index", headers=_headers(anon_id)).status_code == 422

    # 非法流转：generated 直接 index → 422
    recipe2 = _generate_recipe(client, anon_id)
    assert client.post(f"/v1/innovation/recipes/{recipe2}/index", headers=_headers(anon_id)).status_code == 422

    # 不存在/他人资源 → 404 由 reuse 用例覆盖；此处补不存在 adopt 404
    assert client.post("/v1/innovation/recipes/999999999/adopt", headers=_headers(anon_id)).status_code == 404


# ---------------------------------------------------------------------------
# 6) reuse：本人 200 / 他人 404（跨用户隔离）
# ---------------------------------------------------------------------------
def test_reuse_isolation(client: TestClient, anon_id: str) -> None:
    """复用接口跨用户隔离（函数）。

    参数：
        client：TestClient fixture。
        anon_id：唯一匿名身份 fixture。

    返回值：
        None。

    异常：
        断言失败即测试失败。
    """
    recipe_id = _generate_recipe(client, anon_id)

    # generated 未采纳 → 422（仅 indexed/adopted 可复用）
    assert client.post(f"/v1/innovation/recipes/{recipe_id}/reuse", headers=_headers(anon_id)).status_code == 422

    # 采纳后本人复用 200
    assert client.post(f"/v1/innovation/recipes/{recipe_id}/adopt", headers=_headers(anon_id)).status_code == 200
    reused = client.post(f"/v1/innovation/recipes/{recipe_id}/reuse", headers=_headers(anon_id))
    assert reused.status_code == 200
    recipe = reused.json()["recipe"]
    assert recipe["id"] == recipe_id
    assert recipe["disclaimer"]
    assert recipe["is_ai_innovated"] is True

    # 他人复用/查看 → 404（🔴 跨用户隔离）
    other = _anon()
    try:
        assert client.post(f"/v1/innovation/recipes/{recipe_id}/reuse", headers=_headers(other)).status_code == 404
        assert client.get(f"/v1/innovation/recipes/{recipe_id}", headers=_headers(other)).status_code == 404
    finally:
        _delete_user(other)


# ---------------------------------------------------------------------------
# 7) index 写入 ai_private 向量分区：行存在、owner 正确、默认检索不含
# ---------------------------------------------------------------------------
def test_index_writes_ai_private_embedding(client: TestClient, anon_id: str) -> None:
    """index 后向量行断言（source/owner/innovation 三要素）（函数）。

    参数：
        client：TestClient fixture。
        anon_id：唯一匿名身份 fixture。

    返回值：
        None。

    异常：
        断言失败即测试失败。
    """
    recipe_id = _generate_recipe(client, anon_id)
    assert client.post(f"/v1/innovation/recipes/{recipe_id}/adopt", headers=_headers(anon_id)).status_code == 200
    index = client.post(f"/v1/innovation/recipes/{recipe_id}/index", headers=_headers(anon_id))
    assert index.status_code == 200
    embedding_id = int(index.json()["embedding_id"])

    uid = int(_get_user_id(anon_id))
    with SessionLocal() as db:
        row = db.get(RecipeEmbedding, embedding_id)
        assert row is not None
        assert row.source == "ai_private"
        assert int(row.owner_user_id) == uid
        assert int(row.innovation_recipe_id) == recipe_id
        # recipe_id 为空：默认 verified 检索（官方菜谱分区）不含 AI 私有行
        assert row.recipe_id is None
        assert row.embedding_json, "向量（便携列）应已写入"


# ---------------------------------------------------------------------------
# 8) feedback 回流：rating 5 → 对应搭配规则 weight 增加（DB 断言 + 还原）
# ---------------------------------------------------------------------------
def test_feedback_adjusts_pairing_weight(client: TestClient, anon_id: str) -> None:
    """评分回流调整搭配规则权重（函数）。

    参数：
        client：TestClient fixture。
        anon_id：唯一匿名身份 fixture。

    返回值：
        None。

    异常：
        断言失败即测试失败。
    """
    recipe_id = _generate_recipe(client, anon_id, ("鸡蛋", "西红柿"))
    with SessionLocal() as db:
        row = db.get(InnovationRecipe, recipe_id)
        rule_id = int(row.basis["pairings"][0]["rule_id"])
        before = float(db.get(FlavorPairingRule, rule_id).weight)

    resp = client.post(
        f"/v1/innovation/recipes/{recipe_id}/feedback",
        json={"rating": 5},
        headers=_headers(anon_id),
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"
    assert resp.json()["adjusted_rules"] >= 1
    try:
        with SessionLocal() as db:
            after = float(db.get(FlavorPairingRule, rule_id).weight)
        assert after == pytest.approx(min(3.0, before + 0.1))
    finally:
        # 还原种子规则权重（try/finally 保证不污染后续测试）
        with SessionLocal() as db:
            rule = db.get(FlavorPairingRule, rule_id)
            rule.weight = before
            db.commit()

    # rating=3 不调整权重
    neutral = client.post(
        f"/v1/innovation/recipes/{recipe_id}/feedback",
        json={"rating": 3},
        headers=_headers(anon_id),
    )
    assert neutral.status_code == 200
    assert neutral.json()["adjusted_rules"] == 0

    # 非法评分 → 422（Pydantic 1~5 校验）
    assert (
        client.post(
            f"/v1/innovation/recipes/{recipe_id}/feedback",
            json={"rating": 9},
            headers=_headers(anon_id),
        ).status_code
        == 422
    )


# ---------------------------------------------------------------------------
# 9) switch.innovation=false → 全部 7 端点 503 维护态
# ---------------------------------------------------------------------------
def test_switch_maintenance_503(client: TestClient, anon_id: str) -> None:
    """维护开关拦截全部创新端点（函数）。

    说明：
        改 remote_config.switch.innovation 行并 try/finally 还原；入口隐藏由
        前端处理，服务端统一 503 拒绝。

    参数：
        client：TestClient fixture。
        anon_id：唯一匿名身份 fixture。

    返回值：
        None。

    异常：
        断言失败即测试失败。
    """
    with SessionLocal() as db:
        cfg = db.execute(
            select(RemoteConfig).where(RemoteConfig.config_key == "switch.innovation")
        ).scalar_one()
        original = cfg.value
        cfg.value = False
        db.commit()
    try:
        headers = _headers(anon_id)
        # 1 precheck
        resp = client.post("/v1/innovation/precheck", json={"ingredients": ["鸡蛋"]}, headers=headers)
        assert resp.status_code == 503
        assert resp.json()["code"] == "INNOVATION_MAINTENANCE"
        # 2 generate
        assert client.post("/v1/innovation/generate", json={"ingredients": ["鸡蛋"]}, headers=headers).status_code == 503
        # 3 detail
        assert client.get("/v1/innovation/recipes/1", headers=headers).status_code == 503
        # 4 adopt
        assert client.post("/v1/innovation/recipes/1/adopt", headers=headers).status_code == 503
        # 5 index
        assert client.post("/v1/innovation/recipes/1/index", headers=headers).status_code == 503
        # 6 reuse
        assert client.post("/v1/innovation/recipes/1/reuse", headers=headers).status_code == 503
        # 7 feedback
        assert (
            client.post("/v1/innovation/recipes/1/feedback", json={"rating": 5}, headers=headers).status_code == 503
        )
    finally:
        with SessionLocal() as db:
            cfg = db.execute(
                select(RemoteConfig).where(RemoteConfig.config_key == "switch.innovation")
            ).scalar_one()
            cfg.value = original
            db.commit()


# ---------------------------------------------------------------------------
# O 补齐（深度验证差距项，R-8 冻结：仅新增测试断言，业务代码零改动）
# ---------------------------------------------------------------------------
# NFR-9.2 抽检违禁词表（任务口径：适量/少许/若干/一些；并含业务词表「随意」）
_VAGUE_AMOUNT_WORDS: tuple[str, ...] = ("适量", "少许", "若干", "一些", "随意")


def _assert_quantified_recipe(recipe: dict) -> None:
    """NFR-9.2 量化抽检断言函数（函数）。

    说明：
        对创新菜产出结构做 0 模糊用量抽检：食材行（amount 正数值 + unit 非空）、
        步骤（duration_sec>0）、以及 name/basis/nutrition/全文序列化后逐词断言
        不命中 _VAGUE_AMOUNT_WORDS（适量/少许/若干/一些/随意）。

    参数：
        recipe：创新菜响应 dict（/v1/innovation/generate 的 recipe 节点）。

    返回值：
        None。

    异常：
        断言失败即测试失败（发现模糊用量或结构缺量即失败）。
    """
    for item in recipe["ingredients"]:
        assert isinstance(item["amount"], (int, float)) and not isinstance(item["amount"], bool)
        assert item["amount"] > 0
        assert str(item.get("unit") or "").strip()
    for step in recipe["steps"]:
        assert isinstance(step["duration_sec"], (int, float)) and step["duration_sec"] > 0
    full_text = json.dumps(recipe, ensure_ascii=False)
    for word in _VAGUE_AMOUNT_WORDS:
        assert word not in full_text, f"产出含模糊用量词「{word}」：{full_text}"


def test_nfr92_quantified_spot_check_multiple_recipes(client: TestClient, anon_id: str) -> None:
    """NFR-9.2 量化抽检：多组食材生成产出 0 模糊用量（降级模板路径同样满足）（函数）。

    说明：
        conftest 将 LLM 指向不可达地址 → 生成走本地模板降级（generated_by=
        local_template）；降级输出与 LLM 输出共用同一 _is_quantified 代码强制
        校验（违例重试一次、再违例本地模板替换），因此 Mock 输出路径与正式路径
        同受红线约束。抽检 3 组食材，逐个过 _assert_quantified_recipe。

    参数：
        client：TestClient fixture。
        anon_id：唯一匿名身份 fixture。

    返回值：
        None。

    异常：
        断言失败即测试失败。
    """
    combos = [
        ("鸡蛋", "西红柿"),
        ("土豆", "青椒"),
        ("牛肉", "洋葱"),
    ]
    for ingredients in combos:
        resp = client.post(
            "/v1/innovation/generate",
            json={"ingredients": list(ingredients)},
            headers=_headers(anon_id),
        )
        assert resp.status_code == 201, resp.text
        recipe = resp.json()["recipe"]
        assert recipe["is_ai_innovated"] is True
        assert recipe["visibility"] == "private"
        assert recipe["status"] == "generated"
        _assert_quantified_recipe(recipe)
        assert recipe["basis"]["generated_by"] == "local_template"

def test_nfr94_default_recommend_excludes_ai_private(client: TestClient, anon_id: str) -> None:
    """NFR-9.4 私有分区红线：默认推荐链路绝不检索他人 ai_private 创新菜（函数）。

    流程：
        1. A 用户 generate→adopt→index 创新菜（食材名含进程级唯一 token，模板
           菜名携带 token，保证与种子菜谱/食材零碰撞）；
        2. DB 断言向量行 source='ai_private'、owner=A、recipe_id=None（分区结构）；
        3. B 用户默认检索（ability.retrieval.retrieve_candidates 默认
           include_private_owner=None，与推荐链路同口径）：结果标题不含 token
           （🔴 他人创新菜不出现——InnovationRecipe 不在 recipe 表，且 ai_private
           向量行不进默认向量查询，双重隔离）。

    参数：
        client：TestClient fixture。
        anon_id：A 用户唯一匿名身份 fixture（teardown 级联清理）。

    返回值：
        None。

    异常：
        默认检索出现 AI 私有创新菜时断言失败（分区红线破坏）。
    """
    from app.ability.retrieval import retrieve_candidates

    token = uuid.uuid4().hex[:8]
    ing_a = f"{token}幻影果"
    ing_b = f"{token}星尘糖"
    resp = client.post(
        "/v1/innovation/generate",
        json={"ingredients": [ing_a, ing_b]},
        headers=_headers(anon_id),
    )
    assert resp.status_code == 201, resp.text
    recipe = resp.json()["recipe"]
    recipe_id = int(recipe["id"])
    uid = int(_get_user_id(anon_id))

    # adopt → index（写 ai_private 向量行）
    assert client.post(
        f"/v1/innovation/recipes/{recipe_id}/adopt", headers=_headers(anon_id)
    ).status_code == 200
    index = client.post(
        f"/v1/innovation/recipes/{recipe_id}/index", headers=_headers(anon_id)
    )
    assert index.status_code == 200

    # 分区结构断言：ai_private 行 owner 归属正确、recipe_id 为空（verified 检索天然不含）
    with SessionLocal() as db:
        row = db.execute(
            select(RecipeEmbedding).where(RecipeEmbedding.innovation_recipe_id == recipe_id)
        ).scalar_one()
        assert row.source == "ai_private"
        assert int(row.owner_user_id) == uid
        assert row.recipe_id is None

    # B 用户默认推荐链路：绝不出现 A 的创新菜（标题与 token 双断言）
    other = _anon()
    try:
        with SessionLocal() as db:
            results = retrieve_candidates(db, [], query_text=ing_a, use_vector=True)
        hit_titles = [str(item.get("title") or "") for item in results]
        assert all(token not in title for title in hit_titles), (
            f"🔴 默认检索出现他人 ai_private 创新菜: {hit_titles}"
        )
        assert all(int(recipe_id) != int(item.get("recipe_id") or -1) for item in results)
    finally:
        _delete_user(other)

def test_removed_terminal_state_rejects_transitions(client: TestClient, anon_id: str) -> None:
    """removed 终态拒绝一切流转（adopt/index/reuse/detail/feedback → 404）（函数）。

    说明：
        状态机 generated→adopted→indexed 的合法流转与重复/跳步 422 已由
        test_adopt_index_state_machine 覆盖；本用例补 removed 终态口径：
        管理端下架（status='removed'）后，用户侧一切流转与读取统一 404
        （对外视为已删除，不泄露存在性）。

    参数：
        client：TestClient fixture。
        anon_id：唯一匿名身份 fixture。

    返回值：
        None。

    异常：
        断言失败即测试失败。
    """
    recipe_id = _generate_recipe(client, anon_id)
    with SessionLocal() as db:
        row = db.get(InnovationRecipe, recipe_id)
        row.status = "removed"
        db.commit()

    headers = _headers(anon_id)
    assert client.post(f"/v1/innovation/recipes/{recipe_id}/adopt", headers=headers).status_code == 404
    assert client.post(f"/v1/innovation/recipes/{recipe_id}/index", headers=headers).status_code == 404
    assert client.post(f"/v1/innovation/recipes/{recipe_id}/reuse", headers=headers).status_code == 404
    assert client.get(f"/v1/innovation/recipes/{recipe_id}", headers=headers).status_code == 404
    assert (
        client.post(
            f"/v1/innovation/recipes/{recipe_id}/feedback",
            json={"rating": 5},
            headers=headers,
        ).status_code
        == 404
    )
