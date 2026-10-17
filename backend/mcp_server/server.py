"""stdio MCP Server 最小实现（JSON-RPC 2.0 over stdio，阶段二）。

职责：
    以「一行一消息」协议在 stdin/stdout 上提供 MCP（Model Context Protocol）
    只读工具服务，供 MCPClient（app.ability.mcp_client）或任意标准 MCP 客户端
    以子进程方式拉起：

    - initialize：返回 protocolVersion="2024-11-05" 与 serverInfo；
    - notifications/initialized：通知，不回复；
    - tools/list：返回 recipe_search / recipe_detail 两个只读工具
      （JSON Schema 取自 app.ability.tools 对应实例的 parameters_schema()）；
    - tools/call：白名单校验（非白名单工具名 → 结果 isError=true + "permission
      denied" 文案——选用结果级错误而非协议级 -32602，与 MCP 规范中「工具执行
      失败用 isError 表达」的口径一致）；随后转发 execute_tool 执行；
    - ping：返回空对象结果；
    - 未知方法：协议级错误 -32601；参数不合法：-32602；内部错误：-32603；
      请求行非法 JSON：-32700（parse error）。
    - stdin EOF：进程以退出码 0 正常结束。

健壮性：
    DB 不可用时 tools/call 返回 isError=true 的结构化文本消息，进程不崩溃；
    AICOOK_MCP_STUB=1 时进入 stub 模式（不导入 app 模块、不连 DB，返回固定
    演示数据），供测试与前端联调使用。

运行：
    Set-Location backend && .venv\\Scripts\\python.exe -m mcp_server
"""

from __future__ import annotations

import json
import os
import sys
from typing import Any, NoReturn

# stub 模式开关（须在导入 app.* 之前读取：stub 模式完全不触碰应用与 DB）
_STUB_MODE = os.environ.get("AICOOK_MCP_STUB") == "1"

if not _STUB_MODE:
    # 真实模式才导入应用模块（含 SQLAlchemy / 配置单例；stub 模式零依赖）
    from app.ability.tools import (
        RecipeDetailTool,
        RecipeSearchTool,
        ToolContext,
        execute_tool,
    )
    from app.core.logging import get_logger

    _logger = get_logger("mcp_server")
else:
    _logger = None

# ---------------------------------------------------------------------------
# 协议常量（JSON-RPC 2.0 / MCP 2024-11-05）
# ---------------------------------------------------------------------------
PROTOCOL_VERSION = "2024-11-05"
SERVER_NAME = "aicook-readonly-mcp"
SERVER_VERSION = "1.0.0"

# JSON-RPC 标准错误码
ERR_PARSE = -32700        # 请求行非法 JSON
ERR_METHOD_NOT_FOUND = -32601
ERR_INVALID_PARAMS = -32602
ERR_INTERNAL = -32603

# 工具白名单（只读工具名集合；tools/call 仅放行集合内工具）
_TOOL_WHITELIST: frozenset[str] = frozenset({"recipe_search", "recipe_detail"})

# 工具实例（真实模式懒加载；stub 模式为 None）
_tools: dict[str, Any] | None = None


def _get_tools() -> dict[str, Any]:
    """获取白名单工具实例映射（懒加载，函数）。

    说明：
        首次调用时实例化 RecipeSearchTool / RecipeDetailTool（真实模式）；
        stub 模式返回空映射（tools/list 由固定演示定义承担）。

    参数：
        无。

    返回值：
        dict[str, Any]：{工具名: AgentTool 实例}。

    异常：
        无。
    """
    global _tools
    if _tools is None:
        _tools = {"recipe_search": RecipeSearchTool(), "recipe_detail": RecipeDetailTool()}
    return _tools


def _stub_tool_defs() -> list[dict]:
    """返回 stub 模式的固定工具定义（函数）。

    返回值：
        list[dict]：两个只读工具的 MCP 工具描述（name/description/inputSchema）。

    异常：
        无。
    """
    return [
        {
            "name": "recipe_search",
            "description": "（stub）按自然语言查询文本检索菜谱候选列表。",
            "inputSchema": {
                "type": "object",
                "properties": {"query": {"type": "string"}, "top_k": {"type": "integer", "default": 5}},
                "required": ["query"],
            },
        },
        {
            "name": "recipe_detail",
            "description": "（stub）按菜谱 ID 查询详情。",
            "inputSchema": {"type": "object", "properties": {"recipe_id": {"type": "integer"}}, "required": ["recipe_id"]},
        },
    ]


def _write_message(message: dict) -> None:
    """向 stdout 写一行 JSON-RPC 消息并立即刷出（函数）。

    参数：
        message：JSON-RPC 请求/响应/通知字典。

    返回值：
        None。

    异常：
        BrokenPipeError/OSError：stdout 关闭（客户端退出）时向上抛出，由主循环结束进程。
    """
    sys.stdout.write(json.dumps(message, ensure_ascii=False, default=str) + "\n")
    sys.stdout.flush()


def _reply_result(request_id: Any, result: dict) -> None:
    """回写成功响应（函数）。

    参数：
        request_id：请求 id（原样回填）。
        result：结果字典。

    返回值：
        None。

    异常：
        同 _write_message。
    """
    _write_message({"jsonrpc": "2.0", "id": request_id, "result": result})


def _reply_error(request_id: Any, code: int, message: str) -> None:
    """回写协议级错误响应（函数）。

    参数：
        request_id：请求 id（原样回填；解析失败无 id 时为 None）。
        code：JSON-RPC 错误码（-32601/-32602/-32603/-32700）。
        message：错误描述。

    返回值：
        None。

    异常：
        同 _write_message。
    """
    _write_message({"jsonrpc": "2.0", "id": request_id, "error": {"code": code, "message": message}})


def _tool_text_payload(data: Any, is_error: bool) -> dict:
    """把工具执行数据包装为 MCP tools/call 结果（函数）。

    说明：
        统一结构：content 为单条 text（结果 JSON 序列化，ensure_ascii=False），
        isError 标记执行失败（协议层仍是成功响应）。

    参数：
        data：工具结果数据（ToolResult.result / 错误描述）。
        is_error：是否执行失败。

    返回值：
        dict：{"content": [{"type": "text", "text": ...}], "isError": bool}。

    异常：
        无（序列化失败退化为 str(data)）。
    """
    try:
        text = json.dumps(data, ensure_ascii=False, default=str)
    except Exception:  # noqa: BLE001 —— 不可序列化数据退化为字符串
        text = str(data)
    return {"content": [{"type": "text", "text": text}], "isError": is_error}


def _handle_tools_call(request_id: Any, params: dict) -> None:
    """处理 tools/call 请求（白名单校验 + 执行转发，函数）。

    说明：
        白名单外工具名 → 结果级错误（isError=true + "permission denied" 文案）；
        白名单内 → execute_tool（校验/超时/重试/缓存/审计复用 tools.py），
        任何执行失败（含 DB 不可用）都转 isError=true 结构化消息，进程不崩溃。
        stub 模式返回固定演示数据（不连 DB）。

    参数：
        request_id：请求 id。
        params：{"name": 工具名, "arguments": 参数字典}。

    返回值：
        None（响应直接写 stdout）。

    异常：
        无（全部失败路径转结构化结果）。
    """
    name = str(params.get("name") or "")
    arguments = params.get("arguments")
    if not isinstance(arguments, dict):
        arguments = {}
    # 白名单校验：非只读白名单工具一律拒绝（结果级 permission denied）
    if name not in _TOOL_WHITELIST:
        if _logger:
            _logger.warning("mcp tools/call denied (tool=%s)", name)
        _reply_result(request_id, _tool_text_payload({"error": f"permission denied: tool '{name}' is not allowed"}, True))
        return
    if _STUB_MODE:
        # stub 模式：固定演示数据（测试/联调用，绝不触 DB）
        demo = {"recipe_search": {"results": [{"recipe_id": 1, "title": "番茄炒蛋（stub）"}], "count": 1}}
        payload = demo.get(name, {"found": True, "recipe": {"recipe_id": arguments.get("recipe_id"), "title": "番茄炒蛋（stub）"}})
        _reply_result(request_id, _tool_text_payload(payload, False))
        return
    tool = _get_tools().get(name)
    if tool is None:
        _reply_result(request_id, _tool_text_payload({"error": f"unknown tool '{name}'"}, True))
        return
    # 转发统一执行框架（不抛异常；DB 不可用 → error_code=unavailable）
    result = execute_tool(tool, arguments, ToolContext(user_id=None, request_id=str(request_id), max_timeout_seconds=10.0))
    if result.status != "ok":
        if _logger:
            _logger.warning("mcp tools/call failed (tool=%s code=%s)", name, result.error_code)
        _reply_result(
            request_id,
            _tool_text_payload({"error": result.error_code, "message": result.message}, True),
        )
        return
    _reply_result(request_id, _tool_text_payload(result.result, False))


def _handle_request(message: dict) -> None:
    """分发单条 JSON-RPC 消息（函数）。

    说明：
        仅处理 initialize / notifications/initialized / ping / tools/list /
        tools/call；带 id 的未知方法回 -32601，通知（无 id）静默丢弃；
        其余异常转 -32603 内部错误（服务进程绝不因单条消息崩溃）。

    参数：
        message：已解析的 JSON-RPC 消息字典。

    返回值：
        None。

    异常：
        无（内部错误全部转 -32603 响应）。
    """
    method = str(message.get("method") or "")
    request_id = message.get("id")
    is_notification = request_id is None
    params = message.get("params")
    if not isinstance(params, dict):
        params = {}
    try:
        if method == "initialize":
            _reply_result(
                request_id,
                {
                    "protocolVersion": PROTOCOL_VERSION,
                    "capabilities": {"tools": {}},
                    "serverInfo": {"name": SERVER_NAME, "version": SERVER_VERSION},
                },
            )
            return
        if method == "notifications/initialized":
            return  # 通知不回复
        if method == "ping":
            _reply_result(request_id, {})
            return
        if method == "tools/list":
            if _STUB_MODE:
                _reply_result(request_id, {"tools": _stub_tool_defs()})
                return
            defs = [
                {
                    "name": tool.name,
                    "description": tool.description,
                    "inputSchema": tool.parameters_schema(),
                }
                for tool in _get_tools().values()
            ]
            _reply_result(request_id, {"tools": defs})
            return
        if method == "tools/call":
            _handle_tools_call(request_id, params)
            return
        # 未知方法：通知静默丢弃，请求回 -32601
        if not is_notification:
            _reply_error(request_id, ERR_METHOD_NOT_FOUND, f"method not found: {method}")
    except Exception as exc:  # noqa: BLE001 —— 单条消息内部错误不终止服务进程
        if _logger:
            _logger.error("mcp internal error (method=%s): %s", method, exc)
        if not is_notification:
            _reply_error(request_id, ERR_INTERNAL, f"internal error: {exc}")


def main() -> NoReturn:
    """MCP Server 主入口：逐行读 stdin、分发、EOF 以退出码 0 结束（函数）。

    说明：
        日志只走 stderr（logging 由 app.core.logging 配置，stdout 专用协议通道）；
        每行一个 JSON-RPC 消息，空行跳过，非法 JSON 回 -32700 后继续服务；
        stdin EOF（客户端 close/退出）时进程正常结束（退出码 0）。

    参数：
        无。

    返回值：
        NoReturn：进程结束（sys.exit(0)）。

    异常：
        BrokenPipeError/OSError：stdout 写失败（客户端已死）时结束进程（退出码 0）。
    """
    if _logger:
        _logger.info("mcp_server started (stub=%s)", _STUB_MODE)
    for raw_line in sys.stdin:
        line = raw_line.strip()
        if not line:
            continue
        try:
            message = json.loads(line)
            if not isinstance(message, dict):
                raise ValueError("message must be a JSON object")
        except Exception as exc:  # noqa: BLE001 —— 非法 JSON 回 parse error 后继续
            if _logger:
                _logger.warning("mcp parse error: %s", exc)
            _reply_error(None, ERR_PARSE, f"parse error: {exc}")
            continue
        try:
            _handle_request(message)
        except (BrokenPipeError, OSError):
            # stdout 已关闭（客户端退出）：正常结束
            break
    if _logger:
        _logger.info("mcp_server exited (stdin EOF)")
    sys.exit(0)


if __name__ == "__main__":
    main()
