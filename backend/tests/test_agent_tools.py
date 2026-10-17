"""Agent 工具框架单测（tools.py：校验/超时/幂等缓存/权限）。

覆盖：
    1. invalid_params：缺少必填参数 → execute_tool 返回结构化错误（不抛异常）；
    2. timeout：stub 工具 sleep 超过 ctx.max_timeout_seconds → error_code=timeout
       （重试耗尽后仍为 timeout）；
    3. 幂等缓存：只读工具同参数二次调用 cached=True 且 attempts=0；
    4. permission_denied：InventoryQueryTool 无 user_id → permission_denied；
    5. 用户作用域缓存：user_scoped 工具跨用户隔离、permission_denied 不入缓存、
       非 user_scoped 工具跨用户共享缓存。

测试全部离线确定性（不依赖 DB——DB 不可用路径不在本文件覆盖范围）。
"""

from __future__ import annotations

import time
from datetime import date
from types import SimpleNamespace
from typing import Any

import pytest

import app.ability.tools as tools
from app.ability.tools import (
    AgentTool,
    InventoryQueryTool,
    RecipeDetailTool,
    RecipeSearchTool,
    ToolContext,
    ToolError,
    clear_tool_cache,
    execute_tool,
)


class StubSleepTool(AgentTool):
    """超时验证用 stub 工具（模型类）：sleep 指定秒数后返回。

    属性：
        name：stub_sleep。
        description：测试用休眠工具。
        read_only：True。
    """

    name = "stub_sleep"
    description = "测试用休眠工具（验证执行框架超时控制）"
    read_only = True

    def parameters_schema(self) -> dict:
        """返回参数 Schema（函数）。

        返回值：
            dict：{"seconds": 可选数字（休眠秒数，默认 0.3）}。

        异常：
            无。
        """
        return {"type": "object", "properties": {"seconds": {"type": "number", "default": 0.3}}, "required": []}

    def execute(self, params: dict, ctx: ToolContext) -> dict:
        """执行休眠（函数）。

        参数：
            params：{"seconds": 休眠秒数}。
            ctx：执行上下文（未使用）。

        返回值：
            dict：{"slept": 实际休眠秒数}。

        异常：
            无。
        """
        seconds = float(params.get("seconds") or 0.3)
        time.sleep(seconds)
        return {"slept": seconds}


class StubCountTool(AgentTool):
    """缓存验证用计数 stub 工具（模型类）：每次真实执行自增计数。

    属性：
        name：stub_count。
        description：测试用计数工具。
        read_only：True。
        user_scoped：False（非用户作用域，缓存跨用户共享）。
    """

    name = "stub_count"
    description = "测试用计数工具（验证幂等缓存）"
    read_only = True
    user_scoped = False

    def __init__(self) -> None:
        """构造（函数）：执行计数初始化为 0。

        异常：
            无。
        """
        self.exec_count = 0

    def parameters_schema(self) -> dict:
        """返回参数 Schema（函数）。

        返回值：
            dict：{"q": 必填字符串}。

        异常：
            无。
        """
        return {"type": "object", "properties": {"q": {"type": "string"}}, "required": ["q"]}

    def execute(self, params: dict, ctx: ToolContext) -> dict:
        """执行计数（函数）。

        参数：
            params：{"q": 任意字符串}。
            ctx：执行上下文（未使用）。

        返回值：
            dict：{"echo": q, "exec": 执行计数}。

        异常：
            无。
        """
        self.exec_count += 1
        return {"echo": params.get("q"), "exec": self.exec_count}


@pytest.fixture(autouse=True)
def _clean_cache():
    """每用例前后清空工具幂等缓存（fixture）。

    异常：
        无。
    """
    clear_tool_cache()
    yield
    clear_tool_cache()


class TestExecuteToolValidation:
    """参数校验路径（execute_tool 结构化错误，不抛异常）。"""

    def test_invalid_params_missing_required(self) -> None:
        """缺少必填 query → status=error + error_code=invalid_params（函数）。

        异常：
            断言失败即测试失败。
        """
        result = execute_tool(RecipeSearchTool(), {}, ToolContext(user_id=1, request_id="t"))
        assert result.status == "error"
        assert result.error_code == "invalid_params"
        assert "query" in (result.message or "")
        assert result.attempts == 0

    def test_invalid_params_non_dict(self) -> None:
        """params 非字典 → invalid_params（函数）。

        异常：
            断言失败即测试失败。
        """
        result = execute_tool(RecipeDetailTool(), "not-a-dict", ToolContext())  # type: ignore[arg-type]
        assert result.status == "error"
        assert result.error_code == "invalid_params"

    def test_invalid_params_type_mismatch(self) -> None:
        """recipe_id 类型不合法（字符串数字可容忍，纯字母不可）→ invalid_params（函数）。

        说明：
            pydantic v2 对 int 字段的 "123" 会宽松转换，故用纯字母触发校验失败。

        异常：
            断言失败即测试失败。
        """
        result = execute_tool(RecipeDetailTool(), {"recipe_id": "abc"}, ToolContext())
        assert result.status == "error"
        assert result.error_code == "invalid_params"


class TestExecuteToolTimeout:
    """超时控制路径（线程池 future 超时 → ToolError(timeout) → 重试耗尽）。"""

    def test_timeout_returns_structured_error(self) -> None:
        """stub 工具 sleep 0.3s 超过 0.1s 预算 → error_code=timeout（函数）。

        说明：
            timeout 可重试：3 次尝试全部超时后仍返回 timeout（attempts=3）。

        异常：
            断言失败即测试失败。
        """
        result = execute_tool(StubSleepTool(), {"seconds": 0.3}, ToolContext(request_id="t", max_timeout_seconds=0.1))
        assert result.status == "error"
        assert result.error_code == "timeout"
        assert result.attempts == 3
        assert "timed out" in (result.message or "")


class TestIdempotentCache:
    """幂等缓存路径（只读工具成功结果 LRU 缓存）。"""

    def test_cache_hit_on_second_call(self) -> None:
        """同参数二次调用 → cached=True、attempts=0、真实执行仅 1 次（函数）。

        异常：
            断言失败即测试失败。
        """
        tool = StubCountTool()
        first = execute_tool(tool, {"q": "番茄"}, ToolContext(request_id="t"))
        assert first.status == "ok"
        assert first.cached is False
        assert first.attempts == 1
        second = execute_tool(tool, {"q": "番茄"}, ToolContext(request_id="t2"))
        assert second.status == "ok"
        assert second.cached is True
        assert second.attempts == 0
        assert tool.exec_count == 1, "缓存命中不应真实执行"
        assert second.result == first.result

    def test_different_params_miss_cache(self) -> None:
        """不同参数不命中缓存（真实执行 2 次）（函数）。

        异常：
            断言失败即测试失败。
        """
        tool = StubCountTool()
        execute_tool(tool, {"q": "a"}, ToolContext())
        result = execute_tool(tool, {"q": "b"}, ToolContext())
        assert result.cached is False
        assert tool.exec_count == 2


class TestPermissionDenied:
    """权限路径（归属敏感工具的 user_id 校验）。"""

    def test_inventory_query_without_user_id(self) -> None:
        """InventoryQueryTool 无 user_id → permission_denied（函数）。

        说明：
            permission_denied 不可重试：attempts=1（单次尝试即失败）。

        异常：
            断言失败即测试失败。
        """
        result = execute_tool(InventoryQueryTool(), {}, ToolContext(user_id=None, request_id="t"))
        assert result.status == "error"
        assert result.error_code == "permission_denied"
        assert result.attempts == 1

    def test_inventory_query_tool_error_contract(self) -> None:
        """直接调用工具（绕过框架）时抛 ToolError(permission_denied)（函数）。

        异常：
            断言失败即测试失败。
        """
        with pytest.raises(ToolError) as excinfo:
            InventoryQueryTool().execute({}, ToolContext(user_id=None))
        assert excinfo.value.code == "permission_denied"


def _inv_row(ingredient_id: int, name: str, *, status: str = "normal") -> tuple[Any, str]:
    """构造一行 fake 库存数据 (库存条目替身, 食材名)（函数）。

    参数：
        ingredient_id：食材 ID。
        name：食材名。
        status：库存状态（normal/expiring）。

    返回值：
        tuple[Any, str]：(SimpleNamespace 库存条目替身, 食材名)。

    异常：
        无。
    """
    expiry = date(2026, 1, 1) if status == "normal" else date(2026, 2, 1)
    item = SimpleNamespace(
        ingredient_id=ingredient_id,
        quantity_level="half",
        storage="fridge",
        expiry_date=expiry,
        status=status,
    )
    return (item, name)


def _user_id_from_stmt(stmt: Any) -> int | None:
    """从 SQLAlchemy 语句 where 条件提取 InventoryItem.user_id 过滤值（函数）。

    说明：
        测试替身用：fake session 据此模拟按 owner 过滤，返回各用户自己的库存行。

    参数：
        stmt：select/text 等 SQLAlchemy 语句对象。

    返回值：
        int | None：user_id 比较值；语句无该条件（如 text 探针）返回 None。

    异常：
        无。
    """
    clause = getattr(stmt, "whereclause", None)
    if clause is None:
        return None
    conds = list(clause) if hasattr(clause, "__iter__") else [clause]
    for cond in conds:
        left = getattr(cond, "left", None)
        right = getattr(cond, "right", None)
        if getattr(left, "key", None) == "user_id" and getattr(right, "value", None) is not None:
            return int(right.value)
    return None


class _FakeExecuteResult:
    """fake session.execute 的结果替身（模型类）。

    说明：
        仅实现 InventoryQueryTool 消费的 .all()。

    参数（构造）：
        rows：预置的 (库存条目, 食材名) 元组列表。

    异常：
        无。
    """

    def __init__(self, rows: list[tuple[Any, str]]) -> None:
        """构造（函数）：保存预置行。

        参数：
            rows：预置行列表。

        返回值：
            None。

        异常：
            无。
        """
        self._rows = rows

    def all(self) -> list[tuple[Any, str]]:
        """返回预置行（函数）。

        返回值：
            list[tuple[Any, str]]：(库存条目, 食材名) 行列表副本。

        异常：
            无。
        """
        return list(self._rows)


class _FakeInventorySession:
    """InventoryQueryTool 的 DB 会话替身（模型类）。

    说明：
        按语句 where 条件中的 InventoryItem.user_id 过滤值返回预置库存行，
        模拟不同用户持有不同库存；probe_db 的 SELECT 1 探针（无 where 条件）
        返回空行直接放行。

    参数（构造）：
        data_by_user：user_id -> [(库存条目, 食材名), ...] 的预置数据表。

    异常：
        无。
    """

    def __init__(self, data_by_user: dict[int, list[tuple[Any, str]]]) -> None:
        """构造（函数）：保存按用户预置的数据表。

        参数：
            data_by_user：user_id -> 行列表的映射。

        返回值：
            None。

        异常：
            无。
        """
        self._data_by_user = data_by_user

    def __enter__(self) -> _FakeInventorySession:
        """进入 with 上下文（函数）。

        返回值：
            _FakeInventorySession：自身。

        异常：
            无。
        """
        return self

    def __exit__(self, exc_type: Any, exc: Any, tb: Any) -> bool:
        """退出 with 上下文（函数）。

        参数：
            exc_type：异常类型（未使用）。
            exc：异常实例（未使用）。
            tb：回溯对象（未使用）。

        返回值：
            bool：False（不吞异常）。

        异常：
            无。
        """
        return False

    def execute(self, stmt: Any) -> _FakeExecuteResult:
        """执行语句替身（函数）。

        说明：
            从语句 where 条件提取 user_id 并返回该用户预置库存行；
            无 user_id 条件（text 探针）返回空行。

        参数：
            stmt：SQLAlchemy 语句对象。

        返回值：
            _FakeExecuteResult：可 .all() 的结果替身。

        异常：
            无。
        """
        user_id = _user_id_from_stmt(stmt)
        return _FakeExecuteResult(self._data_by_user.get(user_id, []))


class TestUserScopedCache:
    """用户作用域缓存路径（user_scoped 工具的跨用户缓存隔离契约）。"""

    def test_inventory_cache_isolated_per_user(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """user_scoped 工具：用户 2 同参数不命中用户 1 的缓存（函数）。

        说明：
            用户 1 查询结果入缓存后，用户 2 相同空参数必须真实执行并返回
            自己的库存（修复前命中用户 1 缓存：cached=True 且结果相同）。

        参数：
            monkeypatch：pytest 替身（替换 tools.SessionLocal 为 fake 会话工厂）。

        异常：
            断言失败即测试失败。
        """
        data = {1: [_inv_row(3, "鸡蛋")], 2: [_inv_row(7, "牛奶", status="expiring")]}
        monkeypatch.setattr(tools, "SessionLocal", lambda: _FakeInventorySession(data))
        tool = InventoryQueryTool()
        first = execute_tool(tool, {}, ToolContext(user_id=1, request_id="u1"))
        assert first.status == "ok"
        assert first.cached is False
        assert first.result["count"] == 1
        assert first.result["items"][0]["name"] == "鸡蛋"

        second = execute_tool(tool, {}, ToolContext(user_id=2, request_id="u2"))
        assert second.status == "ok"
        assert second.cached is False, "用户 2 不应命中用户 1 的缓存"
        assert second.result["items"][0]["name"] == "牛奶"
        assert second.result != first.result

    def test_inventory_permission_denied_not_cached(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """permission_denied 不写缓存：匿名两次均 denied，实名调用仍真实执行（函数）。

        说明：
            denied 结果绝不能进入幂等缓存污染后续调用（即便键相同）。

        参数：
            monkeypatch：pytest 替身（替换 tools.SessionLocal 为 fake 会话工厂）。

        异常：
            断言失败即测试失败。
        """
        data = {1: [_inv_row(3, "鸡蛋")]}
        monkeypatch.setattr(tools, "SessionLocal", lambda: _FakeInventorySession(data))
        tool = InventoryQueryTool()
        first = execute_tool(tool, {}, ToolContext(user_id=None, request_id="anon1"))
        second = execute_tool(tool, {}, ToolContext(user_id=None, request_id="anon2"))
        assert first.status == "error"
        assert first.error_code == "permission_denied"
        assert second.status == "error"
        assert second.error_code == "permission_denied"

        third = execute_tool(tool, {}, ToolContext(user_id=1, request_id="real"))
        assert third.status == "ok"
        assert third.cached is False, "denied 结果不应污染缓存，实名调用必须真实执行"

    def test_non_user_scoped_tools_share_cache(self) -> None:
        """user_scoped=False 工具跨用户共享缓存（防过度隔离回归）（函数）。

        异常：
            断言失败即测试失败。
        """
        tool = StubCountTool()
        first = execute_tool(tool, {"q": "番茄"}, ToolContext(user_id=1, request_id="u1"))
        second = execute_tool(tool, {"q": "番茄"}, ToolContext(user_id=2, request_id="u2"))
        assert first.cached is False
        assert second.cached is True, "非用户作用域工具不应因 user_id 不同而缓存未命中"
        assert tool.exec_count == 1
