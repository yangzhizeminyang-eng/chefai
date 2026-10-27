"""工具用户隔离端到端测试（InventoryQueryTool × 真实执行链路）。

覆盖（双用户真实执行级隔离）：
    1. 双匿名用户经真实 API 各自入库库存 → execute_tool 真实执行
      （InventoryQueryTool 内部走真实 SessionLocal/PostgreSQL）→
      各自仅见本人库存（owner 过滤 + 真实 DB 行）；
    2. user_scoped 幂等缓存键隔离：用户 A 写入缓存后用户 B 执行，B 不命中
      A 的缓存（缓存键含 "u{user_id}\x00" 前缀）；A 再次执行命中自身缓存
      （cached=True 且数据仍为 A 的）；
    3. 匿名上下文（user_id=None）→ permission_denied 结构化拒绝，且不污染缓存；
    4. 删除库存 + 清缓存后再次执行 → 真实数据口径（count=0），证明工具结果
      由 DB 行驱动而非共享残留。

隔离手段：
    真实 SessionLocal + 真实 PostgreSQL（与 client fixture 同库）；
    匿名用户 anon_ 前缀 + uuid4，teardown 删除 User 行（DB 外键
    ondelete=CASCADE 级联清理库存行）；工具幂等缓存测试前后
    clear_tool_cache()，防跨测试缓存串扰。
"""

from __future__ import annotations

import uuid
from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app.ability.tools import InventoryQueryTool, ToolContext, ToolResult, clear_tool_cache, execute_tool
from app.core.db import SessionLocal
from app.models import InventoryItem, User

# 测试食材 ID（种子数据固定：1=番茄、2=土豆、101=鸡蛋，与 test_api_inventory 同源）
TOMATO_ID, POTATO_ID, EGG_ID = 1, 2, 101


@pytest.fixture(autouse=True)
def _clean_tool_cache():
    """工具幂等缓存清理 fixture（autouse，前后各清一次）。

    说明：
        工具缓存为进程级 LRU：前置清理防其他测试残留同键缓存造成
        cached 误判；后置清理防本测试的 user_scoped 键泄漏到后续测试。

    参数：
        无。

    返回值：
        None（yield 后执行清理）。

    异常：
        无。
    """
    clear_tool_cache()
    yield
    clear_tool_cache()


@pytest.fixture()
def two_anon_users() -> tuple[str, str]:
    """双唯一匿名用户 fixture（函数）。

    说明：
        生成两个互不相同、不与历史测试冲突的匿名 ID；teardown 按匿名 ID
        删除 User 行，库存/清单等随 DB 外键级联清理（自建数据自清理）。

    参数：
        无。

    返回值：
        tuple[str, str]：(用户 A 匿名 ID, 用户 B 匿名 ID)。

    异常：
        清理失败向上抛出（暴露测试污染）。
    """
    anon_a = "anon_tooliso_" + uuid.uuid4().hex[:10]
    anon_b = "anon_tooliso_" + uuid.uuid4().hex[:10]
    yield anon_a, anon_b
    with SessionLocal() as db:
        for anon in (anon_a, anon_b):
            row = db.execute(select(User).where(User.anonymous_id == anon)).scalar_one_or_none()
            if row is not None:
                db.delete(row)
        db.commit()


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


def _add_item(client: TestClient, anon: str, ingredient_id: int, level: str, expire: date | None = None) -> dict:
    """经真实 API 新增库存条目（函数）。

    说明：
        POST /v1/inventory（服务端以 upsert 语义自动创建匿名用户，
        DB 存 status=normal，工具查询口径可见）。

    参数：
        client：TestClient fixture。
        anon：匿名身份。
        ingredient_id：食材 ID。
        level：数量档位（low/mid/plenty）。
        expire：到期日期（可 None）。

    返回值：
        dict：创建响应体（含 id/ingredient_name/quantity_level 等）。

    异常：
        断言失败即测试失败。
    """
    payload = {
        "ingredient_id": ingredient_id,
        "quantity_level": level,
        "expire_date": expire.isoformat() if expire else None,
    }
    resp = client.post("/v1/inventory", json=payload, headers=_headers(anon))
    assert resp.status_code == 201, resp.text
    return resp.json()


def _user_id_of(anon: str) -> int:
    """按匿名 ID 查询真实用户数字 ID（函数）。

    说明：
        工具上下文 ToolContext.user_id 需要 DB 自增主键（与 API 头中的
        匿名字符串解耦），此处经真实 SessionLocal 取证。

    参数：
        anon：匿名会话 ID。

    返回值：
        int：User.id（真实主键）。

    异常：
        断言失败即测试失败（用户行不存在时 scalar_one 抛出）。
    """
    with SessionLocal() as db:
        user = db.execute(select(User).where(User.anonymous_id == anon)).scalar_one()
        return int(user.id)


def _run_inventory_tool(user_id: int | None, request_id: str) -> ToolResult:
    """以指定用户上下文真实执行库存查询工具（函数）。

    参数：
        user_id：执行上下文用户 ID（None=匿名，应被权限拒绝）。
        request_id：请求唯一标识（审计关联）。

    返回值：
        ToolResult：结构化执行结果（status/error_code/cached/result）。

    异常：
        不抛出（execute_tool 全分支转结构化结果）。
    """
    ctx = ToolContext(user_id=user_id, request_id=request_id, max_timeout_seconds=10.0)
    return execute_tool(InventoryQueryTool(), {}, ctx)


def _db_count_for(user_id: int) -> int:
    """直查 DB 统计某用户在库条目数（取证函数）。

    参数：
        user_id：用户数字 ID。

    返回值：
        int：InventoryItem 在库（normal/expiring）行数。

    异常：
        数据库异常向上抛出。
    """
    with SessionLocal() as db:
        stmt = (
            select(func.count())
            .select_from(InventoryItem)
            .where(InventoryItem.user_id == user_id)
            .where(InventoryItem.status.in_(("normal", "expiring")))
        )
        return int(db.execute(stmt).scalar_one())


def _rid() -> str:
    """生成测试专用 request_id（函数）。

    返回值：
        str：t_iso_ 前缀唯一标识。

    异常：
        无。
    """
    return "t_iso_" + uuid.uuid4().hex[:12]


class TestToolUserIsolationE2E:
    """双用户真实执行级隔离断言（测试类）。"""

    def test_inventory_query_returns_only_owner_items(
        self, client: TestClient, two_anon_users: tuple[str, str]
    ) -> None:
        """双用户各自仅见本人库存（owner 过滤 + user_scoped 缓存隔离）（函数）。

        参数：
            client：TestClient fixture。
            two_anon_users：双匿名用户 fixture。

        返回值：
            None。

        异常：
            断言失败即测试失败。
        """
        anon_a, anon_b = two_anon_users
        _add_item(client, anon_a, TOMATO_ID, "plenty", date.today() + timedelta(days=1))
        _add_item(client, anon_a, EGG_ID, "low")
        _add_item(client, anon_b, POTATO_ID, "mid")

        uid_a, uid_b = _user_id_of(anon_a), _user_id_of(anon_b)
        assert uid_a != uid_b, "两个匿名用户必须映射到不同的真实主键"

        # A 首次执行：真实 DB 查询，仅 A 的两条
        first_a = _run_inventory_tool(uid_a, _rid())
        assert first_a.status == "ok"
        assert first_a.cached is False
        names_a = {item["name"] for item in first_a.result["items"]}
        assert names_a == {"番茄", "鸡蛋"}
        assert first_a.result["count"] == 2

        # B 执行：A 刚写入缓存（u{uid_a} 键），B 必须命中自己的真实数据而非 A 的缓存
        first_b = _run_inventory_tool(uid_b, _rid())
        assert first_b.status == "ok"
        assert first_b.cached is False
        names_b = {item["name"] for item in first_b.result["items"]}
        assert names_b == {"土豆"}
        assert first_b.result["count"] == 1

        # A 再次执行：命中自身缓存，数据仍为 A 的（cached=True 且不串用户）
        second_a = _run_inventory_tool(uid_a, _rid())
        assert second_a.status == "ok"
        assert second_a.cached is True
        assert {item["name"] for item in second_a.result["items"]} == names_a

        # DB 交叉取证：工具结果与真实库存行数一致
        assert _db_count_for(uid_a) == 2
        assert _db_count_for(uid_b) == 1

    def test_anonymous_tool_context_is_permission_denied(
        self, client: TestClient, two_anon_users: tuple[str, str]
    ) -> None:
        """匿名上下文执行被结构化拒绝且不污染缓存（函数）。

        参数：
            client：TestClient fixture。
            two_anon_users：双匿名用户 fixture（此处仅用 A 制造数据）。

        返回值：
            None。

        异常：
            断言失败即测试失败。
        """
        anon_a, _ = two_anon_users
        _add_item(client, anon_a, TOMATO_ID, "mid")
        uid_a = _user_id_of(anon_a)

        denied = _run_inventory_tool(None, _rid())
        assert denied.status == "error"
        assert denied.error_code == "permission_denied"
        assert denied.result == {}  # 失败路径无载荷（dataclass 默认空 dict）
        assert denied.attempts == 1  # permission_denied 不可重试，仅一次尝试

        # 拒绝路径未写缓存：再以 A 执行仍为真实查询（cached=False）
        followup = _run_inventory_tool(uid_a, _rid())
        assert followup.status == "ok"
        assert followup.cached is False
        assert followup.result["count"] == 1

    def test_deleted_inventory_reflected_after_cache_clear(
        self, client: TestClient, two_anon_users: tuple[str, str]
    ) -> None:
        """库存删除 + 清缓存后执行结果跟随真实数据（函数）。

        参数：
            client：TestClient fixture。
            two_anon_users：双匿名用户 fixture。

        返回值：
            None。

        异常：
            断言失败即测试失败。
        """
        anon_a, _ = two_anon_users
        item = _add_item(client, anon_a, POTATO_ID, "low")
        uid_a = _user_id_of(anon_a)

        warmed = _run_inventory_tool(uid_a, _rid())
        assert warmed.result["count"] == 1  # 缓存已预热（u{uid_a} 键）

        # 真实删除 A 的条目（API 204），缓存中仍是旧结果
        deleted = client.delete("/v1/inventory/" + str(item["id"]), headers=_headers(anon_a))
        assert deleted.status_code == 204

        clear_tool_cache()  # 只读幂等缓存按设计不主动失效，清缓存后重新取证
        refreshed = _run_inventory_tool(uid_a, _rid())
        assert refreshed.status == "ok"
        assert refreshed.cached is False
        assert refreshed.result["items"] == []
        assert refreshed.result["count"] == 0
        assert _db_count_for(uid_a) == 0


if __name__ == "__main__":  # pragma: no cover
    import sys

    sys.exit(pytest.main([__file__, "-q"]))
