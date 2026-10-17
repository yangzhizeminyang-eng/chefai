"""Agent 工具框架单测（tools.py：校验/超时/幂等缓存/权限）。

覆盖：
    1. invalid_params：缺少必填参数 → execute_tool 返回结构化错误（不抛异常）；
    2. timeout：stub 工具 sleep 超过 ctx.max_timeout_seconds → error_code=timeout
       （重试耗尽后仍为 timeout）；
    3. 幂等缓存：只读工具同参数二次调用 cached=True 且 attempts=0；
    4. permission_denied：InventoryQueryTool 无 user_id → permission_denied。

测试全部离线确定性（不依赖 DB——DB 不可用路径不在本文件覆盖范围）。
"""

from __future__ import annotations

import time

import pytest

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
    """

    name = "stub_count"
    description = "测试用计数工具（验证幂等缓存）"
    read_only = True

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
