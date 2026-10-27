"""应用 lifespan 启动逻辑测试（质量债清理：on_event → lifespan 迁移防回归）。

覆盖：
    - TestClient 进入时 lifespan 启动逻辑执行：创新任务恢复
      recover_stale_innovation_jobs 被调用（monkeypatch 记录桩）；
    - 恢复函数抛异常时启动不被阻断（lifespan 正常完成，健康检查路由可达）。

说明：
    app.main.lifespan 内部为局部导入 recover_stale_innovation_jobs，
    monkeypatch 目标为 app.api.v1.innovation 模块属性（运行时解析）。
    嵌入预热在测试进程为 hash provider + warmup 关闭 → no-op，不触网。
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

import app.api.v1.innovation as innovation_module
from app.main import app


def test_lifespan_triggers_innovation_recovery(monkeypatch: pytest.MonkeyPatch) -> None:
    """lifespan 启动阶段执行创新任务恢复（测试）。

    断言：
        - TestClient 进入（lifespan startup）时 recover_stale_innovation_jobs
          恰好被调用一次（与迁移前 @app.on_event("startup") 行为等价）；
        - 应用进入就绪状态，健康检查路由可达（200 或数据库降级 503）。

    参数：
        monkeypatch：替换 innovation 模块的恢复函数为记录桩。

    返回值：
        None。

    异常：
        断言失败即测试失败。
    """
    calls: list[int] = []
    monkeypatch.setattr(innovation_module, "recover_stale_innovation_jobs", lambda: calls.append(1))
    with TestClient(app) as client:
        assert calls == [1], "lifespan startup 应调用 recover_stale_innovation_jobs"
        assert client.get("/healthz").status_code in (200, 503)


def test_lifespan_survives_recovery_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    """恢复函数抛异常不阻断启动（测试）。

    断言：
        - recover_stale_innovation_jobs 抛 RuntimeError 时 lifespan 仍正常完成
          （启动逻辑尽力而为语义），TestClient 可进入且健康检查路由可达。

    参数：
        monkeypatch：替换恢复函数为抛异常桩。

    返回值：
        None。

    异常：
        断言失败即测试失败。
    """

    def _boom() -> None:
        """模拟恢复失败（内部函数）：抛出 RuntimeError。

        异常：
            RuntimeError：模拟数据库不可达等恢复失败场景。
        """
        raise RuntimeError("db down")

    monkeypatch.setattr(innovation_module, "recover_stale_innovation_jobs", _boom)
    with TestClient(app) as client:
        assert client.get("/healthz").status_code in (200, 503)
