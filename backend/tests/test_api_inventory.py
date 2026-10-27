"""库存与购物清单集成测试（模块 H）。

覆盖：
    - 库存 CRUD：POST 201/404/422、GET 默认在库 + 临期优先排序（NULL 最后）、
      PATCH 状态机（active→used；终态回退/再流转 422；他人 404）、DELETE 204；
    - 临期查询：N 天窗口按天分组、中性描述「距到期 X 天」（RL-3）；
    - 两段式扣减：suggest（只建议不改库存，主料无库存不返回）→
      confirm（档位降一档 plenty→mid→low→删除；mark_used 置 used）；
    - 购物清单：同名（ingredient_id 相同）合并去重、quantity_note 追加/更新、
      from_recipe_name 反解、勾选同步、to-inventory（low 档 + 删除清单行）、
      DELETE 204、致敏原标注存在。
"""

from __future__ import annotations

import uuid
from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.api.v1 import inventory as inventory_api
from app.api.v1.router import api_router
from app.core.db import SessionLocal
from app.models import User
from tests.conftest import ensure_router_registered

# 并行开发约定：router.py 由集成步骤统一注册；未注册时此处补注册。
# 守卫用进程级标记（懒加载路由下 path 探测不可靠，且同路由重复 include 会产生
# OpenAPI Duplicate Operation ID 告警）——统一走 conftest.ensure_router_registered。
ensure_router_registered(
    api_router,
    (inventory_api.router, inventory_api.shopping_router),
    flag="_t3_inventory_registered",
    probe_paths=("/v1/inventory", "/v1/shopping-list"),
)


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
        自建数据自清理：测试结束后删除该用户行，库存/清单/会话等随级联清理。

    返回值：
        str：唯一 anon_ 前缀匿名 ID。

    异常：
        清理失败向上抛出（暴露测试污染）。
    """
    value = f"anon_t3inv_{uuid.uuid4().hex[:10]}"
    yield value
    with SessionLocal() as db:
        user = db.execute(select(User).where(User.anonymous_id == value)).scalar_one_or_none()
        if user is not None:
            db.delete(user)
            db.commit()


def _add_item(client: TestClient, anon: str, ingredient_id: int, level: str, expire: date | None = None) -> dict:
    """新增库存条目辅助（函数）。

    参数：
        client：TestClient fixture。
        anon：匿名身份。
        ingredient_id：食材 ID。
        level：数量档位（low/mid/plenty）。
        expire：到期日期（可 None）。

    返回值：
        dict：创建响应体。

    异常：
        断言失败即测试失败。
    """
    resp = client.post(
        "/v1/inventory",
        json={"ingredient_id": ingredient_id, "quantity_level": level, "expire_date": expire.isoformat() if expire else None},
        headers=_headers(anon),
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


def test_create_and_list_order_and_allergens(client: TestClient, anon_id: str) -> None:
    """创建库存 + 列表临期优先排序 + 致敏原标注（函数）。

    参数：
        client：TestClient fixture。
        anon_id：唯一匿名身份 fixture。

    返回值：
        None。

    异常：
        断言失败即测试失败。
    """
    tomorrow = date.today() + timedelta(days=1)
    tomato = _add_item(client, anon_id, 1, "plenty", tomorrow)  # 番茄：无致敏原
    egg = _add_item(client, anon_id, 101, "low")  # 鸡蛋：allergen=['egg']
    assert tomato["quantity_level"] == "plenty"
    assert tomato["status"] == "active"
    assert tomato["location"] == "fridge"
    assert tomato["expire_date"] == tomorrow.isoformat()
    assert tomato["stocked_at"]
    assert tomato["allergen_codes"] == []
    assert egg["allergen_codes"] == ["egg"]  # H.9 致敏原标注存在

    listed = client.get("/v1/inventory", headers=_headers(anon_id)).json()["items"]
    assert [i["id"] for i in listed] == [tomato["id"], egg["id"]]  # 有到期日在前（临期优先），NULL 最后

    # 非法枚举 / 食材不存在
    assert client.post("/v1/inventory", json={"ingredient_id": 1, "quantity_level": "huge"}, headers=_headers(anon_id)).status_code == 422
    assert client.post("/v1/inventory", json={"ingredient_id": 999999999, "quantity_level": "low"}, headers=_headers(anon_id)).status_code == 404


def test_patch_status_machine_and_ownership(client: TestClient, anon_id: str) -> None:
    """PATCH 状态机与归属校验（函数）。

    参数：
        client：TestClient fixture。
        anon_id：唯一匿名身份 fixture。

    返回值：
        None。

    异常：
        断言失败即测试失败。
    """
    item = _add_item(client, anon_id, 2, "mid")

    patched = client.patch(
        f"/v1/inventory/{item['id']}",
        json={"quantity_level": "plenty", "location": "freezer"},
        headers=_headers(anon_id),
    )
    assert patched.status_code == 200
    assert patched.json()["quantity_level"] == "plenty"
    assert patched.json()["location"] == "freezer"

    # active → used 合法；used 为终态：回退 active / 再流转 expired 均 422
    used = client.patch(f"/v1/inventory/{item['id']}", json={"status": "used"}, headers=_headers(anon_id))
    assert used.status_code == 200
    assert used.json()["status"] == "used"
    assert client.patch(f"/v1/inventory/{item['id']}", json={"status": "active"}, headers=_headers(anon_id)).status_code == 422
    assert client.patch(f"/v1/inventory/{item['id']}", json={"status": "expired"}, headers=_headers(anon_id)).status_code == 422

    # 他人条目 404；状态过滤：used 列表可见、active 列表不可见
    other_anon = f"anon_t3inv_{uuid.uuid4().hex[:10]}"
    try:
        assert client.patch(f"/v1/inventory/{item['id']}", json={"status": "used"}, headers=_headers(other_anon)).status_code == 404
    finally:
        with SessionLocal() as db:
            stranger = db.execute(select(User).where(User.anonymous_id == other_anon)).scalar_one_or_none()
            if stranger is not None:
                db.delete(stranger)
                db.commit()
    used_list = client.get("/v1/inventory", params={"status": "used"}, headers=_headers(anon_id)).json()["items"]
    assert [i["id"] for i in used_list] == [item["id"]]
    active_list = client.get("/v1/inventory", headers=_headers(anon_id)).json()["items"]
    assert item["id"] not in [i["id"] for i in active_list]


def test_delete_inventory(client: TestClient, anon_id: str) -> None:
    """删除库存条目（函数）。

    参数：
        client：TestClient fixture。
        anon_id：唯一匿名身份 fixture。

    返回值：
        None。

    异常：
        断言失败即测试失败。
    """
    item = _add_item(client, anon_id, 3, "low")
    assert client.delete(f"/v1/inventory/{item['id']}", headers=_headers(anon_id)).status_code == 204
    assert client.get("/v1/inventory", headers=_headers(anon_id)).json()["items"] == []
    assert client.delete(f"/v1/inventory/{item['id']}", headers=_headers(anon_id)).status_code == 404
    assert client.delete("/v1/inventory/999999999", headers=_headers(anon_id)).status_code == 404


def test_expiring_grouped_by_day(client: TestClient, anon_id: str) -> None:
    """临期查询按天分组 + 中性描述（RL-3）（函数）。

    参数：
        client：TestClient fixture。
        anon_id：唯一匿名身份 fixture。

    返回值：
        None。

    异常：
        断言失败即测试失败。
    """
    today = date.today()
    _add_item(client, anon_id, 1, "plenty", today + timedelta(days=1))
    _add_item(client, anon_id, 2, "mid", today + timedelta(days=2))
    _add_item(client, anon_id, 3, "low", today + timedelta(days=10))  # 窗口外
    _add_item(client, anon_id, 101, "mid")  # 无到期日不参与

    resp = client.get("/v1/inventory/expiring", params={"days": 3}, headers=_headers(anon_id))
    assert resp.status_code == 200
    body = resp.json()
    assert body["days"] == 3
    assert [g["expire_date"] for g in body["groups"]] == [
        (today + timedelta(days=1)).isoformat(),
        (today + timedelta(days=2)).isoformat(),
    ]
    assert body["groups"][0]["days_left"] == 1
    assert body["groups"][0]["label"] == "距到期 1 天"
    # RL-3：仅中性描述，无判定字段
    assert "能吃" not in resp.text and "可食用" not in resp.text

    narrow = client.get("/v1/inventory/expiring", params={"days": 1}, headers=_headers(anon_id)).json()
    assert [g["days_left"] for g in narrow["groups"]] == [1]


def test_deduct_suggest_then_confirm(client: TestClient, anon_id: str) -> None:
    """两段式扣减：suggest 不改库存 → confirm 生效降档/标记已用（函数）。

    参数：
        client：TestClient fixture。
        anon_id：唯一匿名身份 fixture。

    返回值：
        None。

    异常：
        断言失败即测试失败。
    """
    tomato = _add_item(client, anon_id, 1, "plenty")  # 菜谱 1 主料：番茄 300g
    egg = _add_item(client, anon_id, 101, "mid")  # 菜谱 1 主料：鸡蛋 3 个

    created = client.post("/v1/cooking/sessions", json={"recipe_id": 1, "servings": 2}, headers=_headers(anon_id))
    assert created.status_code == 200
    sid = created.json()["id"]

    # 未完成会话 → 422
    assert client.post("/v1/inventory/deduct-suggest", json={"session_id": int(sid)}, headers=_headers(anon_id)).status_code == 422

    finished = client.post(f"/v1/cooking/sessions/{sid}/finish", json={}, headers=_headers(anon_id))
    assert finished.status_code == 200

    # suggest：主料且在库 → deduct 建议（reason 含用量）；不改库存
    suggest = client.post("/v1/inventory/deduct-suggest", json={"session_id": int(sid)}, headers=_headers(anon_id))
    assert suggest.status_code == 200
    suggestions = suggest.json()["suggestions"]
    assert {s["ingredient_id"] for s in suggestions} == {1, 101}
    assert all(s["suggest_action"] == "deduct" for s in suggestions)
    assert all("菜谱用量" in s["reason"] and "2 人份" in s["reason"] for s in suggestions)
    levels_after_suggest = {i["id"]: i["quantity_level"] for i in client.get("/v1/inventory", headers=_headers(anon_id)).json()["items"]}
    assert levels_after_suggest[tomato["id"]] == "plenty"  # 未改库存
    assert levels_after_suggest[egg["id"]] == "mid"

    # 他人会话 → 404
    other_anon = f"anon_t3inv_{uuid.uuid4().hex[:10]}"
    try:
        assert client.post("/v1/inventory/deduct-suggest", json={"session_id": int(sid)}, headers=_headers(other_anon)).status_code == 404
    finally:
        with SessionLocal() as db:
            stranger = db.execute(select(User).where(User.anonymous_id == other_anon)).scalar_one_or_none()
            if stranger is not None:
                db.delete(stranger)
                db.commit()

    # confirm：deduct 降一档 + mark_used 置 used
    confirm = client.post(
        "/v1/inventory/deduct-confirm",
        json={
            "session_id": int(sid),
            "confirmations": [
                {"item_id": tomato["id"], "action": "deduct"},
                {"item_id": egg["id"], "action": "mark_used"},
            ],
        },
        headers=_headers(anon_id),
    )
    assert confirm.status_code == 200
    assert confirm.json()["applied"] == 2
    active = {i["id"]: i["quantity_level"] for i in client.get("/v1/inventory", headers=_headers(anon_id)).json()["items"]}
    assert active[tomato["id"]] == "mid"  # plenty → mid
    assert egg["id"] not in active  # 已标记用完
    used_items = client.get("/v1/inventory", params={"status": "used"}, headers=_headers(anon_id)).json()["items"]
    assert egg["id"] in [i["id"] for i in used_items]

    # 再扣两档：mid → low → 删除条目
    first = client.post(
        "/v1/inventory/deduct-confirm",
        json={"session_id": int(sid), "confirmations": [{"item_id": tomato["id"], "action": "deduct"}]},
        headers=_headers(anon_id),
    )
    assert first.status_code == 200 and first.json()["applied"] == 1
    second = client.post(
        "/v1/inventory/deduct-confirm",
        json={"session_id": int(sid), "confirmations": [{"item_id": tomato["id"], "action": "deduct"}]},
        headers=_headers(anon_id),
    )
    assert second.status_code == 200 and second.json()["applied"] == 1
    remaining = client.get("/v1/inventory", headers=_headers(anon_id)).json()["items"]
    assert tomato["id"] not in [i["id"] for i in remaining]  # low 再扣 → 删除


def test_shopping_list_merge_and_to_inventory(client: TestClient, anon_id: str) -> None:
    """购物清单：合并去重 + 备注更新 + 转库存（函数）。

    参数：
        client：TestClient fixture。
        anon_id：唯一匿名身份 fixture。

    返回值：
        None。

    异常：
        断言失败即测试失败。
    """
    first = client.post(
        "/v1/shopping-list",
        json={
            "items": [
                {"ingredient_id": 1, "quantity_note": "2斤", "from_recipe_name": "番茄炒蛋"},
                {"ingredient_id": 2},
            ]
        },
        headers=_headers(anon_id),
    )
    assert first.status_code == 201
    assert first.json() == {"added": 2, "merged": 0}

    # 同 ingredient_id 合并：quantity_note 追加，不重复建行
    second = client.post(
        "/v1/shopping-list",
        json={"items": [{"ingredient_id": 1, "quantity_note": "再来1斤", "from_recipe_name": "番茄炒蛋"}]},
        headers=_headers(anon_id),
    )
    assert second.status_code == 201
    assert second.json() == {"added": 0, "merged": 1}

    items = client.get("/v1/shopping-list", headers=_headers(anon_id)).json()["items"]
    assert len(items) == 2
    tomato_row = next(i for i in items if i["ingredient_id"] == 1)
    potato_row = next(i for i in items if i["ingredient_id"] == 2)
    assert tomato_row["ingredient_name"] == "番茄"
    assert tomato_row["quantity_note"] == "2斤；再来1斤"
    assert tomato_row["from_recipe_name"] == "番茄炒蛋"  # 按标题反解
    assert tomato_row["checked"] is False
    assert potato_row["quantity_note"] is None

    # 致敏原标注（H.9）
    assert client.post("/v1/shopping-list", json={"items": [{"ingredient_id": 101}]}, headers=_headers(anon_id)).status_code == 201
    items = client.get("/v1/shopping-list", headers=_headers(anon_id)).json()["items"]
    egg_row = next(i for i in items if i["ingredient_id"] == 101)
    assert egg_row["allergen_codes"] == ["egg"]

    # 勾选同步
    checked = client.patch(f"/v1/shopping-list/{tomato_row['id']}", json={"checked": True}, headers=_headers(anon_id))
    assert checked.status_code == 200
    assert checked.json()["checked"] is True

    # 转库存：low 档 + 到期日，清单行删除
    converted = client.post(
        f"/v1/shopping-list/{potato_row['id']}/to-inventory",
        json={"expire_date": (date.today() + timedelta(days=5)).isoformat()},
        headers=_headers(anon_id),
    )
    assert converted.status_code == 201
    inventory_item_id = converted.json()["inventory_item_id"]
    remaining = client.get("/v1/shopping-list", headers=_headers(anon_id)).json()["items"]
    assert potato_row["id"] not in [i["id"] for i in remaining]
    inv_item = next(
        i for i in client.get("/v1/inventory", headers=_headers(anon_id)).json()["items"] if i["id"] == inventory_item_id
    )
    assert inv_item["quantity_level"] == "low"
    assert inv_item["ingredient_name"] == "土豆"
    assert inv_item["expire_date"] == (date.today() + timedelta(days=5)).isoformat()

    # 删除清单行 + 他人条目 404
    assert client.delete(f"/v1/shopping-list/{egg_row['id']}", headers=_headers(anon_id)).status_code == 204
    other_anon = f"anon_t3inv_{uuid.uuid4().hex[:10]}"
    try:
        assert client.patch(f"/v1/shopping-list/{tomato_row['id']}", json={"checked": False}, headers=_headers(other_anon)).status_code == 404
    finally:
        with SessionLocal() as db:
            stranger = db.execute(select(User).where(User.anonymous_id == other_anon)).scalar_one_or_none()
            if stranger is not None:
                db.delete(stranger)
                db.commit()
    # 食材不存在 → 404
    assert client.post("/v1/shopping-list", json={"items": [{"ingredient_id": 999999999}]}, headers=_headers(anon_id)).status_code == 404
