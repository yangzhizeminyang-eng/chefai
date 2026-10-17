"""aicook 只读 MCP Server 包（阶段二）。

说明：
    提供 stdio JSON-RPC 2.0 最小 MCP Server 实现（`python -m mcp_server` 可跑），
    对外暴露 recipe_search / recipe_detail 两个只读工具；日志只走 stderr，
    stdout 专用于 JSON-RPC 消息（一行一条）。
"""

from mcp_server.server import main

__all__ = ["main"]
