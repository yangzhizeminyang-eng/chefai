"""一票否决短路集成测试（D9 红线取证）。

覆盖（spec Task 6.5）：
    - POST /v1/ask 高危输入 → blocked 响应（不含 results/candidates/nutrition 键）；
    - GET /v1/trace/{request_id} → veto=true、业务节点 not_executed/skipped_by_veto；
    - risk_log 留痕该请求。
"""

from __future__ import annotations

from fastapi.testclient import TestClient
from sqlalchemy import text

from app.core.db import SessionLocal
from tests.conftest import unique_request_id


def test_ask_veto_response_body_pure(client: TestClient) -> None:
    """高危 ask 输入 → 否决短路返回体纯净（函数）。

    说明：
        「木耳泡一晚上明天炒行吗」命中 FS-001：
        - intent=blocked，blocked.blocked=true，blocked.risk.rule_code 非空；
        - 🔴 顶层响应不含 results/candidates/nutrition 键（blocked 键内同样不含）。

    参数：
        client：TestClient fixture。

    返回值：
        None。

    异常：
        断言失败即测试失败。
    """
    rid = unique_request_id()
    resp = client.post("/v1/ask", json={"request_id": rid, "text": "木耳泡一晚上明天炒行吗"})
    assert resp.status_code == 200
    body = resp.json()

    # 🔴 纯净返回体：任何业务内容键都不得出现（顶层与否决体两层）
    for forbidden in ("results", "candidates", "nutrition"):
        assert forbidden not in body, f"否决响应顶层含业务键 {forbidden}"
        if isinstance(body.get("blocked"), dict):
            assert forbidden not in body["blocked"], f"否决体含业务键 {forbidden}"

    assert body["intent"] == "blocked"
    assert body["trace_id"]
    blocked = body["blocked"]
    assert blocked["blocked"] is True
    assert blocked["overrides_all"] is True
    assert blocked["risk"]["rule_code"]  # 非空
    assert blocked["risk"]["category"] == "food_safety_high_risk"
    # W-05 三段话术齐备（risk_message 表）
    assert blocked["risk"]["body"]
    assert blocked["risk"]["title"]


def test_veto_trace_and_risk_log(client: TestClient) -> None:
    """否决请求的 trace 取证与 risk_log 留痕（函数）。

    说明：
        - GET /v1/trace/{rid}：veto.veto=true；业务节点（supervisor / recipe_retrieve /
          hard_filter / recipe_rank / compose）状态 ∈ {not_executed, skipped_by_veto}；
        - risk_log 存在该请求行且 action=blocked。

    参数：
        client：TestClient fixture。

    返回值：
        None。

    异常：
        断言失败即测试失败。
    """
    rid = unique_request_id()
    resp = client.post("/v1/ask", json={"request_id": rid, "text": "豆角炒脆点可以吗"})
    assert resp.status_code == 200
    assert resp.json()["intent"] == "blocked"

    # trace 详情
    detail = client.get(f"/v1/trace/{rid}")
    assert detail.status_code == 200
    trace = detail.json()
    assert trace["veto"]["veto"] is True
    assert trace["risk"]["hit"] is True
    assert trace["risk"]["rule_code"]
    nodes = {n["node_name"]: n["status"] for n in trace["nodes"]}
    for business in ("supervisor", "recipe_retrieve", "hard_filter", "recipe_rank", "compose"):
        assert business in nodes, f"trace 缺少业务节点 {business}"
        assert nodes[business] in ("not_executed", "skipped_by_veto"), (
            f"业务节点 {business} 状态为 {nodes[business]}，违反一票否决短路"
        )
    assert trace["totals"]["total_duration_ms"] >= 0

    # risk_log 留痕
    with SessionLocal() as session:
        row = session.execute(
            text(
                "SELECT rule_code, action, stage FROM risk_log "
                "WHERE request_id = :rid ORDER BY id DESC LIMIT 1"
            ),
            {"rid": rid},
        ).first()
    assert row is not None, "risk_log 未留痕该请求"
    assert row.rule_code == "FS-002"
    assert row.action == "blocked"
