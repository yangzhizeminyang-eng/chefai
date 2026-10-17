"""MCP stub Server（测试专用，stdio JSON-RPC 2.0）。

职责：
    供 tests/test_mcp_client.py 以子进程方式拉起，覆盖客户端全部行为分支。
    场景由命令行第一个参数控制（缺省 normal）：

    - normal：正常握手 / tools/list 返回 2 工具 / tools/call 成功回显；
    - slow：tools/call 休眠 30s（触发客户端超时）；
    - bad_params：tools/call 一律回协议级错误 -32602；
    - permission：tools/call 回结果级错误（isError=true + permission denied 文案）；
    - 所有场景共用：ping → {}；未知方法 → -32601；stdin EOF → 退出码 0。

用法：
    python stub_mcp_server.py [normal|slow|bad_params|permission]
"""

from __future__ import annotations

import json
import sys
import time

# JSON-RPC 标准错误码
ERR_METHOD_NOT_FOUND = -32601
ERR_INVALID_PARAMS = -32602

# tools/list 固定返回的 2 个只读工具定义
_TOOLS = [
    {
        "name": "stub_echo",
        "description": "回显工具（测试用）",
        "inputSchema": {"type": "object", "properties": {"q": {"type": "string"}}, "required": ["q"]},
    },
    {
        "name": "stub_meta",
        "description": "元信息工具（测试用，无参数）",
        "inputSchema": {"type": "object", "properties": {}, "required": []},
    },
]


def _write(message: dict) -> None:
    """向 stdout 写一行 JSON 并立即刷出（函数）。

    参数：
        message：JSON-RPC 响应/通知字典。

    返回值：
        None。

    异常：
        BrokenPipeError/OSError：客户端退出时向上抛出（结束主循环）。
    """
    sys.stdout.write(json.dumps(message, ensure_ascii=False) + "\n")
    sys.stdout.flush()


def _result(request_id, result: dict) -> None:
    """回写成功响应（函数）。

    参数：
        request_id：请求 id。
        result：结果字典。

    返回值：
        None。

    异常：
        同 _write。
    """
    _write({"jsonrpc": "2.0", "id": request_id, "result": result})


def _error(request_id, code: int, message: str) -> None:
    """回写协议级错误响应（函数）。

    参数：
        request_id：请求 id。
        code：JSON-RPC 错误码。
        message：错误描述。

    返回值：
        None。

    异常：
        同 _write。
    """
    _write({"jsonrpc": "2.0", "id": request_id, "error": {"code": code, "message": message}})


def main() -> None:
    """stub server 主循环（函数）。

    说明：
        逐行读 stdin、按场景分发、EOF 正常退出（退出码 0）；日志走 stderr
        不污染协议通道（本 stub 不打日志）。

    参数：
        无。

    返回值：
        None（stdin EOF 时 return，进程退出码 0）。

    异常：
        BrokenPipeError/OSError：客户端已死时正常结束。
    """
    scenario = sys.argv[1] if len(sys.argv) > 1 else "normal"
    for raw_line in sys.stdin:
        line = raw_line.strip()
        if not line:
            continue
        try:
            message = json.loads(line)
        except Exception:  # noqa: BLE001 —— 非法行静默丢弃
            continue
        if not isinstance(message, dict):
            continue
        method = str(message.get("method") or "")
        request_id = message.get("id")
        params = message.get("params")
        if not isinstance(params, dict):
            params = {}
        try:
            if method == "initialize":
                _result(
                    request_id,
                    {
                        "protocolVersion": "2024-11-05",
                        "capabilities": {"tools": {}},
                        "serverInfo": {"name": "stub-mcp", "version": "1.0.0"},
                    },
                )
            elif method == "notifications/initialized":
                continue  # 通知不回复
            elif method == "ping":
                _result(request_id, {})
            elif method == "tools/list":
                _result(request_id, {"tools": _TOOLS})
            elif method == "tools/call":
                name = str(params.get("name") or "")
                arguments = params.get("arguments") or {}
                if scenario == "bad_params":
                    _error(request_id, ERR_INVALID_PARAMS, f"invalid params for tool '{name}'")
                elif scenario == "permission":
                    _result(
                        request_id,
                        {
                            "content": [{"type": "text", "text": f"permission denied: tool '{name}'"}],
                            "isError": True,
                        },
                    )
                elif scenario == "slow":
                    time.sleep(30)  # 远超客户端超时预算（测试断言 MCPTimeoutError 后 terminate）
                    _result(request_id, {"content": [{"type": "text", "text": "{}"}], "isError": False})
                else:  # normal：成功回显
                    _result(
                        request_id,
                        {
                            "content": [{"type": "text", "text": json.dumps({"echo": arguments}, ensure_ascii=False)}],
                            "isError": False,
                        },
                    )
            else:
                # 未知方法：通知静默丢弃，请求回 -32601
                if request_id is not None:
                    _error(request_id, ERR_METHOD_NOT_FOUND, f"method not found: {method}")
        except (BrokenPipeError, OSError):
            return
    # stdin EOF → 正常退出（退出码 0）


if __name__ == "__main__":
    main()
