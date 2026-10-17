"""MCP stdio 客户端模块（JSON-RPC 2.0 最小实现，阶段二）。

职责：
    以子进程方式拉起 stdio MCP Server（backend/mcp_server），提供最小客户端：
    - connect()：Popen（stdin/stdout=PIPE，utf-8 文本）+ initialize 握手
      （读响应校验 id 匹配）+ notifications/initialized 通知；
    - list_tools()：tools/list → 工具描述列表；
    - call_tool(name, arguments)：tools/call → 结果 dict；结果级错误
      （isError=true）按文案映射：含 "permission" → MCPPermissionError，
      其余 → MCPUnavailableError；协议级错误按 code 映射：
      -32602 → MCPInvalidParams，其余（-32601/-32603/...）→ MCPUnavailableError；
    - close()：关 stdin（EOF 让 server 优雅退出）→ terminate + wait 3s → kill 兜底。

实现说明：
    响应读取走独立 daemon 读线程 + 队列（request() 按 deadline 阻塞取队列，
    超时抛 MCPTimeoutError）；请求间串行（锁）；通知（无 id 的消息）在读线程
    中丢弃，只把带 id 的响应入队。客户端不做任何重试——不可用时由调用方
    （tool_loop 节点）降级（剔除 MCP 工具，不阻断主链路）。
"""

from __future__ import annotations

import json
import queue
import subprocess
import threading
import time

from app.core.logging import get_logger

logger = get_logger(__name__)

# JSON-RPC 协议常量
PROTOCOL_VERSION = "2024-11-05"
CLIENT_NAME = "aicook-mcp-client"
CLIENT_VERSION = "1.0.0"

# close() 各阶段等待秒数（优雅退出 / 强杀兜底）
_CLOSE_WAIT_SECONDS = 3.0


class MCPError(Exception):
    """MCP 客户端异常基类（模型类）。

    说明：
        调用方按具体子类决定降级策略；本类用于 except MCPError 兜底捕获。

    属性：
        message：错误描述。
    """

    def __init__(self, message: str) -> None:
        """构造异常（函数）。

        参数：
            message：错误描述。

        返回值：
            None。

        异常：
            无。
        """
        super().__init__(message)
        self.message = message


class MCPConnectionError(MCPError):
    """连接/握手/进程死亡异常（模型类）：子进程拉起失败或管道中断。"""


class MCPTimeoutError(MCPError):
    """等待响应超时异常（模型类）：deadline 内未收到 id 匹配的响应。"""


class MCPPermissionError(MCPError):
    """权限拒绝异常（模型类）：tools/call 结果 isError 且文案含 permission。"""


class MCPInvalidParams(MCPError):
    """参数错误异常（模型类）：服务端协议级错误 -32602。"""


class MCPUnavailableError(MCPError):
    """服务不可用异常（模型类）：其余协议级错误（-32601/-32603 等）与结果级执行失败。"""


class MCPClient:
    """stdio MCP 客户端（模型类）。

    说明：
        线程安全性：request() 以互斥锁串行（单管道单请求）；读线程唯一消费
        stdout，把带 id 的响应放入队列，EOF 放入 None 哨兵。

    属性：
        server_command：Server 启动命令（argv 列表）。
        timeout_seconds：单请求超时预算秒数（握手/list_tools/call_tool 共用）。
    """

    def __init__(self, server_command: list[str], timeout_seconds: float = 15.0) -> None:
        """构造客户端（函数）。

        参数：
            server_command：Server 启动命令（如 ["python", "-m", "mcp_server"]）。
            timeout_seconds：单请求超时秒数（默认 15）。

        返回值：
            None。

        异常：
            无（拉起/握手失败延迟到 connect() 抛出）。
        """
        self.server_command = list(server_command)
        self.timeout_seconds = float(timeout_seconds)
        self._proc: subprocess.Popen | None = None
        self._reader: threading.Thread | None = None
        self._queue: queue.Queue = queue.Queue()
        self._lock = threading.Lock()
        self._next_id = 0

    # ------------------------------------------------------------------
    # 内部：读线程与请求收发
    # ------------------------------------------------------------------
    def _read_loop(self) -> None:
        """读线程主循环：逐行读 stdout，带 id 的响应入队（函数）。

        说明：
            通知（无 id）与非法 JSON 行静默丢弃（协议通道只消费合法响应）；
            EOF 时放入 None 哨兵，唤醒等待中的 request()。

        参数：
            无。

        返回值：
            None。

        异常：
            无（行级异常均吞掉——服务端输出脏行不应击穿客户端）。
        """
        assert self._proc is not None and self._proc.stdout is not None
        for raw_line in self._proc.stdout:
            line = raw_line.strip()
            if not line:
                continue
            try:
                message = json.loads(line)
            except Exception:  # noqa: BLE001 —— 脏行丢弃
                continue
            if isinstance(message, dict) and message.get("id") is not None:
                self._queue.put(message)
        self._queue.put(None)  # EOF 哨兵

    def _send(self, payload: dict) -> None:
        """向 stdin 写一行 JSON 并刷出（函数）。

        参数：
            payload：请求/通知字典。

        返回值：
            None。

        异常：
            MCPConnectionError：管道断开/进程已死/写失败。
        """
        assert self._proc is not None and self._proc.stdin is not None
        try:
            self._proc.stdin.write(json.dumps(payload, ensure_ascii=False) + "\n")
            self._proc.stdin.flush()
        except Exception as exc:  # noqa: BLE001 —— 统一包装为连接错误
            raise MCPConnectionError(f"failed to write to mcp server stdin: {exc}") from exc

    def _request(self, method: str, params: dict) -> dict:
        """发送请求并等待 id 匹配的响应（deadline 检查，函数）。

        说明：
            串行（锁内）；收到非本 id 响应（过期/串扰）继续等；EOF 哨兵 →
            MCPConnectionError；超 budget → MCPTimeoutError；协议级 error 响应
            按 code 映射（-32602 → MCPInvalidParams，其余 → MCPUnavailableError）。

        参数：
            method：JSON-RPC 方法名。
            params：请求参数。

        返回值：
            dict：响应 result 字段（缺省 {}）。

        异常：
            MCPConnectionError / MCPTimeoutError / MCPInvalidParams / MCPUnavailableError。
        """
        if self._proc is None or self._proc.poll() is not None:
            raise MCPConnectionError(f"mcp server is not running: {self.server_command}")
        with self._lock:
            self._next_id += 1
            request_id = self._next_id
            self._send({"jsonrpc": "2.0", "id": request_id, "method": method, "params": params})
            deadline = time.monotonic() + self.timeout_seconds
            while True:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise MCPTimeoutError(f"mcp request timed out after {self.timeout_seconds}s (method={method})")
                try:
                    item = self._queue.get(timeout=remaining)
                except queue.Empty:
                    continue
                if item is None:
                    raise MCPConnectionError(f"mcp server closed stdout unexpectedly (method={method})")
                if item.get("id") != request_id:
                    continue  # 过期响应（理论不发生，防御性跳过）
                if "error" in item:
                    err = item.get("error") or {}
                    code = err.get("code")
                    message = str(err.get("message") or "unknown error")
                    if code == -32602:
                        raise MCPInvalidParams(f"mcp invalid params ({method}): {message}")
                    raise MCPUnavailableError(f"mcp error {code} ({method}): {message}")
                result = item.get("result")
                return result if isinstance(result, dict) else {}

    # ------------------------------------------------------------------
    # 公共 API
    # ------------------------------------------------------------------
    def request(self, method: str, params: dict) -> dict:
        """发送任意 JSON-RPC 请求并返回 result（公开通用入口，函数）。

        说明：
            list_tools / call_tool 均基于本方法；亦供扩展方法（如 ping）与
            测试（未知方法 -32601 映射验证）直接使用。

        参数：
            method：JSON-RPC 方法名。
            params：请求参数。

        返回值：
            dict：响应 result 字段（缺省 {}）。

        异常：
            MCPConnectionError / MCPTimeoutError / MCPInvalidParams / MCPUnavailableError。
        """
        return self._request(method, params)

    def connect(self) -> None:
        """拉起 Server 子进程并完成 MCP 握手（函数）。

        说明：
            Popen（stdin/stdout=PIPE，text + utf-8，stderr 丢弃）→ 后台读线程 →
            initialize 请求（id 匹配由 _request 保证，响应须含 protocolVersion）→
            notifications/initialized 通知（不等待响应）。

        参数：
            无。

        返回值：
            None。

        异常：
            MCPConnectionError：命令不存在 / 进程立即退出 / 握手失败。
        """
        try:
            self._proc = subprocess.Popen(
                self.server_command,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                text=True,
                encoding="utf-8",
            )
        except Exception as exc:  # noqa: BLE001 —— FileNotFoundError/OSError 统一包装
            raise MCPConnectionError(f"failed to spawn mcp server {self.server_command}: {exc}") from exc
        self._reader = threading.Thread(target=self._read_loop, daemon=True, name="mcp-client-reader")
        self._reader.start()
        try:
            result = self._request(
                "initialize",
                {
                    "protocolVersion": PROTOCOL_VERSION,
                    "capabilities": {},
                    "clientInfo": {"name": CLIENT_NAME, "version": CLIENT_VERSION},
                },
            )
        except MCPError:
            self.close()
            raise
        if not result.get("protocolVersion"):
            self.close()
            raise MCPConnectionError("mcp initialize handshake failed: missing protocolVersion")
        self._send({"jsonrpc": "2.0", "method": "notifications/initialized", "params": {}})

    def list_tools(self) -> list[dict]:
        """发现 Server 工具列表（函数）。

        参数：
            无。

        返回值：
            list[dict]：工具描述列表（name/description/inputSchema），无工具返回 []。

        异常：
            MCPError 子类：连接/超时/协议错误。
        """
        result = self._request("tools/list", {})
        tools = result.get("tools")
        return [t for t in tools if isinstance(t, dict)] if isinstance(tools, list) else []

    def call_tool(self, name: str, arguments: dict) -> dict:
        """调用 Server 工具（函数）。

        说明：
            结果级错误（isError=true）按文案映射：含 "permission"（不区分大小写）
            → MCPPermissionError，否则 MCPUnavailableError；成功返回完整结果
            （含 content / isError 字段）。

        参数：
            name：工具名（须为 Server 白名单内工具）。
            arguments：工具参数字典。

        返回值：
            dict：{"content": [...], "isError": False, ...}。

        异常：
            MCPPermissionError / MCPUnavailableError / MCPConnectionError /
            MCPTimeoutError / MCPInvalidParams。
        """
        result = self._request("tools/call", {"name": name, "arguments": arguments})
        if result.get("isError"):
            text = ""
            for item in result.get("content") or []:
                if isinstance(item, dict) and item.get("type") == "text":
                    text = str(item.get("text") or "")
                    break
            if "permission" in text.lower():
                raise MCPPermissionError(text or "permission denied by mcp server")
            raise MCPUnavailableError(text or "mcp tool execution failed")
        return result

    def close(self) -> None:
        """关闭客户端并回收子进程（函数）。

        说明：
            顺序：关 stdin（EOF → Server 优雅退出）→ wait 3s → 仍存活则
            terminate → 再 wait 3s → 仍存活则 kill；幂等（可重复调用）。

        参数：
            无。

        返回值：
            None。

        异常：
            不抛出（回收失败仅记录日志）。
        """
        proc = self._proc
        if proc is None:
            return
        try:
            if proc.stdin is not None and not proc.stdin.closed:
                proc.stdin.close()  # EOF：Server 侧正常退出（退出码 0）
        except Exception as exc:  # noqa: BLE001
            logger.warning("mcp client close stdin failed: %s", exc)
        try:
            if proc.poll() is None:
                try:
                    proc.wait(timeout=_CLOSE_WAIT_SECONDS)
                except subprocess.TimeoutExpired:
                    proc.terminate()
                    try:
                        proc.wait(timeout=_CLOSE_WAIT_SECONDS)
                    except subprocess.TimeoutExpired:
                        proc.kill()
        except Exception as exc:  # noqa: BLE001
            logger.warning("mcp client close process failed: %s", exc)
        self._proc = None


__all__ = [
    "MCPClient",
    "MCPConnectionError",
    "MCPError",
    "MCPInvalidParams",
    "MCPPermissionError",
    "MCPTimeoutError",
    "MCPUnavailableError",
]
