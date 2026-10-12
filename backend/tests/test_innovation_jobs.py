"""AI 创新异步生成任务集成测试（M-01 异步化，Task 2）。

覆盖：
    - POST /v1/innovation/jobs：202 立即受理（不阻塞等待 LLM）——job_id 为
      injob_ 前缀、status=pending、request_id 回显；
    - GET /v1/innovation/jobs/{id}：提交后立即查询为 pending/running（受控函数
      sleep 0.2s 拉长运行窗口），轮询至终态 succeeded，recipe 恒带
      is_ai_innovated=true 与 disclaimer（🔴 强制标识红线）；
    - blocked：受控函数返回拦截 → 终态 blocked 且 issues 非空（前端拦截卡语义）；
    - failed：受控函数抛异常 → 终态 failed 且 error 非空（worker 防御性兜底，
      run_innovation_generate 理论上不抛，保证 job 必达终态）；
    - 未知 job_id → 404；
    - A 用户创建、B 用户（不同 X-Anonymous-Id）查询 → 404（🔴 跨用户隔离，
      不泄露存在性）；
    - switch.innovation=false → 两端点均 503 维护态。

测试约定：
    不真调 LLM：monkeypatch 路由模块命名空间的 run_innovation_generate（from
    ... import 后的名字，worker 在线程池中运行时按模块全局查找命中 patch）为
    受控函数，不触网不落库；测试用户走 get_current_user 惯例自动 upsert，
    teardown 级联清理；remote_config 开关修改 try/finally 还原。
"""

from __future__ import annotations

import time
import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.api.v1 import innovation as innovation_api
from app.api.v1.router import api_router
from app.core.db import SessionLocal
from app.models import RemoteConfig, User
from app.schemas.innovation import DISCLAIMER_TEXT

# 并行开发约定：router.py 已统一注册；未注册时此处补注册（进程级标记守卫，
# 避免 OpenAPI Duplicate Operation ID 告警；注册后本守卫自动跳过）。
if not getattr(api_router, "_t7_innovation_registered", False):
    api_router.include_router(innovation_api.router)
    api_router._t7_innovation_registered = True

# 轮询终态超时（秒）：受控函数最长 sleep 0.2s，5s 超时已留足余量
_JOB_POLL_TIMEOUT = 5.0

# 终态集合（pending/running 之外即冻结，轮询可安全停止）
_TERMINAL_STATUSES = ("succeeded", "failed", "blocked")


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
        str：anon_m01_ 前缀唯一 ID。

    异常：
        无。
    """
    return f"anon_m01_{uuid.uuid4().hex[:10]}"


def _delete_user(anon: str) -> None:
    """按匿名 ID 删除用户行（级联清理自建数据）（函数）。

    说明：
        job store 记录仅持 user_db_id 整数（无外键），用户删除不影响残留记录。

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
            db.delete(user)
            db.commit()


def _fake_recipe() -> dict:
    """构造受控创新菜响应 dict（函数，结构与子图 result / InnovationRecipeOut 兼容）。

    返回值：
        dict：完整创新菜结构（is_ai_innovated=true、disclaimer 恒带）。

    异常：
        无。
    """
    return {
        "id": int(uuid.uuid4().hex[:8], 16),
        "name": "异步测试创新菜",
        "ingredients": [{"name": "鸡蛋", "amount": 2, "unit": "个"}],
        "steps": [{"no": 1, "description": "打散鸡蛋", "duration_sec": 30, "tips": ""}],
        "basis": {"pairings": [], "properties": [], "techniques_whitelist": [], "generated_by": "template"},
        "nutrition": {"total": {}, "per_serving": {}, "excluded_items": [], "estimate_note": "测试估算"},
        "status": "generated",
        "is_ai_innovated": True,
        "visibility": "private",
        "disclaimer": DISCLAIMER_TEXT,
        "rating": None,
        "created_at": None,
    }


def _submit_job(client: TestClient, anon: str, request_id: str | None = None) -> dict:
    """提交异步生成任务并断言 202 受理（函数）。

    参数：
        client：TestClient fixture。
        anon：匿名身份。
        request_id：幂等键（可缺省，缺省时自动生成）。

    返回值：
        dict：202 响应体 {job_id, status, request_id}。

    异常：
        断言失败即测试失败。
    """
    payload: dict = {"ingredients": ["鸡蛋", "西红柿"]}
    if request_id is not None:
        payload["request_id"] = request_id
    resp = client.post("/v1/innovation/jobs", json=payload, headers=_headers(anon))
    assert resp.status_code == 202, resp.text
    body = resp.json()
    assert body["job_id"].startswith("injob_"), "job_id 应为 injob_ 前缀"
    assert body["status"] == "pending"
    return body


def _poll_terminal(client: TestClient, job_id: str, anon: str) -> dict:
    """轮询任务至终态并返回最后响应体（函数）。

    参数：
        client：TestClient fixture。
        job_id：异步任务 ID。
        anon：匿名身份。

    返回值：
        dict：终态响应体（status ∈ succeeded/failed/blocked）。

    异常：
        超时未达终态时断言失败。
    """
    deadline = time.time() + _JOB_POLL_TIMEOUT
    while time.time() < deadline:
        resp = client.get(f"/v1/innovation/jobs/{job_id}", headers=_headers(anon))
        assert resp.status_code == 200, resp.text
        body = resp.json()
        if body["status"] in _TERMINAL_STATUSES:
            return body
        time.sleep(0.05)
    raise AssertionError(f"job {job_id} 未在 {_JOB_POLL_TIMEOUT}s 内到达终态")


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
# 1) 提交即返回 202 + 立即查询 pending/running + 轮询终态 succeeded（标识红线）
# ---------------------------------------------------------------------------
def test_submit_then_poll_succeeded(client: TestClient, anon_id: str, monkeypatch: pytest.MonkeyPatch) -> None:
    """提交 202 → 立即查询为 pending/running → 轮询终态 succeeded（函数）。

    说明：
        受控函数 sleep 0.2s 模拟 LLM 上游慢，验证「提交即返回不阻塞、结果经
        轮询取得」的异步链路；succeeded 的 recipe 恒带 is_ai_innovated=true 与
        disclaimer（🔴 强制标识红线），request_id 全链路回显一致。

    参数：
        client：TestClient fixture。
        anon_id：唯一匿名身份 fixture。
        monkeypatch：patch 路由模块命名空间的 run_innovation_generate。

    返回值：
        None。

    异常：
        断言失败即测试失败。
    """
    request_id = f"t_{uuid.uuid4().hex[:16]}"

    def _fake_generate(user_db_id: int, ingredients: list[str], request_id: str | None = None,
                       user_id_hash: str | None = None) -> dict:
        """受控生成函数（模拟 LLM 上游慢：sleep 0.2s 后返回成功产物）。"""
        time.sleep(0.2)
        return {
            "ok": True,
            "blocked": False,
            "issues": [],
            "risk_log_written": False,
            "result": _fake_recipe(),
            "request_id": request_id,
            "trace_id": "tr_m01test",
        }

    monkeypatch.setattr(innovation_api, "run_innovation_generate", _fake_generate)

    # 提交：202 立即返回（不阻塞等待 LLM），幂等键回显
    created = _submit_job(client, anon_id, request_id)
    assert created["request_id"] == request_id
    job_id = created["job_id"]

    # 立即查询：受控函数尚未返回 → pending 或 running（绝不出现终态）
    immediate = client.get(f"/v1/innovation/jobs/{job_id}", headers=_headers(anon_id))
    assert immediate.status_code == 200, immediate.text
    assert immediate.json()["status"] in ("pending", "running")

    # 轮询至终态：succeeded + recipe 标识红线
    terminal = _poll_terminal(client, job_id, anon_id)
    assert terminal["status"] == "succeeded"
    assert terminal["error"] is None
    recipe = terminal["recipe"]
    assert recipe is not None
    assert recipe["is_ai_innovated"] is True
    assert recipe["disclaimer"] == DISCLAIMER_TEXT
    assert recipe["name"] == "异步测试创新菜"
    assert terminal["request_id"] == request_id
    assert terminal["issues"] == []


# ---------------------------------------------------------------------------
# 2) 受控函数返回拦截 → 终态 blocked 且带 issues
# ---------------------------------------------------------------------------
def test_job_blocked_terminal_state(client: TestClient, anon_id: str, monkeypatch: pytest.MonkeyPatch) -> None:
    """job 内风控拦截 → 终态 blocked + issues（与同步接口拦截语义一致）（函数）。

    参数：
        client：TestClient fixture。
        anon_id：唯一匿名身份 fixture。
        monkeypatch：patch 路由模块命名空间的 run_innovation_generate。

    返回值：
        None。

    异常：
        断言失败即测试失败。
    """
    issues = [{"type": "high_risk", "message": "异步拦截测试：含高危食材"}]

    def _fake_generate(user_db_id: int, ingredients: list[str], request_id: str | None = None,
                       user_id_hash: str | None = None) -> dict:
        """受控生成函数（返回风控拦截响应）。"""
        return {
            "ok": False,
            "blocked": True,
            "issues": issues,
            "risk_log_written": True,
            "result": None,
            "request_id": request_id,
            "trace_id": "tr_m01block",
        }

    monkeypatch.setattr(innovation_api, "run_innovation_generate", _fake_generate)

    created = _submit_job(client, anon_id)
    terminal = _poll_terminal(client, created["job_id"], anon_id)
    assert terminal["status"] == "blocked"
    assert terminal["recipe"] is None
    assert terminal["error"] is None
    assert terminal["issues"], "blocked 终态必须携带拦截原因"
    assert terminal["issues"][0]["type"] == "high_risk"
    assert terminal["issues"][0]["message"] == "异步拦截测试：含高危食材"


# ---------------------------------------------------------------------------
# 3) 受控函数抛异常 → 终态 failed 且 error 非空（worker 防御性兜底）
# ---------------------------------------------------------------------------
def test_job_failed_on_exception(client: TestClient, anon_id: str, monkeypatch: pytest.MonkeyPatch) -> None:
    """worker 异常兜底 → 终态 failed + error 文案（job 必达终态，轮询不悬挂）（函数）。

    说明：
        run_innovation_generate 理论上不抛（内部全捕获 + 25s 硬超时 + template
        降级）；本用例防御性验证 worker 的兜底分支：异常不外溢、error 不透出
        内部异常细节。

    参数：
        client：TestClient fixture。
        anon_id：唯一匿名身份 fixture。
        monkeypatch：patch 路由模块命名空间的 run_innovation_generate。

    返回值：
        None。

    异常：
        断言失败即测试失败。
    """
    def _fake_generate_crash(user_db_id: int, ingredients: list[str], request_id: str | None = None,
                             user_id_hash: str | None = None) -> dict:
        """受控生成函数（直接抛异常，触发 worker 防御性兜底）。"""
        raise RuntimeError("m01 模拟上游崩溃")

    monkeypatch.setattr(innovation_api, "run_innovation_generate", _fake_generate_crash)

    created = _submit_job(client, anon_id)
    terminal = _poll_terminal(client, created["job_id"], anon_id)
    assert terminal["status"] == "failed"
    assert terminal["recipe"] is None
    assert terminal["error"], "failed 终态必须携带面向用户文案"
    assert "RuntimeError" not in terminal["error"], "error 不得透出内部异常细节"
    assert terminal["issues"] == []


# ---------------------------------------------------------------------------
# 4) 未知 job_id → 404
# ---------------------------------------------------------------------------
def test_job_not_found_404(client: TestClient, anon_id: str) -> None:
    """查询不存在的 job_id → 404（函数）。

    参数：
        client：TestClient fixture。
        anon_id：唯一匿名身份 fixture。

    返回值：
        None。

    异常：
        断言失败即测试失败。
    """
    resp = client.get(f"/v1/innovation/jobs/injob_{uuid.uuid4().hex[:12]}", headers=_headers(anon_id))
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# 5) 跨用户隔离：A 创建、B 查询 → 404（不泄露存在性）
# ---------------------------------------------------------------------------
def test_job_cross_user_isolation(client: TestClient, anon_id: str, monkeypatch: pytest.MonkeyPatch) -> None:
    """A 用户创建的 job，B 用户查询 → 404；A 本人查询 → 200（函数）。

    说明：
        🔴 跨用户隔离红线：不存在与他人的 job 统一 404，不泄露存在性（与
        recipes 详情/reuse 同口径）。

    参数：
        client：TestClient fixture。
        anon_id：A 用户唯一匿名身份 fixture。
        monkeypatch：patch 路由模块命名空间的 run_innovation_generate。

    返回值：
        None。

    异常：
        断言失败即测试失败。
    """
    def _fake_generate(user_db_id: int, ingredients: list[str], request_id: str | None = None,
                       user_id_hash: str | None = None) -> dict:
        """受控生成函数（立即返回成功产物，不触网不落库）。"""
        return {
            "ok": True,
            "blocked": False,
            "issues": [],
            "risk_log_written": False,
            "result": _fake_recipe(),
            "request_id": request_id,
            "trace_id": "tr_m01iso",
        }

    monkeypatch.setattr(innovation_api, "run_innovation_generate", _fake_generate)

    created = _submit_job(client, anon_id)
    job_id = created["job_id"]

    # A 本人查询 → 200（状态任意，job 终态与否不影响隔离断言）
    assert client.get(f"/v1/innovation/jobs/{job_id}", headers=_headers(anon_id)).status_code == 200

    # B 用户（不同 X-Anonymous-Id）查询 → 404
    other = _anon()
    try:
        resp = client.get(f"/v1/innovation/jobs/{job_id}", headers=_headers(other))
        assert resp.status_code == 404
    finally:
        _delete_user(other)


# ---------------------------------------------------------------------------
# 6) 维护态：switch.innovation=false → 两端点均 503
# ---------------------------------------------------------------------------
def test_job_maintenance_503(client: TestClient, anon_id: str) -> None:
    """维护开关拦截异步 job 两端点（与既有 7 端点同语义）（函数）。

    说明：
        改 remote_config.switch.innovation 行并 try/finally 还原；503 在身份
        解析之前生效（GET 用任意 job_id 即可断言）。

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
        # POST jobs → 503 维护态
        resp = client.post("/v1/innovation/jobs", json={"ingredients": ["鸡蛋"]}, headers=headers)
        assert resp.status_code == 503
        assert resp.json()["code"] == "INNOVATION_MAINTENANCE"
        # GET jobs/{id} → 503 维护态
        resp = client.get(f"/v1/innovation/jobs/injob_{uuid.uuid4().hex[:12]}", headers=headers)
        assert resp.status_code == 503
        assert resp.json()["code"] == "INNOVATION_MAINTENANCE"
    finally:
        with SessionLocal() as db:
            cfg = db.execute(
                select(RemoteConfig).where(RemoteConfig.config_key == "switch.innovation")
            ).scalar_one()
            cfg.value = original
            db.commit()
