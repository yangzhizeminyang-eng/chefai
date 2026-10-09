"""V1.1 文档对齐集成测试（spec fix-onestart-align-v11 Task 1）。

覆盖：
    - GET /healthz、GET /v1/healthz、GET /api/health 三路由共用 handler，均 200
      且含 status/database 字段（04-V1.1 §7 / 05-V1.1 §9.5/§12.3 健康检查口径）；
    - POST /v1/search 与 POST /v1/ask 同文本同实现（02-V1.1 §9.1 #15 与
      05-V1.1 §12.3 两种口径并存）：blocked=true 且响应键集合一致，
      均无 results/candidates/nutrition 键（D9 短路纯净性）；
    - GET /v1/config/switches 返回五键布尔（05-V1.1 §4.4 第 5 个 switch.innovation）。
"""

from __future__ import annotations

from fastapi.testclient import TestClient


def test_healthz_three_routes(client: TestClient) -> None:
    """健康检查三路由均 200 且含 status/database 字段（函数）。

    说明：
        /api/health（既有兼容）、/healthz（docker 根级口径）、/v1/healthz
        （05-V1.1 标准口径）共用同一 handler，响应语义一致。

    参数：
        client：TestClient fixture。

    返回值：
        None。

    异常：
        断言失败即测试失败。
    """
    for path in ("/api/health", "/healthz", "/v1/healthz"):
        resp = client.get(path)
        assert resp.status_code == 200, f"{path} 应返回 200"
        body = resp.json()
        assert body["status"] == "ok"
        assert body["database"] == "up"
        assert "version" in body


def test_search_alias_same_as_ask(client: TestClient) -> None:
    """/v1/search 与 /v1/ask 同实现：同文本同响应键集合（函数）。

    说明：
        高危样本「木耳泡一晚上明天炒行吗」（FS-001）两入口均应被一票否决：
        intent=blocked 且 blocked.blocked=true；响应键集合完全一致，
        且均无 results/candidates/nutrition 键（D9 短路纯净性）。

    参数：
        client：TestClient fixture。

    返回值：
        None。

    异常：
        断言失败即测试失败。
    """
    text = "木耳泡一晚上明天炒行吗"
    # 不显式传 request_id，中间件自动生成，避免命中幂等缓存混淆两条执行路径
    body_ask = client.post("/v1/ask", json={"text": text}).json()
    body_search = client.post("/v1/search", json={"text": text}).json()

    # 两入口均命中阻断（intent=blocked 且 blocked.blocked=true）
    assert body_ask["intent"] == "blocked"
    assert body_search["intent"] == "blocked"
    assert body_ask["blocked"]["blocked"] is True
    assert body_search["blocked"]["blocked"] is True

    # 同一实现 → 响应键集合完全一致（值如 request_id/trace_id 允许不同）
    assert set(body_ask.keys()) == set(body_search.keys())

    # D9 短路纯净性：否决响应体不承载任何业务内容键
    for body in (body_ask, body_search):
        assert "results" not in body
        assert "candidates" not in body
        assert "nutrition" not in body


def test_switches_five_keys(client: TestClient) -> None:
    """远程开关返回五键且均为布尔（函数）。

    说明：
        05-V1.1 §4.4 五个远程开关：recommend/vision/qa/payment/innovation；
        模块 O 属阶段二，阶段一仅下发 switch.innovation 配置。

    参数：
        client：TestClient fixture。

    返回值：
        None。

    异常：
        断言失败即测试失败。
    """
    resp = client.get("/v1/config/switches")
    assert resp.status_code == 200
    body = resp.json()
    assert set(body.keys()) == {"recommend", "vision", "qa", "payment", "innovation"}
    for key, value in body.items():
        assert isinstance(value, bool), f"开关 {key} 应为布尔值"
