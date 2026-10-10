"""后台管理端 /admin/v1 接口集成测试（模块 K）。

覆盖（spec Task 11 测试清单）：
    - 登录成功 / 密码错 401 / me；
    - readonly GET 200 + 写 403 且不写操作日志；
    - content_ops 改菜谱 200、改 admin-user 403；
    - 发布校验 422 定位违规行 → 修复 → 200；
    - 批量导入 json 2 成 1 败 + csv 冒烟；
    - rollback 按 log_id 恢复 before 快照；
    - 风控规则 toggle 写 before/after 日志（热更新随操作触发）；
    - trace-logs 四维过滤生效（时间窗/node/status/rule_hit）；
    - 工单流转 + 非法流转 422；
    - dashboard cost / risk 两个 200；
    - switches PUT 后 /v1/config/switches 反映（try/finally 还原）；
    - 订单 compensate failed → paid；
    - 创新规则 CRUD + inspect + remove；
    - 敏感词 remote_config 覆盖方案 PUT/GET/DELETE + sanitize 生效。

清理约定：
    全部自建行使用唯一后缀 SUFFIX，自建自清理；禁删种子（admin / 种子食材 /
    种子风控规则）。remote_config switch.* 与敏感词键在测试内 try/finally 还原。
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete, select, update

from app.core.db import SessionLocal
from app.core.security import hash_password
from app.main import app as main_app
from app.models import (
    AdminUser,
    AgentTrace,
    Feedback,
    FlavorPairingRule,
    Ingredient,
    InnovationRecipe,
    OperationLog,
    Order,
    Recipe,
    RemoteConfig,
    RiskRule,
    User,
)
from app.safety.sensitive_words import invalidate_custom_rules_cache, sanitize

# 唯一后缀：本次运行全部自建行以此命名，保证可重复执行
SUFFIX = uuid.uuid4().hex[:8]

# 自建账号定义：(username, role, password)
_ACCOUNTS = [
    (f"ops_{SUFFIX}", "content_ops", "Ops@123456"),
    (f"ro_{SUFFIX}", "readonly", "Ro@123456"),
    (f"super2_{SUFFIX}", "super_admin", "Super@123456"),
]

# 自建食材名（batch-import / innovation 复用）
_ING_A = f"测试食材甲{SUFFIX}"
_ING_B = f"测试食材乙{SUFFIX}"

# agent_trace 自建 request_id 前缀
_TRACE_PREFIX = f"t_admin_{SUFFIX}"

# 自建订单号
_ORDER_NO = f"KTEST{SUFFIX}0001"

# 测试规则编码前缀
_RULE_CODE = f"KTEST-{SUFFIX}"

# 敏感词自定义配置键（与 sensitive_words.py 模块常量一致）
_WORDS_KEY = "output_sensitive_words"

_HEADERS_JSON = {"Content-Type": "application/json"}


def _login(username: str, password: str) -> dict:
    """登录并返回 {headers, role}（函数）。

    参数：
        username：管理员用户名。
        password：明文密码。

    返回值：
        dict：{"headers": Authorization 头, "role": 角色}。

    异常：
        AssertionError：登录失败（测试环境前置条件）。
    """
    with TestClient(main_app) as c:
        resp = c.post("/admin/v1/auth/login", json={"username": username, "password": password})
    assert resp.status_code == 200, f"登录失败 {username}: {resp.text}"
    body = resp.json()
    return {
        "headers": {"Authorization": f"Bearer {body['access_token']}"},
        "role": body["role"],
    }


@pytest.fixture(scope="module")
def env() -> dict:
    """模块级测试环境 fixture（函数）。

    说明：
        创建三个角色账号与两个测试食材，登录获取 token；yield 后按 FK
        逆序清理全部自建行（operation_log → 创新菜 → 订单/反馈 → 菜谱 →
        规则 → 食材 → trace → 配置 → 账号）。

    返回值：
        dict：{super/ops/ro: 登录上下文, admin_id: {...}, ing_a_id, ing_b_id}。

    异常：
        数据库异常向上抛出（环境不可用即测试失败）。
    """
    with SessionLocal() as session:
        ids: dict[str, int] = {}
        for username, role, password in _ACCOUNTS:
            admin = AdminUser(
                username=username,
                password_hash=hash_password(password),
                role=role,
                status="active",
            )
            session.add(admin)
            session.flush()
            ids[role] = int(admin.id)
        ing_a = Ingredient(name=_ING_A, category="veg", allergen_codes=[])
        ing_b = Ingredient(name=_ING_B, category="seasoning", allergen_codes=[])
        session.add_all([ing_a, ing_b])
        session.flush()
        ing_ids = {"a": int(ing_a.id), "b": int(ing_b.id)}
        session.commit()

    tokens = {role: _login(username, password) for username, role, password in _ACCOUNTS}
    yield {"ids": ids, "ing": ing_ids, "tokens": tokens}

    # ---- 清理（FK 逆序）----
    with SessionLocal() as session:
        admin_ids = list(ids.values())
        # 自建 admin 写过的 remote_config 行（updated_by FK）先置空再删账号
        session.execute(
            update(RemoteConfig)
            .where(RemoteConfig.updated_by.in_(admin_ids))
            .values(updated_by=None)
        )
        session.execute(delete(OperationLog).where(OperationLog.admin_user_id.in_(admin_ids)))
        user_ids = [
            int(uid) for (uid,) in session.execute(
                select(User.id).where(User.anonymous_id.like(f"%{SUFFIX}%"))
            ).all()
        ]
        if user_ids:
            session.execute(delete(InnovationRecipe).where(InnovationRecipe.user_id.in_(user_ids)))
            session.execute(delete(Order).where(Order.user_id.in_(user_ids)))
            session.execute(delete(Feedback).where(Feedback.user_id.in_(user_ids)))
            session.execute(delete(User).where(User.id.in_(user_ids)))
        session.execute(delete(Recipe).where(Recipe.title.like(f"%{SUFFIX}%")))
        ing_id_list = [ing_ids["a"], ing_ids["b"]]
        session.execute(
            delete(FlavorPairingRule).where(
                FlavorPairingRule.ingredient_a_id.in_(ing_id_list)
                | FlavorPairingRule.ingredient_b_id.in_(ing_id_list)
            )
        )
        session.execute(delete(Ingredient).where(Ingredient.id.in_(ing_id_list)))
        session.execute(delete(AgentTrace).where(AgentTrace.request_id.like(f"{_TRACE_PREFIX}%")))
        session.execute(
            delete(RemoteConfig).where(
                RemoteConfig.config_key == _WORDS_KEY
            )
        )
        session.execute(delete(RiskRule).where(RiskRule.rule_code.like(f"{_RULE_CODE}%")))
        session.execute(delete(AdminUser).where(AdminUser.id.in_(admin_ids)))
        session.commit()
    invalidate_custom_rules_cache()


# ---------------------------------------------------------------------------
# 鉴权
# ---------------------------------------------------------------------------
def test_login_and_me(client: TestClient, env: dict) -> None:
    """登录成功 / 密码错 401 / me 身份回显（函数）。"""
    resp = client.post(
        "/admin/v1/auth/login",
        json={"username": f"ops_{SUFFIX}", "password": "Ops@123456"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["token_type"] == "bearer"
    assert body["role"] == "content_ops"
    token = body["access_token"]

    # 密码错误统一 401
    resp = client.post(
        "/admin/v1/auth/login", json={"username": f"ops_{SUFFIX}", "password": "wrong!"}
    )
    assert resp.status_code == 401
    # 用户不存在同样 401
    resp = client.post(
        "/admin/v1/auth/login", json={"username": f"nouser_{SUFFIX}", "password": "x"}
    )
    assert resp.status_code == 401

    resp = client.get(
        "/admin/v1/auth/me", headers={"Authorization": f"Bearer {token}"}
    )
    assert resp.status_code == 200
    assert resp.json() == {"username": f"ops_{SUFFIX}", "role": "content_ops"}


def test_readonly_permissions(client: TestClient, env: dict) -> None:
    """readonly：GET 200 + 写 403 且不产生操作日志（函数）。"""
    ro_headers = env["tokens"]["readonly"]["headers"]
    resp = client.get("/admin/v1/recipes", headers=ro_headers)
    assert resp.status_code == 200

    resp = client.post("/admin/v1/recipes", headers=ro_headers, json={"title": "x"})
    assert resp.status_code == 403
    resp = client.put(
        f"/admin/v1/admin-users/{env['ids']['super_admin']}", headers=ro_headers, json={}
    )
    assert resp.status_code == 403
    resp = client.put(
        "/admin/v1/config/switches", headers=ro_headers, json={"switches": {"qa": False}}
    )
    assert resp.status_code == 403

    # 403 不写操作日志
    with SessionLocal() as session:
        cnt = session.execute(
            select(OperationLog.id).where(
                OperationLog.admin_user_id == env["ids"]["readonly"]
            )
        ).scalars().all()
    assert cnt == [], "readonly 账号不应产生任何操作日志"


def test_content_ops_permissions(client: TestClient, env: dict) -> None:
    """content_ops：菜谱写 200/201、成员管理 403（函数）。"""
    ops_headers = env["tokens"]["content_ops"]["headers"]
    resp = client.post(
        "/admin/v1/recipes",
        headers=ops_headers,
        json={"title": f"权限菜谱{SUFFIX}", "ingredients": [], "steps": []},
    )
    assert resp.status_code == 201
    recipe_id = resp.json()["id"]

    resp = client.put(
        f"/admin/v1/recipes/{recipe_id}",
        headers=ops_headers,
        json={"title": f"权限菜谱改{SUFFIX}"},
    )
    assert resp.status_code == 200

    resp = client.post(
        "/admin/v1/admin-users",
        headers=ops_headers,
        json={"username": "hack", "password": "123456", "role": "readonly"},
    )
    assert resp.status_code == 403
    resp = client.put(
        f"/admin/v1/admin-users/{env['ids']['super_admin']}",
        headers=ops_headers,
        json={"status": "disabled"},
    )
    assert resp.status_code == 403


# ---------------------------------------------------------------------------
# 菜谱发布 / 导入 / 回滚
# ---------------------------------------------------------------------------
def test_publish_quantified_flow(client: TestClient, env: dict) -> None:
    """发布校验 422 定位行 → 修复 → 200 published（函数）。"""
    ops_headers = env["tokens"]["content_ops"]["headers"]
    ing_a, ing_b = env["ing"]["a"], env["ing"]["b"]
    resp = client.post(
        "/admin/v1/recipes",
        headers=ops_headers,
        json={
            "title": f"发布菜谱{SUFFIX}",
            "ingredients": [
                # amount_value 有值满足 DB CHECK，但备注含模糊词 → 发布校验 422 定位
                {"ingredient_id": ing_a, "amount_value": 1, "amount_note": "适量",
                 "amount_type": "main"},
                {"ingredient_id": ing_b, "amount_value": 2, "amount_unit": "克",
                 "amount_type": "seasoning"},
            ],
            "steps": [{"step_no": 1, "description": "下锅炒熟", "amount_hint": "少许盐"}],
        },
    )
    assert resp.status_code == 201
    recipe_id = resp.json()["id"]

    resp = client.post(f"/admin/v1/recipes/{recipe_id}/publish", headers=ops_headers)
    assert resp.status_code == 422
    body = resp.json()
    assert body["code"] == "RECIPE_NOT_QUANTIFIED"
    rows = [e["row"] for e in body["errors"]]
    assert 1 in rows, f"未定位到第 1 行违规: {body['errors']}"
    assert any(e["field"] == "amount_note" for e in body["errors"])
    assert any(e["field"] == "steps.amount_hint" for e in body["errors"])

    # 修复第 1 行与步骤提示后发布成功
    resp = client.put(
        f"/admin/v1/recipes/{recipe_id}",
        headers=ops_headers,
        json={
            "ingredients": [
                {"ingredient_id": ing_a, "amount_value": 150, "amount_unit": "克",
                 "amount_type": "main"},
                {"ingredient_id": ing_b, "amount_value": 2, "amount_unit": "克",
                 "amount_type": "seasoning"},
            ],
            "steps": [{"step_no": 1, "description": "下锅炒熟", "amount_hint": "盐 3 克"}],
        },
    )
    assert resp.status_code == 200
    resp = client.post(f"/admin/v1/recipes/{recipe_id}/publish", headers=ops_headers)
    assert resp.status_code == 200
    assert resp.json()["status"] == "published"

    # 下架回 draft
    resp = client.post(f"/admin/v1/recipes/{recipe_id}/unpublish", headers=ops_headers)
    assert resp.status_code == 200
    assert resp.json()["status"] == "draft"

    # 列表 quantified 判定
    resp = client.get(
        "/admin/v1/recipes", headers=ops_headers, params={"keyword": f"发布菜谱{SUFFIX}"}
    )
    assert resp.status_code == 200
    items = [r for r in resp.json()["items"] if r["id"] == recipe_id]
    assert items and items[0]["quantified"] is True


def test_batch_import(client: TestClient, env: dict) -> None:
    """批量导入：json 2 成 1 败 + csv 冒烟（函数）。"""
    ops_headers = env["tokens"]["content_ops"]["headers"]
    dishes = [
        {"name": f"导入菜一{SUFFIX}", "category": "家常菜",
         "ingredients": [{"name": _ING_A, "amount": 100, "unit": "克"}],
         "steps": [{"no": 1, "description": "洗净切块"}]},
        {"name": f"导入菜二{SUFFIX}",
         "ingredients": [{"name": _ING_B, "amount": 5, "unit": "克"}],
         "steps": [{"no": 1, "description": "调味"}]},
        {"name": f"导入菜三{SUFFIX}",
         "ingredients": [{"name": f"不存在的食材{SUFFIX}", "amount": 1, "unit": "克"}],
         "steps": []},
    ]
    resp = client.post(
        "/admin/v1/recipes/batch-import",
        headers=ops_headers,
        data={"format": "json"},
        files={"file": ("dishes.json", _json_bytes(dishes), "application/json")},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["imported"] == 2, body
    assert body["failed"] == 1
    assert body["errors"][0]["name"] == f"导入菜三{SUFFIX}"

    with SessionLocal() as session:
        titles = {
            t for (t,) in session.execute(
                select(Recipe.title).where(Recipe.title.like(f"%{SUFFIX}"))
            ).all()
        }
    assert f"导入菜一{SUFFIX}" in titles and f"导入菜二{SUFFIX}" in titles

    # csv 冒烟：扁平列按菜名分组
    csv_text = (
        "name,category,ingredient_name,amount,unit,step_no,step_desc\n"
        f"导入菜四{SUFFIX},家常菜,{_ING_A},50,克,1,热锅下油\n"
        f"导入菜四{SUFFIX},家常菜,{_ING_B},2,克,2,翻炒均匀出锅\n"
    )
    resp = client.post(
        "/admin/v1/recipes/batch-import",
        headers=ops_headers,
        data={"format": "csv"},
        files={"file": ("dishes.csv", csv_text.encode("utf-8"), "text/csv")},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["imported"] == 1


def _json_bytes(data: list) -> bytes:
    """序列化 JSON 为 utf-8 bytes（函数）。

    参数：
        data：任意可 JSON 结构。

    返回值：
        bytes：utf-8 编码字节串。

    异常：
        无。
    """
    import json
    return json.dumps(data, ensure_ascii=False).encode("utf-8")


def test_recipe_rollback(client: TestClient, env: dict) -> None:
    """rollback：按 operation_log before_snapshot 恢复菜谱内容（函数）。"""
    ops_headers = env["tokens"]["content_ops"]["headers"]
    resp = client.post(
        "/admin/v1/recipes",
        headers=ops_headers,
        json={"title": f"回滚菜谱v1{SUFFIX}", "ingredients": [], "steps": []},
    )
    recipe_id = resp.json()["id"]
    resp = client.put(
        f"/admin/v1/recipes/{recipe_id}",
        headers=ops_headers,
        json={"title": f"回滚菜谱v2{SUFFIX}"},
    )
    assert resp.status_code == 200

    # 找到 update 日志的 log_id
    with SessionLocal() as session:
        log = session.execute(
            select(OperationLog)
            .where(
                OperationLog.module == "recipe",
                OperationLog.action == "update",
                OperationLog.target_id == recipe_id,
            )
            .order_by(OperationLog.id.desc())
        ).scalars().first()
        assert log is not None and log.before_snapshot["title"] == f"回滚菜谱v1{SUFFIX}"
        log_id = int(log.id)

    resp = client.post(
        f"/admin/v1/recipes/{recipe_id}/rollback",
        headers=ops_headers,
        json={"log_id": log_id},
    )
    assert resp.status_code == 200, resp.text

    resp = client.get(f"/admin/v1/recipes/{recipe_id}", headers=ops_headers)
    assert resp.json()["title"] == f"回滚菜谱v1{SUFFIX}"


# ---------------------------------------------------------------------------
# 风控
# ---------------------------------------------------------------------------
def test_risk_rule_toggle_and_rollback(client: TestClient, env: dict) -> None:
    """规则创建 / toggle 写 before/after 日志 / rollback 恢复（函数）。"""
    super_headers = env["tokens"]["super_admin"]["headers"]
    payload = {
        "rule_code": _RULE_CODE,
        "category": "output_ban",
        "stage_scope": "output",
        "trigger_condition": {"keywords": [f"测试禁词{SUFFIX}"], "any": True},
        "block": False,
        "risk_level": "medium",
        "version": "v1",
        "enabled": True,
    }
    resp = client.post("/admin/v1/risk-rules", headers=super_headers, json=payload)
    assert resp.status_code == 201, resp.text
    rule_id = resp.json()["id"]

    resp = client.post(
        f"/admin/v1/risk-rules/{rule_id}/toggle",
        headers=super_headers,
        json={"enabled": False},
    )
    assert resp.status_code == 200
    assert resp.json()["enabled"] is False

    with SessionLocal() as session:
        log = session.execute(
            select(OperationLog)
            .where(
                OperationLog.module == "risk_rule",
                OperationLog.action == "toggle",
                OperationLog.target_id == rule_id,
            )
            .order_by(OperationLog.id.desc())
        ).scalars().first()
        assert log is not None
        assert log.before_snapshot["enabled"] is True
        assert log.after_snapshot["enabled"] is False
        log_id = int(log.id)

    # 恢复启用 → 再按日志回滚（该日志 before.enabled=True → 规则恢复启用态）
    resp = client.post(
        f"/admin/v1/risk-rules/{rule_id}/toggle",
        headers=super_headers,
        json={"enabled": True},
    )
    assert resp.status_code == 200
    resp = client.post(
        "/admin/v1/risk-rules/rollback", headers=super_headers, json={"log_id": log_id}
    )
    assert resp.status_code == 200, resp.text
    with SessionLocal() as session:
        rule = session.get(RiskRule, rule_id)
        assert rule.enabled is True  # before 快照 enabled=True 被恢复
        session.execute(delete(RiskRule).where(RiskRule.id == rule_id))
        session.commit()

    # content_ops 无权操作风控
    resp = client.get("/admin/v1/risk-rules", headers=env["tokens"]["content_ops"]["headers"])
    assert resp.status_code == 403


def test_sensitive_words_crud_and_sanitize(client: TestClient, env: dict) -> None:
    """敏感词 remote_config 覆盖：CRUD + sanitize 实际生效（函数）。"""
    super_headers = env["tokens"]["super_admin"]["headers"]
    try:
        resp = client.put(
            "/admin/v1/sensitive-words",
            headers=super_headers,
            json={"words": [{"word": f"管理敏感词{SUFFIX}", "replacement": "合规表述"}]},
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["active_source"] == "remote_config"

        resp = client.get("/admin/v1/sensitive-words", headers=super_headers)
        assert resp.status_code == 200
        assert resp.json()["words"][0]["word"] == f"管理敏感词{SUFFIX}"

        # 自定义词表优先：内置表不匹配的词被替换
        clean, violations = sanitize(f"包含管理敏感词{SUFFIX}的输出")
        assert f"管理敏感词{SUFFIX}" not in clean
        assert violations and violations[0]["category"] == "custom"

        # 单删 → 回退内置表
        resp = client.delete(
            "/admin/v1/sensitive-words",
            headers=super_headers,
            params={"word": f"管理敏感词{SUFFIX}"},
        )
        assert resp.status_code == 200
        assert resp.json()["active_source"] == "builtin"
    finally:
        with SessionLocal() as session:
            session.execute(delete(RemoteConfig).where(RemoteConfig.config_key == _WORDS_KEY))
            session.commit()
        invalidate_custom_rules_cache()


# ---------------------------------------------------------------------------
# 日志
# ---------------------------------------------------------------------------
def test_trace_logs_filters(client: TestClient, env: dict) -> None:
    """trace-logs 四维过滤（时间窗/node/status/rule_hit）生效（函数）。"""
    with SessionLocal() as session:
        session.add_all([
            AgentTrace(
                request_id=f"{_TRACE_PREFIX}a", user_id_hash=f"hash_{SUFFIX}a",
                node_name="supervisor", status="ok", duration_ms=10,
                prompt_tokens=100, completion_tokens=50, cost_cents=0.5,
            ),
            AgentTrace(
                request_id=f"{_TRACE_PREFIX}b", user_id_hash=f"hash_{SUFFIX}b",
                node_name="qa", status="failed", duration_ms=20,
                prompt_tokens=10, completion_tokens=5, cost_cents=0.1,
                rule_hit=f"RS-{SUFFIX}",
            ),
        ])
        session.commit()

    super_headers = env["tokens"]["super_admin"]["headers"]
    start = (datetime.now(UTC) - timedelta(hours=1)).isoformat()
    end = (datetime.now(UTC) + timedelta(hours=1)).isoformat()

    # 时间窗 + status 过滤：只命中 failed 行
    resp = client.get(
        "/admin/v1/trace-logs",
        headers=super_headers,
        params={"start": start, "end": end, "status": "failed"},
    )
    assert resp.status_code == 200
    items = [i for i in resp.json()["items"] if i["request_id"].startswith(_TRACE_PREFIX)]
    assert len(items) == 1 and items[0]["rule_hit"] == f"RS-{SUFFIX}"
    # 脱敏：只回 user_id_hash
    assert items[0]["user_id_hash"] == f"hash_{SUFFIX}b"

    # node_name 过滤
    resp = client.get(
        "/admin/v1/trace-logs",
        headers=super_headers,
        params={"start": start, "end": end, "node_name": "supervisor"},
    )
    items = [i for i in resp.json()["items"] if i["request_id"].startswith(_TRACE_PREFIX)]
    assert len(items) == 1 and items[0]["status"] == "ok"

    # rule_hit 过滤
    resp = client.get(
        "/admin/v1/trace-logs",
        headers=super_headers,
        params={"start": start, "end": end, "rule_hit": f"RS-{SUFFIX}"},
    )
    assert resp.json()["total"] >= 1

    # 操作日志列表（module 过滤）
    resp = client.get(
        "/admin/v1/operation-logs",
        headers=super_headers,
        params={"module": "recipe"},
    )
    assert resp.status_code == 200
    assert resp.json()["total"] >= 1


# ---------------------------------------------------------------------------
# 反馈 / 看板 / 开关 / 订单
# ---------------------------------------------------------------------------
def test_feedback_transition(client: TestClient, env: dict) -> None:
    """工单流转 pending→processing→resolved，非法流转 422（函数）。"""
    with SessionLocal() as session:
        user = User(anonymous_id=f"fb_user_{SUFFIX}")
        session.add(user)
        session.flush()
        fb = Feedback(user_id=int(user.id), type="other", content=f"工单内容{SUFFIX}")
        session.add(fb)
        session.commit()
        fb_id, user_id = int(fb.id), int(user.id)

    try:
        ops_headers = env["tokens"]["content_ops"]["headers"]
        resp = client.get(
            "/admin/v1/feedbacks", headers=ops_headers, params={"status": "pending"}
        )
        assert resp.status_code == 200
        assert any(i["id"] == fb_id for i in resp.json()["items"])

        resp = client.post(
            f"/admin/v1/feedbacks/{fb_id}/transition",
            headers=ops_headers, json={"action": "start"},
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "processing"

        resp = client.post(
            f"/admin/v1/feedbacks/{fb_id}/transition",
            headers=ops_headers, json={"action": "resolve"},
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "resolved"

        # resolved 再 resolve → 422
        resp = client.post(
            f"/admin/v1/feedbacks/{fb_id}/transition",
            headers=ops_headers, json={"action": "resolve"},
        )
        assert resp.status_code == 422
    finally:
        with SessionLocal() as session:
            session.execute(delete(Feedback).where(Feedback.id == fb_id))
            session.execute(delete(User).where(User.id == user_id))
            session.commit()


def test_dashboard(client: TestClient, env: dict) -> None:
    """dashboard cost / risk 两个 200 且结构正确（函数）。"""
    super_headers = env["tokens"]["super_admin"]["headers"]
    resp = client.get("/admin/v1/dashboard/cost", headers=super_headers, params={"days": 1})
    assert resp.status_code == 200
    assert isinstance(resp.json()["days"], list)

    resp = client.get("/admin/v1/dashboard/risk", headers=super_headers, params={"days": 1})
    assert resp.status_code == 200
    assert isinstance(resp.json()["days"], list)

    # content_ops 无权访问开关/风控看板外的超管端点
    resp = client.get(
        "/admin/v1/config/switches", headers=env["tokens"]["content_ops"]["headers"]
    )
    assert resp.status_code == 403


def test_switches_put_reflects_v1(client: TestClient, env: dict) -> None:
    """switches PUT 后 /v1/config/switches 反映（try/finally 还原）（函数）。"""
    with SessionLocal() as session:
        row = session.execute(
            select(RemoteConfig).where(RemoteConfig.config_key == "switch.qa")
        ).scalar_one()
        orig_value = bool(row.value)
        orig_version = int(row.version)

    super_headers = env["tokens"]["super_admin"]["headers"]
    try:
        resp = client.put(
            "/admin/v1/config/switches",
            headers=super_headers,
            json={"switches": {"qa": not orig_value}},
        )
        assert resp.status_code == 200, resp.text

        # /v1 口径（无需登录）应立即反映
        resp = client.get("/v1/config/switches")
        assert resp.status_code == 200
        assert resp.json()["qa"] == (not orig_value)

        # 后台 GET 带 version
        resp = client.get("/admin/v1/config/switches", headers=super_headers)
        assert resp.status_code == 200
        assert resp.json()["switches"]["qa"] == (not orig_value)
        version_after = resp.json()["version"]

        # rollback：用 PUT 日志恢复
        with SessionLocal() as session:
            log = session.execute(
                select(OperationLog)
                .where(OperationLog.module == "config", OperationLog.action == "update_switches")
                .order_by(OperationLog.id.desc())
            ).scalars().first()
            log_id = int(log.id)
        resp = client.post(
            "/admin/v1/config/switches/rollback",
            headers=super_headers, json={"log_id": log_id},
        )
        assert resp.status_code == 200, resp.text
        resp = client.get("/v1/config/switches")
        assert resp.json()["qa"] == orig_value
        assert version_after is not None
    finally:
        with SessionLocal() as session:
            row = session.execute(
                select(RemoteConfig).where(RemoteConfig.config_key == "switch.qa")
            ).scalar_one()
            row.value = orig_value
            row.version = orig_version
            session.commit()


def test_order_compensate(client: TestClient, env: dict) -> None:
    """订单 compensate：failed → paid，重复补发 422（函数）。"""
    with SessionLocal() as session:
        user = User(anonymous_id=f"order_user_{SUFFIX}")
        session.add(user)
        session.flush()
        order = Order(
            order_no=_ORDER_NO, user_id=int(user.id), product_type="membership",
            amount_cents=990, status="failed",
        )
        session.add(order)
        session.commit()
        order_id, user_id = int(order.id), int(user.id)

    try:
        super_headers = env["tokens"]["super_admin"]["headers"]
        resp = client.get(
            "/admin/v1/orders", headers=super_headers, params={"status": "failed"}
        )
        assert resp.status_code == 200
        assert any(o["order_no"] == _ORDER_NO for o in resp.json()["items"])

        resp = client.post(
            f"/admin/v1/orders/{_ORDER_NO}/compensate",
            headers=super_headers,
            json={"reason": f"支付回调丢失补发{SUFFIX}"},
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["status"] == "paid"

        with SessionLocal() as session:
            order = session.get(Order, order_id)
            assert order.status == "paid"

        # 非 failed/closed 状态不可补发
        resp = client.post(
            f"/admin/v1/orders/{_ORDER_NO}/compensate",
            headers=super_headers,
            json={"reason": "重复补发"},
        )
        assert resp.status_code == 422
    finally:
        with SessionLocal() as session:
            session.execute(delete(Order).where(Order.id == order_id))
            session.execute(delete(User).where(User.id == user_id))
            session.commit()


# ---------------------------------------------------------------------------
# 创新规则库 / 巡检
# ---------------------------------------------------------------------------
def test_innovation_rules_and_recipes(client: TestClient, env: dict) -> None:
    """创新规则 CRUD + inspect（未量化/空步骤）+ remove（函数）。"""
    ops_headers = env["tokens"]["content_ops"]["headers"]
    ing_a, ing_b = env["ing"]["a"], env["ing"]["b"]

    # 规则 CRUD
    resp = client.post(
        "/admin/v1/innovation/rules",
        headers=ops_headers,
        json={
            "ingredient_a_id": ing_a, "ingredient_b_id": ing_b,
            "relation": "recommend", "rationale": "口感互补",
            "signed_by_expert": False,
        },
    )
    assert resp.status_code == 201, resp.text
    rule_id = resp.json()["id"]

    resp = client.put(
        f"/admin/v1/innovation/rules/{rule_id}",
        headers=ops_headers,
        json={"weight": 1.5, "signed_by_expert": True},
    )
    assert resp.status_code == 200
    assert resp.json()["weight"] == 1.5
    assert resp.json()["signed_by_expert"] is True

    resp = client.get("/admin/v1/innovation/rules", headers=ops_headers)
    assert resp.status_code == 200
    # 种子规则行可能超过单页容量：翻页查找自建规则
    found = False
    page = 1
    while not found and page <= 50:
        page_resp = client.get(
            "/admin/v1/innovation/rules",
            headers=ops_headers, params={"page": page, "size": 100},
        )
        ids = [r["id"] for r in page_resp.json()["items"]]
        found = rule_id in ids
        if len(ids) < 100:
            break
        page += 1
    assert found, f"规则 {rule_id} 未在列表中找到"

    resp = client.delete(f"/admin/v1/innovation/rules/{rule_id}", headers=ops_headers)
    assert resp.status_code == 200

    # 创新菜：建行（ingredients 未量化 + 空 steps）→ inspect 报问题 → 修复 → remove
    with SessionLocal() as session:
        user = User(anonymous_id=f"innov_user_{SUFFIX}")
        session.add(user)
        session.flush()
        recipe = InnovationRecipe(
            user_id=int(user.id),
            name=f"创新菜{SUFFIX}",
            ingredients=[{"ingredient_id": ing_a, "name": _ING_A, "amount": None, "unit": ""}],
            steps=[],
            nutrition={"kcal": 100},
            basis={"pairing": []},
        )
        session.add(recipe)
        session.commit()
        recipe_id, user_id = int(recipe.id), int(user.id)

    try:
        resp = client.get(
            "/admin/v1/innovation/recipes",
            headers=ops_headers, params={"status": "generated"},
        )
        assert resp.status_code == 200
        # 他人自建/种子行可能占满首页：翻页查找自建创新菜
        found = False
        page = 1
        while not found and page <= 50:
            page_resp = client.get(
                "/admin/v1/innovation/recipes",
                headers=ops_headers,
                params={"status": "generated", "page": page, "size": 100},
            )
            ids = [r["id"] for r in page_resp.json()["items"]]
            found = recipe_id in ids
            if len(ids) < 100:
                break
            page += 1
        assert found, f"创新菜 {recipe_id} 未在列表中找到"

        resp = client.post(
            f"/admin/v1/innovation/recipes/{recipe_id}/inspect", headers=ops_headers
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["ok"] is False
        fields = {i["field"] for i in body["issues"]}
        assert any(f.startswith("ingredients[1]") for f in fields)
        assert "steps" in fields

        # 修复后巡检通过
        with SessionLocal() as session:
            recipe = session.get(InnovationRecipe, recipe_id)
            recipe.ingredients = [
                {"ingredient_id": ing_a, "name": _ING_A, "amount": 100, "unit": "克"}
            ]
            recipe.steps = [{"no": 1, "description": "大火快炒"}]
            session.commit()

        resp = client.post(
            f"/admin/v1/innovation/recipes/{recipe_id}/inspect", headers=ops_headers
        )
        assert resp.json()["ok"] is True
        assert resp.json()["issues"] == []

        # 下架（巡检下架不升格：直接 removed）
        resp = client.post(
            f"/admin/v1/innovation/recipes/{recipe_id}/remove", headers=ops_headers
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "removed"
        with SessionLocal() as session:
            assert session.get(InnovationRecipe, recipe_id).status == "removed"
    finally:
        with SessionLocal() as session:
            session.execute(delete(InnovationRecipe).where(InnovationRecipe.id == recipe_id))
            session.execute(delete(User).where(User.id == user_id))
            session.commit()


# ---------------------------------------------------------------------------
# K 补齐（深度验证差距项）：风控规则启停热更新生效 + 菜谱回滚版本与审计快照
# ---------------------------------------------------------------------------
def test_risk_rule_toggle_hot_reload_effect(client: TestClient, env: dict) -> None:
    """风控规则启停热更新：停用后命中场景立即放行、恢复后再次拦截（函数）。

    说明：
        引擎为「scan 时指纹校验（COUNT+MAX(updated_at)）」拉模式热更新（等价
        30s 轮询语义）+ 管理端写操作后主动 _load_rules 强制重载（变更即时生效，
        无需等待轮询周期）。本用例走 admin toggle 端点（同时复核 toggle 的
        before/after 审计快照），以 RiskEngine.scan 直接断言拦截场景的生效链：
        - 启用：scan 命中且 block=true（一票否决）；
        - 停用：scan 立即不再命中（热更新生效，不等 30s 轮询）；
        - 恢复启用：scan 再次命中。
        finally 中删除自建规则行并强制重载引擎缓存，避免残留影响其他用例。

    参数：
        client：TestClient fixture。
        env：模块级环境 fixture（super_admin token）。

    返回值：
        None。

    异常：
        断言失败即测试失败；清理/重载失败向上抛出（不影响其他用例判定）。
    """
    from app.safety.engine import get_risk_engine

    keyword = f"热更新探测词{SUFFIX}"
    scan_text = f"普通文本包含{keyword}的场景"
    engine = get_risk_engine()
    super_headers = env["tokens"]["super_admin"]["headers"]
    rule_id: int | None = None
    try:
        resp = client.post(
            "/admin/v1/risk-rules",
            headers=super_headers,
            json={
                "rule_code": f"{_RULE_CODE}-HOT",
                "category": "food_safety_high_risk",
                "stage_scope": "input",
                "trigger_condition": {"keywords": [keyword], "any": True},
                "block": True,
                "risk_level": "high",
                "version": "v1",
                "enabled": True,
            },
        )
        assert resp.status_code == 201, resp.text
        rule_id = int(resp.json()["id"])

        # 启用态：命中场景被拦截（一票否决）
        verdict = engine.scan("input", scan_text)
        assert verdict.hit is True
        assert verdict.block is True

        # 停用 → 命中场景立即放行（热更新，不等 30s 轮询周期）
        resp = client.post(
            f"/admin/v1/risk-rules/{rule_id}/toggle",
            headers=super_headers,
            json={"enabled": False},
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["enabled"] is False
        verdict = engine.scan("input", scan_text)
        assert verdict.hit is False, "停用规则后 scan 仍命中 → 热更新失效"

        # 恢复启用 → 再次拦截
        resp = client.post(
            f"/admin/v1/risk-rules/{rule_id}/toggle",
            headers=super_headers,
            json={"enabled": True},
        )
        assert resp.status_code == 200
        assert resp.json()["enabled"] is True
        verdict = engine.scan("input", scan_text)
        assert verdict.hit is True and verdict.block is True

        # toggle 的 before/after 审计快照（最新一条为恢复启用：False → True）
        with SessionLocal() as session:
            log = session.execute(
                select(OperationLog)
                .where(
                    OperationLog.module == "risk_rule",
                    OperationLog.action == "toggle",
                    OperationLog.target_id == rule_id,
                )
                .order_by(OperationLog.id.desc())
            ).scalars().first()
            assert log is not None
            assert log.before_snapshot["enabled"] is False
            assert log.after_snapshot["enabled"] is True
    finally:
        with SessionLocal() as session:
            if rule_id is not None:
                row = session.get(RiskRule, rule_id)
                if row is not None:
                    session.delete(row)
            session.commit()
        # 强制重载引擎缓存，避免本用例规则残留影响其他测试（等价轮询周期后的收敛态）
        for stage in ("input", "output"):
            try:
                engine._load_rules(stage)
            except Exception:  # noqa: BLE001 —— 重载失败交由 scan 的 UNKNOWN 兜底
                pass

def test_recipe_rollback_version_and_after_snapshot(client: TestClient, env: dict) -> None:
    """菜谱回滚：内容与版本号正确 + update 日志 after_snapshot 断言（函数）。

    说明：
        版本口径核对结论：recipe.version 由默认 1 起始，update/publish/rollback
        均不自动递增（「再发布产生新版本号」业务未实现——差距与最小修复方案见
        交付报告，本阶段业务代码零改动）。本用例锁定当下正确口径：
        - update 操作日志携带 before/after 双快照（before.title=v1、after.title=v2）；
        - rollback 后详情内容恢复为 v1 快照、version 保持不变（快照恢复不触碰版本列）；
        - 重新发布成功（空卡通过量化闸门）且 version 维持稳定（现状基线）。

    参数：
        client：TestClient fixture。
        env：模块级环境 fixture（content_ops token）。

    返回值：
        None。

    异常：
        断言失败即测试失败；自建菜谱在 finally 中自清理。
    """
    ops_headers = env["tokens"]["content_ops"]["headers"]
    resp = client.post(
        "/admin/v1/recipes",
        headers=ops_headers,
        json={"title": f"版本菜谱v1{SUFFIX}", "ingredients": [], "steps": []},
    )
    assert resp.status_code == 201, resp.text
    recipe_id = int(resp.json()["id"])
    try:
        resp = client.put(
            f"/admin/v1/recipes/{recipe_id}",
            headers=ops_headers,
            json={"title": f"版本菜谱v2{SUFFIX}"},
        )
        assert resp.status_code == 200

        # update 操作日志：before/after 双快照齐备（补 K 差距：after_snapshot 断言）
        with SessionLocal() as session:
            log = session.execute(
                select(OperationLog)
                .where(
                    OperationLog.module == "recipe",
                    OperationLog.action == "update",
                    OperationLog.target_id == recipe_id,
                )
                .order_by(OperationLog.id.desc())
            ).scalars().first()
            assert log is not None
            assert log.before_snapshot["title"] == f"版本菜谱v1{SUFFIX}"
            assert log.after_snapshot is not None
            assert log.after_snapshot["title"] == f"版本菜谱v2{SUFFIX}"
            log_id = int(log.id)

        with SessionLocal() as session:
            version_before = int(session.get(Recipe, recipe_id).version)

        # 回滚 → 内容恢复 v1 快照、version 保持不变（快照恢复不触碰版本列）
        resp = client.post(
            f"/admin/v1/recipes/{recipe_id}/rollback",
            headers=ops_headers,
            json={"log_id": log_id},
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["rolled_back_to"] == log_id

        resp = client.get(f"/admin/v1/recipes/{recipe_id}", headers=ops_headers)
        assert resp.status_code == 200
        assert resp.json()["title"] == f"版本菜谱v1{SUFFIX}"
        assert int(resp.json()["version"]) == version_before

        # 再发布：内容为空卡可通过量化闸门 → published；version 现状不递增（差距记录）
        resp = client.post(f"/admin/v1/recipes/{recipe_id}/publish", headers=ops_headers)
        assert resp.status_code == 200, resp.text
        assert resp.json()["status"] == "published"
        resp = client.get(f"/admin/v1/recipes/{recipe_id}", headers=ops_headers)
        assert int(resp.json()["version"]) == version_before
    finally:
        with SessionLocal() as session:
            recipe = session.get(Recipe, recipe_id)
            if recipe is not None:
                session.delete(recipe)
                session.commit()
