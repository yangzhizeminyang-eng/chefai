"""推荐主接口集成测试。

覆盖（spec Task 6.5）：
    - POST /v1/recommend 正常 200：results 1~8 条、trace_id、filtered_by、disclaimer_id；
    - 幂等：同 request_id 重复提交返回一致响应（X-Idempotent-Replay: true 头）；
    - 空 ingredients → 4xx 统一错误。
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from tests.conftest import unique_request_id


def test_recommend_normal_response(client: TestClient) -> None:
    """正常推荐 200：结构齐备（函数）。

    说明：
        以种子食材（番茄=1、鸡蛋，取库内真实 ID）发起推荐；
        断言 results 条数 1~8、每条 rank_reasons 非空、match_level 三档合法、
        filtered_by 存在、trace_id 与 disclaimer_id 回显。

    参数：
        client：TestClient fixture。

    返回值：
        None。

    异常：
        断言失败即测试失败。
    """
    rid = unique_request_id()
    resp = client.post(
        "/v1/recommend",
        json={
            "request_id": rid,
            "client_type": "web_stage1",
            "ingredients": [{"ingredient_id": 1, "quantity_level": "enough"}],
            "options": {"show_filtered": False},
        },
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["request_id"] == rid
    assert body["safe_mode"] is False
    assert 1 <= len(body["results"]) <= 8
    assert body["trace_id"]
    assert body["disclaimer_id"]
    assert isinstance(body["filtered_by"], dict)
    for item in body["results"]:
        # 前端 RecommendResultItem 必需字段齐备
        for key in (
            "recipe_id", "title", "match_level", "covered_ingredients", "missing_ingredients",
            "time_minutes", "difficulty", "calories_kcal", "allergens", "required_equipment",
            "rank_score", "rank_reasons", "source",
        ):
            assert key in item, f"results 缺少字段 {key}"
        assert item["rank_reasons"]
        assert item["match_level"] in ("can_cook_now", "missing_1_2", "need_more")
        assert item["difficulty"] in ("easy", "medium", "hard")


def test_recommend_idempotent_replay(client: TestClient) -> None:
    """同 request_id 重复提交返回缓存响应（函数）。

    说明：
        两次提交同一 request_id：第二次带 X-Idempotent-Replay: true 头，
        响应体与首次完全一致（不重复执行编排）。

    参数：
        client：TestClient fixture。

    返回值：
        None。

    异常：
        断言失败即测试失败。
    """
    rid = unique_request_id()
    payload = {
        "request_id": rid,
        "ingredients": [{"ingredient_id": 2, "quantity_level": "enough"}],
    }
    first = client.post("/v1/recommend", json=payload)
    assert first.status_code == 200
    assert first.headers.get("X-Idempotent-Replay") is None

    second = client.post("/v1/recommend", json=payload)
    assert second.status_code == 200
    assert second.headers.get("X-Idempotent-Replay") == "true"
    assert second.json() == first.json()


def test_recommend_empty_ingredients_4xx(client: TestClient) -> None:
    """空 ingredients 返回 4xx 统一错误（函数）。

    说明：
        ingredients=[] 触发 Pydantic 校验（min_length=1）→ 422，
        错误体为统一 {code, message, detail} 结构。

    参数：
        client：TestClient fixture。

    返回值：
        None。

    异常：
        断言失败即测试失败。
    """
    resp = client.post(
        "/v1/recommend",
        json={"request_id": unique_request_id(), "ingredients": []},
    )
    assert resp.status_code == 422
    body = resp.json()
    assert "message" in body and "code" in body
