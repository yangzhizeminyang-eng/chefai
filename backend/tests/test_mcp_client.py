"""MCP stdio 客户端单测（mcp_client.py + stub server，全部离线）。

覆盖（stub server 场景由命令行参数控制）：
    1. 连接成功 + initialize 握手（normal）；
    2. tools/list 发现 ≥1 个工具（normal，2 个）；
    3. tools/call 成功回显（normal）；
    4. 坏命令（不存在的模块）→ MCPConnectionError；
    5. 延迟超时（slow 场景休眠 30s > 客户端 1s 预算）→ MCPTimeoutError；
    6. 参数错误（bad_params 场景 -32602）→ MCPInvalidParams；
    7. 未知方法（-32601）→ MCPUnavailableError；
    8. 权限拒绝（permission 场景 isError + permission 文案）→ MCPPermissionError；
    9. close 后 stub 进程以退出码 0 正常结束（stdin EOF 优雅退出）。
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from app.ability.mcp_client import (
    MCPClient,
    MCPConnectionError,
    MCPInvalidParams,
    MCPPermissionError,
    MCPTimeoutError,
    MCPUnavailableError,
)

# stub server 脚本路径（tests/stubs/stub_mcp_server.py）
_STUB_PATH = Path(__file__).resolve().parent / "stubs" / "stub_mcp_server.py"


def _stub_command(scenario: str, timeout: float = 10.0) -> MCPClient:
    """构造指向 stub server 的客户端（函数）。

    参数：
        scenario：stub 场景名（normal/slow/bad_params/permission）。
        timeout：客户端单请求超时秒数。

    返回值：
        MCPClient：未连接的客户端实例。

    异常：
        无。
    """
    return MCPClient([sys.executable, str(_STUB_PATH), scenario], timeout_seconds=timeout)


class TestMCPClientHappyPath:
    """normal 场景：握手 / 发现 / 调用 / 优雅退出。"""

    def test_connect_and_list_tools(self) -> None:
        """连接成功且 tools/list 返回 2 个工具（函数）。

        异常：
            断言失败即测试失败。
        """
        client = _stub_command("normal")
        client.connect()
        try:
            tools = client.list_tools()
            assert len(tools) >= 1
            assert {"name", "inputSchema"} <= set(tools[0].keys())
            assert {t["name"] for t in tools} == {"stub_echo", "stub_meta"}
        finally:
            client.close()

    def test_call_tool_success(self) -> None:
        """tools/call 成功：结果含 content text 回显且 isError=False（函数）。

        异常：
            断言失败即测试失败。
        """
        client = _stub_command("normal")
        client.connect()
        try:
            result = client.call_tool("stub_echo", {"q": "番茄"})
            assert result.get("isError") is False
            text = result["content"][0]["text"]
            assert '"q": "番茄"' in text or '"q":"番茄"' in text
        finally:
            client.close()

    def test_close_terminates_gracefully(self) -> None:
        """close 后 stub 进程以退出码 0 正常结束（stdin EOF 路径）（函数）。

        异常：
            断言失败即测试失败。
        """
        client = _stub_command("normal")
        client.connect()
        proc = client._proc
        assert proc is not None
        client.close()
        assert proc.poll() == 0, f"stub server 退出码非 0：{proc.returncode}"


class TestMCPClientFailures:
    """失败分支：坏命令 / 超时 / 参数错 / 未知方法 / 权限拒绝。"""

    def test_bad_command_raises_connection_error(self) -> None:
        """不存在的模块命令 → 握手期 MCPConnectionError（函数）。

        异常：
            断言失败即测试失败。
        """
        client = MCPClient([sys.executable, "-m", "aicook_no_such_module_9812"], timeout_seconds=5.0)
        with pytest.raises(MCPConnectionError):
            client.connect()
        client.close()

    def test_slow_tool_call_times_out(self) -> None:
        """slow 场景（休眠 30s）超出 1s 预算 → MCPTimeoutError（函数）。

        异常：
            断言失败即测试失败。
        """
        client = _stub_command("slow", timeout=1.0)
        client.connect()
        try:
            with pytest.raises(MCPTimeoutError):
                client.call_tool("stub_echo", {"q": "x"})
        finally:
            client.close()

    def test_bad_params_maps_invalid_params(self) -> None:
        """bad_params 场景（协议错误 -32602）→ MCPInvalidParams（函数）。

        异常：
            断言失败即测试失败。
        """
        client = _stub_command("bad_params")
        client.connect()
        try:
            with pytest.raises(MCPInvalidParams):
                client.call_tool("stub_echo", {"q": "x"})
        finally:
            client.close()

    def test_unknown_method_maps_unavailable(self) -> None:
        """未知方法（协议错误 -32601）→ MCPUnavailableError（函数）。

        异常：
            断言失败即测试失败。
        """
        client = _stub_command("normal")
        client.connect()
        try:
            with pytest.raises(MCPUnavailableError):
                client.request("bogus/method", {})
        finally:
            client.close()

    def test_permission_denied_maps_permission_error(self) -> None:
        """permission 场景（isError=true + permission 文案）→ MCPPermissionError（函数）。

        异常：
            断言失败即测试失败。
        """
        client = _stub_command("permission")
        client.connect()
        try:
            with pytest.raises(MCPPermissionError):
                client.call_tool("stub_echo", {"q": "x"})
        finally:
            client.close()

    def test_ping_returns_empty_result(self) -> None:
        """ping 方法返回空对象结果（协议一致性冒烟）（函数）。

        异常：
            断言失败即测试失败。
        """
        client = _stub_command("normal")
        client.connect()
        try:
            assert client.request("ping", {}) == {}
        finally:
            client.close()


if __name__ == "__main__":  # pragma: no cover
    sys.exit(pytest.main([__file__, "-q"]))
