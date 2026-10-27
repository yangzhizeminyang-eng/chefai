"""MCP 子进程真实启动冒烟测试（python -m mcp_server × AICOOK_MCP_STUB=1）。

覆盖（subprocess 真实拉起 backend/mcp_server，完成 JSON-RPC 2.0 / MCP
2024-11-05 协议闭环，全部离线、零 DB 依赖）：
    1. initialize 握手：protocolVersion="2024-11-05"、serverInfo=
       aicook-readonly-mcp/1.0.0、capabilities.tools 存在；
    2. tools/list 发现：恰返回 recipe_search / recipe_detail 两个只读工具
      （name/description/inputSchema，required 齐备）；
    3. tools/call 成功：recipe_search（stub 演示载荷）与 recipe_detail
      （found=True 回显 recipe_id），isError=False、content[0] 为 text；
    4. tools/call 白名单外工具 → 结果级错误 isError=True + permission 文案
       （客户端映射 MCPPermissionError）；
    5. ping → 空对象结果；未知方法 → 协议级 -32601（映射 MCPUnavailableError）；
    6. 非法 JSON 请求行 → 协议级 -32700（id=None）且服务进程不崩溃、继续服务；
    7. stdin EOF → 子进程以退出码 0 优雅结束。

实现说明：
    闭环一走真实 MCPClient（app.ability.mcp_client，与生产同链路）；协议级
    细节（-32700 / id=None 错误行）用裸 subprocess.Popen 直接读写 stdin/stdout
    取证；AICOOK_MCP_STUB=1 经环境变量注入子进程，stub 模式不导入 app、
    不连 DB，进程秒级拉起。
"""

from __future__ import annotations

import json
import os
import queue
import subprocess
import sys
import threading
from pathlib import Path

import pytest

from app.ability.mcp_client import (
    MCPClient,
    MCPPermissionError,
    MCPUnavailableError,
)

# backend 根目录（python -m mcp_server 的导入起点）
_BACKEND_ROOT = Path(__file__).resolve().parents[1]

# 子进程协议编码（Windows 默认 GBK 会损坏中文 stub 载荷，显式 UTF-8）
_CHILD_ENV_EXTRA = {"AICOOK_MCP_STUB": "1", "PYTHONIOENCODING": "utf-8"}


def _stub_env() -> dict:
    """构造 stub 模式子进程环境（函数）。

    参数：
        无。

    返回值：
        dict：当前进程环境 + AICOOK_MCP_STUB=1 + 强制 UTF-8 编码。

    异常：
        无。
    """
    env = dict(os.environ)
    env.update(_CHILD_ENV_EXTRA)
    return env


def _spawn_raw_server() -> subprocess.Popen:
    """裸 Popen 拉起真实 mcp_server 子进程（函数）。

    说明：
        cwd 固定 backend 根（保证 -m mcp_server 可导入）；stderr 丢弃，
        stdin/stdout 为 UTF-8 文本管道。

    参数：
        无。

    返回值：
        subprocess.Popen：运行中的 server 子进程。

    异常：
        拉起失败向上抛出。
    """
    return subprocess.Popen(
        [sys.executable, "-m", "mcp_server"],
        cwd=str(_BACKEND_ROOT),
        env=_stub_env(),
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        text=True,
        encoding="utf-8",
    )


def _read_line(proc: subprocess.Popen, timeout: float = 15.0) -> dict:
    """带超时读取子进程一行 JSON-RPC 消息（函数）。

    说明：
        读行走 daemon 线程 + 队列，防对端异常时 readline 永久阻塞；
        空行跳过。

    参数：
        proc：server 子进程。
        timeout：读行超时秒数。

    返回值：
        dict：解析后的 JSON-RPC 消息。

    异常：
        AssertionError：超时未读到消息 / 对端 EOF。
    """
    result: queue.Queue = queue.Queue()

    def _pump() -> None:
        """后台读行泵（内嵌函数）。

        异常：
            无（EOF/异常以 None 哨兵入队）。
        """
        assert proc.stdout is not None
        try:
            for raw in proc.stdout:
                line = raw.strip()
                if line:
                    result.put(json.loads(line))
                    return
        except Exception:  # noqa: BLE001 —— 读失败按 EOF 处理
            pass
        result.put(None)

    threading.Thread(target=_pump, daemon=True).start()
    message = result.get(timeout=timeout)
    assert message is not None, "server 未在超时内返回完整一行消息"
    return message


def _write_line(proc: subprocess.Popen, payload: dict | str) -> None:
    """向子进程 stdin 写一行并刷出（函数）。

    参数：
        proc：server 子进程。
        payload：字典（序列化为 JSON）或原始字符串（用于非法行）。

    返回值：
        None。

    异常：
        管道断开时向上抛出。
    """
    line = payload if isinstance(payload, str) else json.dumps(payload, ensure_ascii=False)
    assert proc.stdin is not None
    proc.stdin.write(line + "\n")
    proc.stdin.flush()


@pytest.fixture()
def stub_client(monkeypatch: pytest.MonkeyPatch) -> MCPClient:
    """指向真实 mcp_server 子进程的 MCPClient fixture（函数）。

    说明：
        monkeypatch 注入 AICOOK_MCP_STUB=1（子进程继承）并 chdir 到
        backend 根（保证 -m mcp_server 可导入，测试后自动恢复）；
        teardown 关闭客户端回收子进程。

    参数：
        monkeypatch：pytest 打桩器。

    返回值：
        MCPClient：已 connect（完成 initialize 握手）的客户端。

    异常：
        握手失败向上抛出（真实 server 行为回归）。
    """
    monkeypatch.setenv("AICOOK_MCP_STUB", "1")
    monkeypatch.chdir(_BACKEND_ROOT)
    client = MCPClient([sys.executable, "-m", "mcp_server"], timeout_seconds=30.0)
    client.connect()
    yield client
    client.close()


class TestMcpSubprocessSmoke:
    """python -m mcp_server（stub）协议闭环冒烟（测试类）。"""

    def test_initialize_handshake_contract(self, stub_client: MCPClient) -> None:
        """initialize 契约：协议版本 / serverInfo / capabilities（函数）。

        说明：
            connect() 已完成一次握手，此处重复请求 initialize 直接验证
            响应体字段（server 无会话状态，幂等回复）。

        参数：
            stub_client：已连接的 MCPClient fixture。

        返回值：
            None。

        异常：
            断言失败即测试失败。
        """
        result = stub_client.request("initialize", {"protocolVersion": "2024-11-05", "capabilities": {}})
        assert result.get("protocolVersion") == "2024-11-05"
        assert result.get("serverInfo", {}).get("name") == "aicook-readonly-mcp"
        assert result.get("serverInfo", {}).get("version") == "1.0.0"
        assert "tools" in result.get("capabilities", {})

    def test_tools_list_discovers_readonly_whitelist(self, stub_client: MCPClient) -> None:
        """tools/list 恰返回两个白名单只读工具且 Schema 完整（函数）。

        参数：
            stub_client：已连接的 MCPClient fixture。

        返回值：
            None。

        异常：
            断言失败即测试失败。
        """
        tools = stub_client.list_tools()
        assert {t["name"] for t in tools} == {"recipe_search", "recipe_detail"}
        for tool in tools:
            assert tool["description"], "工具描述不得为空"
            schema = tool["inputSchema"]
            assert schema.get("type") == "object"
            assert schema.get("required"), "两个 stub 工具均有必填参数"
            assert set(schema.get("properties", {})), "Schema 须声明参数属性"

    def test_ping_returns_empty_result(self, stub_client: MCPClient) -> None:
        """ping 返回空对象结果（函数）。

        参数：
            stub_client：已连接的 MCPClient fixture。

        返回值：
            None。

        异常：
            断言失败即测试失败。
        """
        assert stub_client.request("ping", {}) == {}

    def test_tools_call_recipe_search_stub_payload(self, stub_client: MCPClient) -> None:
        """recipe_search 返回 stub 演示载荷（isError=False）（函数）。

        参数：
            stub_client：已连接的 MCPClient fixture。

        返回值：
            None。

        异常：
            断言失败即测试失败。
        """
        result = stub_client.call_tool("recipe_search", {"query": "番茄", "top_k": 3})
        assert result.get("isError") is False
        content = result["content"]
        assert content and content[0]["type"] == "text"
        payload = json.loads(content[0]["text"])
        assert payload["count"] == 1
        assert payload["results"][0]["recipe_id"] == 1
        assert "番茄炒蛋（stub）" in payload["results"][0]["title"]

    def test_tools_call_recipe_detail_echoes_id(self, stub_client: MCPClient) -> None:
        """recipe_detail 回显 recipe_id 且 found=True（函数）。

        参数：
            stub_client：已连接的 MCPClient fixture。

        返回值：
            None。

        异常：
            断言失败即测试失败。
        """
        result = stub_client.call_tool("recipe_detail", {"recipe_id": 42})
        assert result.get("isError") is False
        payload = json.loads(result["content"][0]["text"])
        assert payload["found"] is True
        assert payload["recipe"]["recipe_id"] == 42

    def test_non_whitelisted_tool_is_permission_denied(self, stub_client: MCPClient) -> None:
        """白名单外工具 → isError + permission 文案（结果级拒绝）（函数）。

        参数：
            stub_client：已连接的 MCPClient fixture。

        返回值：
            None。

        异常：
            断言失败即测试失败。
        """
        with pytest.raises(MCPPermissionError, match="permission"):
            stub_client.call_tool("delete_recipe", {"recipe_id": 1})

    def test_unknown_method_maps_protocol_error(self, stub_client: MCPClient) -> None:
        """未知方法 → 协议级 -32601（客户端映射 MCPUnavailableError）（函数）。

        参数：
            stub_client：已连接的 MCPClient fixture。

        返回值：
            None。

        异常：
            断言失败即测试失败。
        """
        with pytest.raises(MCPUnavailableError):
            stub_client.request("bogus/method", {})

    def test_malformed_line_parse_error_and_server_survives(self) -> None:
        """非法 JSON 行 → -32700（id=None）且服务不崩溃继续服务（函数）。

        说明：
            裸 Popen 直读 stdout 取证协议级错误行结构：{"jsonrpc":"2.0",
            "id":null,"error":{"code":-32700,...}}；随后合法 ping 仍正常
            回复，证明单条坏行不终止服务进程。

        参数：
            无。

        返回值：
            None。

        异常：
            断言失败即测试失败。
        """
        proc = _spawn_raw_server()
        try:
            _write_line(proc, "this is {{{ not json")
            parse_error = _read_line(proc)
            assert parse_error.get("jsonrpc") == "2.0"
            assert parse_error.get("id") is None
            assert parse_error.get("error", {}).get("code") == -32700

            _write_line(proc, {"jsonrpc": "2.0", "id": 99, "method": "ping", "params": {}})
            pong = _read_line(proc)
            assert pong.get("id") == 99
            assert pong.get("result") == {}
        finally:
            proc.stdin.close()
            proc.wait(timeout=10)

    def test_stdin_eof_graceful_exit(self, stub_client: MCPClient) -> None:
        """stdin EOF → 子进程以退出码 0 优雅结束（函数）。

        参数：
            stub_client：已连接的 MCPClient fixture。

        返回值：
            None。

        异常：
            断言失败即测试失败。
        """
        proc = stub_client._proc
        assert proc is not None
        stub_client.close()
        assert proc.poll() == 0, f"server 退出码非 0：{proc.returncode}"


if __name__ == "__main__":  # pragma: no cover
    sys.exit(pytest.main([__file__, "-q"]))
