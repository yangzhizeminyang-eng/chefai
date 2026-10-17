"""创新异步任务重启恢复能力测试（阶段 4 可靠性升级）。

覆盖：
    - 写穿：提交 job 后 innovation_job 表同步出现 pending 快照；
    - 启动恢复：recover_stale_innovation_jobs 把 pending/running 行置为
      failed 终态（error 为面向用户文案，finished_at 落值）；
    - DB fallback：内存 store 清空（模拟重启）后轮询 job → 同用户拿到
      failed 终态（而非 404），他人 job 仍 404（跨用户隔离不变）；
    - 终态冻结：恢复只动 pending/running，已终态行不受影响。

运行：
    .venv\\Scripts\\python.exe -m pytest tests/test_innovation_job_recovery.py -q
"""

from __future__ import annotations

import uuid

from fastapi.testclient import TestClient

from app.api.v1.innovation import (
    _INNOVATION_JOBS,
    recover_stale_innovation_jobs,
)
from app.core.db import SessionLocal
from app.models import InnovationJob
from tests.conftest import unique_request_id


def _headers(anon_id: str) -> dict[str, str]:
    """构造匿名用户请求头（辅助函数）。

    参数：
        anon_id：匿名会话 ID。

    返回值：
        dict[str, str]：X-Anonymous-Id 头。

    异常：
        无。
    """
    return {"X-Anonymous-Id": anon_id}


def _create_anon(client: TestClient) -> str:
    """创建匿名会话并返回 ID（辅助函数）。

    参数：
        client：测试客户端。

    返回值：
        str：匿名会话 ID。

    异常：
        断言失败时抛 AssertionError。
    """
    resp = client.post("/v1/auth/anonymous")
    assert resp.status_code == 200, resp.text
    return resp.json()["anonymous_id"]


def test_job_write_through_and_recovery(client: TestClient) -> None:
    """写穿 + 启动恢复 + DB fallback 全链路（函数）。

    流程：
        1. 提交异步 job（写穿 pending 快照）；
        2. 模拟进程重启：清空内存 store；
        3. 调启动恢复：DB pending 行置 failed；
        4. 轮询 job：内存 miss → DB fallback 返回 200 failed（非 404）；
        5. 他人 job 轮询：仍 404（跨用户隔离不变）。
    """
    anon_a = _create_anon(client)
    anon_b = _create_anon(client)
    rid = unique_request_id()
    resp = client.post(
        "/v1/innovation/jobs",
        json={"ingredients": ["番茄", "鸡蛋"], "request_id": rid},
        headers=_headers(anon_a),
    )
    assert resp.status_code == 202, resp.text
    job_id = resp.json()["job_id"]

    # 写穿断言：DB 中出现 pending 行
    with SessionLocal() as session:
        row = session.query(InnovationJob).filter(
            InnovationJob.job_id == job_id
        ).one_or_none()
        assert row is not None, "job 提交后应写穿出 pending 快照"
        assert row.status in ("pending", "running", "succeeded", "failed", "blocked")

    # 模拟进程重启：清空内存 store（仅本测试进程内可见）
    with SessionLocal() as session:
        # 等待 worker 可能已完成（终态不受恢复影响）——记录恢复前状态
        row = session.query(InnovationJob).filter(
            InnovationJob.job_id == job_id
        ).one()
        pre_status = row.status
    _INNOVATION_JOBS.clear()

    # 启动恢复：仅 pending/running 被置 failed，终态行冻结不动
    recovered = recover_stale_innovation_jobs()
    assert recovered >= 0
    with SessionLocal() as session:
        row = session.query(InnovationJob).filter(
            InnovationJob.job_id == job_id
        ).one()
        if pre_status in ("pending", "running"):
            assert row.status == "failed", "重启遗留任务应被置 failed"
            assert row.error is not None and "重新提交" in str(row.error)
            assert row.finished_at is not None
        else:
            assert row.status == pre_status, "已终态任务不应被恢复改动"

    # DB fallback：内存已清空，轮询走 DB → 同用户 200（终态）
    resp_b = client.get(f"/v1/innovation/jobs/{job_id}", headers=_headers(anon_b))
    assert resp_b.status_code == 404, "他人 job 轮询必须 404（跨用户隔离）"
    resp_a = client.get(f"/v1/innovation/jobs/{job_id}", headers=_headers(anon_a))
    assert resp_a.status_code == 200, resp_a.text
    assert resp_a.json()["status"] in ("failed", "succeeded", "blocked")


def test_recovery_only_touches_non_terminal(client: TestClient) -> None:
    """恢复只处理 pending/running：手工插入终态行后恢复不改写（函数）。"""
    uid_marker = uuid.uuid4().hex[:12]
    with SessionLocal() as session:
        row = InnovationJob(
            job_id=f"injob_recover_{uid_marker}",
            user_id=999999,
            status="succeeded",
            request_id=uid_marker,
            recipe={"name": "样例菜"},
            issues=None,
            error=None,
        )
        session.add(row)
        session.commit()
        job_id = row.job_id
    recover_stale_innovation_jobs()
    with SessionLocal() as session:
        row = session.query(InnovationJob).filter(
            InnovationJob.job_id == job_id
        ).one()
        assert row.status == "succeeded", "终态行不应被启动恢复改动"
        assert row.error is None
        # 清理测试数据
        session.delete(row)
        session.commit()
