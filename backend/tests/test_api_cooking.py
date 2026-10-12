"""烹饪会话集成测试（状态机 §12.1）。

覆盖（spec Task 6.5）：
    - create → 200 status=ongoing、allergen_conflict 无冲突；
    - PATCH next 推进 → current_step_no 递增；
    - GET 会话与 PATCH 结果一致；
    - finish(rating=5) → completed + recipe_feedback 落行；
    - finish 重复 → 409；
    - PATCH 不存在 id → 404；
    - abort → abandoned_step_no 保存、此后推进 409。
"""

from __future__ import annotations

from fastapi.testclient import TestClient
from sqlalchemy import text

from app.core.db import SessionLocal


def _create_session(client: TestClient, recipe_id: int = 1) -> dict:
    """创建测试会话（函数）。

    参数：
        client：TestClient fixture。
        recipe_id：菜谱 ID（默认 1 = 番茄炒蛋，已发布）。

    返回值：
        dict：会话响应体。

    异常：
        断言失败即测试失败。
    """
    resp = client.post("/v1/cooking/sessions", json={"recipe_id": recipe_id, "servings": 2})
    assert resp.status_code == 200
    return resp.json()


def test_create_session_ongoing(client: TestClient) -> None:
    """创建会话 → ongoing 且无过敏原冲突（函数）。

    说明：
        阶段一无家庭档案（D8）：allergen_conflict 为空数组（无冲突）。

    参数：
        client：TestClient fixture。

    返回值：
        None。

    异常：
        断言失败即测试失败。
    """
    session_body = _create_session(client)
    assert session_body["status"] == "ongoing"
    assert session_body["allergen_conflict"] == []
    assert session_body["allergen_conflict_bool"] is False
    assert session_body["current_step_no"] == 1
    assert session_body["recipe_id"] == 1
    assert session_body["servings"] == 2
    assert session_body["started_at"]


def test_patch_next_and_get_consistent(client: TestClient) -> None:
    """PATCH next 推进 + GET 会话一致（函数）。

    参数：
        client：TestClient fixture。

    返回值：
        None。

    异常：
        断言失败即测试失败。
    """
    session_body = _create_session(client)
    sid = session_body["id"]

    patched = client.patch(f"/v1/cooking/sessions/{sid}", json={"action": "next"})
    assert patched.status_code == 200
    assert patched.json()["current_step_no"] == 2

    fetched = client.get(f"/v1/cooking/sessions/{sid}")
    assert fetched.status_code == 200
    detail = fetched.json()
    assert detail["current_step_no"] == 2
    assert detail["status"] == "ongoing"
    # 断点续做快照：步骤齐备且带名称
    assert detail["total_steps"] >= 2
    assert detail["steps"][0]["no"] == 1
    assert detail["steps"][0]["description"]


def test_finish_writes_feedback(client: TestClient) -> None:
    """finish(rating=5) → completed + recipe_feedback 落行（函数）。

    参数：
        client：TestClient fixture。

    返回值：
        None。

    异常：
        断言失败即测试失败。
    """
    session_body = _create_session(client, recipe_id=2)
    sid = session_body["id"]

    finished = client.post(f"/v1/cooking/sessions/{sid}/finish", json={"rating": 5, "tags": ["好吃"]})
    assert finished.status_code == 200
    body = finished.json()
    assert body["session"]["status"] == "completed"
    assert body["session"]["completed_at"]
    # 营养小结（每份口径）
    assert body["nutrition"] is not None
    assert body["nutrition"]["estimate_note"].startswith("估算值")

    # recipe_feedback 落行
    with SessionLocal() as session:
        row = session.execute(
            text(
                "SELECT rating, feedback_type, tags FROM recipe_feedback "
                "WHERE session_id = :sid ORDER BY id DESC LIMIT 1"
            ),
            {"sid": int(sid)},
        ).first()
    assert row is not None, "recipe_feedback 未落行"
    assert row.rating == 5
    assert row.feedback_type == "cooked"
    assert "好吃" in (row.tags or [])


def test_finish_twice_conflict(client: TestClient) -> None:
    """finish 重复调用 → 409（函数）。

    参数：
        client：TestClient fixture。

    返回值：
        None。

    异常：
        断言失败即测试失败。
    """
    session_body = _create_session(client)
    sid = session_body["id"]
    first = client.post(f"/v1/cooking/sessions/{sid}/finish", json={})
    assert first.status_code == 200
    second = client.post(f"/v1/cooking/sessions/{sid}/finish", json={})
    assert second.status_code == 409
    assert second.json()["code"] == "STATE_CONFLICT"


def test_finish_feedback_supplement_after_completed(client: TestClient) -> None:
    """完成后提交评分 → 幂等补录 recipe_feedback；重复补录 → 409（函数）。

    说明（DEF-05）：
        - 完成时未评分（rating=null），完成页评价组件提交 {rating, tags} →
          带评分负载的 finish 补写 recipe_feedback(feedback_type='cooked')；
        - 每会话至多一条 cooked 评价，重复补录 → 409「该次烹饪已完成评价」；
        - 无评分负载的重复 finish 仍 409（既有幂等语义不变）。

    参数：
        client：TestClient fixture。

    返回值：
        None。

    异常：
        断言失败即测试失败。
    """
    session_body = _create_session(client, recipe_id=2)
    sid = session_body["id"]

    # 1) 完成会话（不带评分）
    first = client.post(f"/v1/cooking/sessions/{sid}/finish", json={})
    assert first.status_code == 200

    # 2) 带评分的补录 → 200（会话保持 completed，不重复写 meal_record）
    supplement = client.post(f"/v1/cooking/sessions/{sid}/finish", json={"rating": 4, "tags": ["太咸"]})
    assert supplement.status_code == 200
    assert supplement.json()["session"]["status"] == "completed"

    # 3) 重复补录 → 409，话术含「评价」
    again = client.post(f"/v1/cooking/sessions/{sid}/finish", json={"rating": 5})
    assert again.status_code == 409
    assert "评价" in again.json()["message"]

    # 4) 无评分负载的重复完成仍 409
    plain = client.post(f"/v1/cooking/sessions/{sid}/finish", json={})
    assert plain.status_code == 409

    # 5) recipe_feedback 落行：rating=4、tags 含「太咸」、feedback_type=cooked
    with SessionLocal() as session:
        row = session.execute(
            text(
                "SELECT rating, tags, feedback_type FROM recipe_feedback "
                "WHERE session_id = :sid ORDER BY id DESC LIMIT 1"
            ),
            {"sid": int(sid)},
        ).first()
    assert row is not None, "补录评分未落 recipe_feedback"
    assert row.rating == 4
    assert "太咸" in (row.tags or [])
    assert row.feedback_type == "cooked"


def test_patch_unknown_session_404(client: TestClient) -> None:
    """PATCH 不存在的会话 → 404（函数）。

    参数：
        client：TestClient fixture。

    返回值：
        None。

    异常：
        断言失败即测试失败。
    """
    resp = client.patch("/v1/cooking/sessions/999999999", json={"action": "next"})
    assert resp.status_code == 404
    assert resp.json()["code"] == "NOT_FOUND"


def test_abort_saves_abandoned_step(client: TestClient) -> None:
    """abort 保存 abandoned_step_no，此后不可推进（函数）。

    说明：
        abort 后状态回 not_started（表 CHECK 无 aborted 枚举），
        再次 next → 409（非 ongoing 不可推进）。

    参数：
        client：TestClient fixture。

    返回值：
        None。

    异常：
        断言失败即测试失败。
    """
    session_body = _create_session(client)
    sid = session_body["id"]
    client.patch(f"/v1/cooking/sessions/{sid}", json={"action": "next"})

    aborted = client.patch(f"/v1/cooking/sessions/{sid}", json={"action": "abort"})
    assert aborted.status_code == 200
    assert aborted.json()["abandoned_step_no"] == 2
    assert aborted.json()["status"] == "not_started"

    rejected = client.patch(f"/v1/cooking/sessions/{sid}", json={"action": "next"})
    assert rejected.status_code == 409
