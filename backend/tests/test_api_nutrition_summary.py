"""营养汇总与补录集成测试（模块 G）。

覆盖：
    - manual 补录：描述命中风控（医疗句式「吃什么降血糖」→ 200 blocked，不落库）、
      正常落库 201、meal_type 非法 422；
    - summary：缺失营养记录进入 excluded、totals 不含该项 0 值（键为 null，绝不按 0 计）、
      days ∈ {1,7,30} 校验；完成烹饪后合计出现真实估算值；
    - cooking finish 增强：同步写 meal_record（source=cooking，响应带 meal_record_id）。
"""

from __future__ import annotations

import uuid
from datetime import date

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.api.v1 import nutrition as nutrition_api
from app.api.v1.router import api_router
from app.core.db import SessionLocal
from app.models import MealRecord, User

# 并行开发约定：router.py 由集成步骤统一注册；未注册时此处补注册（进程级标记守卫，
# 避免懒加载路由下重复 include 产生 OpenAPI Duplicate Operation ID 告警）。
if not getattr(api_router, "_t3_nutrition_registered", False):
    api_router.include_router(nutrition_api.router)
    api_router._t3_nutrition_registered = True


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


@pytest.fixture()
def anon_id() -> str:
    """唯一匿名 ID fixture（函数）。

    说明：
        自建数据自清理：测试结束后删除用户行，meal_record/会话等随级联清理。

    返回值：
        str：唯一匿名 ID。

    异常：
        清理失败向上抛出。
    """
    value = f"anon_t3nut_{uuid.uuid4().hex[:10]}"
    yield value
    with SessionLocal() as db:
        user = db.execute(select(User).where(User.anonymous_id == value)).scalar_one_or_none()
        if user is not None:
            db.delete(user)
            db.commit()


def _manual(client: TestClient, anon: str, meal_type: str, description: str) -> dict:
    """手动补录辅助（函数）。

    参数：
        client：TestClient fixture。
        anon：匿名身份。
        meal_type：餐次。
        description：描述。

    返回值：
        dict：响应体。

    异常：
        断言失败即测试失败。
    """
    resp = client.post(
        "/v1/nutrition/manual",
        json={"meal_type": meal_type, "description": description},
        headers=_headers(anon),
    )
    assert resp.status_code in (200, 201), resp.text
    return resp.json()


def test_manual_blocked_by_risk_engine(client: TestClient, anon_id: str) -> None:
    """手动补录命中风控：200 blocked、不落库（函数）。

    参数：
        client：TestClient fixture。
        anon_id：唯一匿名身份 fixture。

    返回值：
        None。

    异常：
        断言失败即测试失败。
    """
    resp = client.post(
        "/v1/nutrition/manual",
        json={"meal_type": "lunch", "description": "吃什么降血糖"},
        headers=_headers(anon_id),
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["blocked"] is True
    assert body["rule_id"] == "MR-001"
    assert body["message"]

    with SessionLocal() as db:
        user = db.execute(select(User).where(User.anonymous_id == anon_id)).scalar_one()
        count = len(
            db.execute(select(MealRecord).where(MealRecord.user_id == int(user.id))).scalars().all()
        )
    assert count == 0, "被拦截的描述不得落库"


def test_manual_normal_creates_record(client: TestClient, anon_id: str) -> None:
    """手动补录正常路径：201 落库、营养为空（进 excluded）（函数）。

    参数：
        client：TestClient fixture。
        anon_id：唯一匿名身份 fixture。

    返回值：
        None。

    异常：
        断言失败即测试失败。
    """
    body = _manual(client, anon_id, "breakfast", "一碗白粥")
    assert body["blocked"] is False
    assert body["meal_type"] == "breakfast"
    assert body["description"] == "一碗白粥"
    assert body["recorded_date"] == date.today().isoformat()

    with SessionLocal() as db:
        user = db.execute(select(User).where(User.anonymous_id == anon_id)).scalar_one()
        record = db.execute(
            select(MealRecord).where(MealRecord.user_id == int(user.id))
        ).scalar_one()
    assert record.source == "manual"
    assert record.custom_name == "一碗白粥"
    assert record.kcal is None  # 无营养数据 → 汇总侧进 excluded

    # meal_type 非法 → 422
    assert (
        client.post(
            "/v1/nutrition/manual",
            json={"meal_type": "brunch", "description": "一份三明治"},
            headers=_headers(anon_id),
        ).status_code
        == 422
    )


def test_summary_excluded_never_zero(client: TestClient, anon_id: str) -> None:
    """summary：缺失营养进 excluded、totals 不按 0 计；完成烹饪后有真实合计（函数）。

    参数：
        client：TestClient fixture。
        anon_id：唯一匿名身份 fixture。

    返回值：
        None。

    异常：
        断言失败即测试失败。
    """
    _manual(client, anon_id, "lunch", "一碗白粥")

    body = client.get("/v1/nutrition/summary", params={"days": 1}, headers=_headers(anon_id)).json()
    assert len(body["days"]) == 1
    assert set(body["days"][0]["meals"].keys()) == {"breakfast", "lunch", "dinner", "snack"}
    # 🔴 缺失营养不按 0 计：totals.kcal 为 null（非 0），记录进 excluded
    assert body["totals"]["kcal"] is None
    assert "一碗白粥 未纳入统计" in body["totals"]["excluded"]
    assert "一碗白粥 未纳入统计" in body["excluded"]
    assert body["days"][0]["meals"]["lunch"]["kcal"] is None
    assert body["disclaimer"].startswith("估算值")

    # 完成一道有营养数据的菜（番茄炒蛋）后：合计出现真实估算值，excluded 仍保留缺口说明
    created = client.post("/v1/cooking/sessions", json={"recipe_id": 1, "servings": 2}, headers=_headers(anon_id))
    assert created.status_code == 200
    sid = created.json()["id"]
    assert client.post(f"/v1/cooking/sessions/{sid}/finish", json={}, headers=_headers(anon_id)).status_code == 200

    after = client.get("/v1/nutrition/summary", params={"days": 1}, headers=_headers(anon_id)).json()
    assert after["totals"]["kcal"] is not None and after["totals"]["kcal"] > 0
    assert "一碗白粥 未纳入统计" in after["excluded"]


def test_finish_writes_meal_record(client: TestClient, anon_id: str) -> None:
    """cooking finish 增强：同步写 meal_record 且响应带 meal_record_id（函数）。

    参数：
        client：TestClient fixture。
        anon_id：唯一匿名身份 fixture。

    返回值：
        None。

    异常：
        断言失败即测试失败。
    """
    created = client.post("/v1/cooking/sessions", json={"recipe_id": 1, "servings": 2}, headers=_headers(anon_id))
    assert created.status_code == 200
    sid = created.json()["id"]

    finished = client.post(f"/v1/cooking/sessions/{sid}/finish", json={}, headers=_headers(anon_id))
    assert finished.status_code == 200
    body = finished.json()
    assert body["meal_record_id"] is not None  # 新增字段，原 session/nutrition 结构保持
    assert body["session"]["status"] == "completed"

    with SessionLocal() as db:
        record = db.execute(
            select(MealRecord).where(MealRecord.id == int(body["meal_record_id"]))
        ).scalar_one()
    assert record.source == "cooking"
    assert int(record.recipe_id) == 1
    assert record.custom_name == "番茄炒蛋"
    assert float(record.servings) == 2.0
    assert record.kcal is not None  # 菜谱营养数据齐备 → 落估算值
    assert record.recorded_date == date.today()
    assert record.meal_type in ("breakfast", "lunch", "dinner", "snack")  # 按完成时间归集


def test_summary_days_validation(client: TestClient, anon_id: str) -> None:
    """summary 窗口校验：仅允许 1/7/30（函数）。

    参数：
        client：TestClient fixture。
        anon_id：唯一匿名身份 fixture。

    返回值：
        None。

    异常：
        断言失败即测试失败。
    """
    assert client.get("/v1/nutrition/summary", params={"days": 5}, headers=_headers(anon_id)).status_code == 422
    for days in (1, 7, 30):
        resp = client.get("/v1/nutrition/summary", params={"days": days}, headers=_headers(anon_id))
        assert resp.status_code == 200
        assert len(resp.json()["days"]) == days
