"""工具循环节点模块（阶段二：MCP Server/Client 接入 + LangGraph 工具节点）。

职责：
    tool_loop_node：qa 意图路径的前置工具节点——LLM 按可用工具列表（内置 4 个
    只读工具 + MCP_ENABLED='on' 时的 MCP 只读工具）选择 {tool, params} 或
    {done: true}，执行经 execute_tool（tools.py 统一框架：校验/超时/重试/
    幂等缓存/审计），结果摘要追加进 state.tool_results；最终回答仍由
    node_free_qa 生成并走出口闸门（工具结果只作回答素材，不绕过风控）。

预算与触限：
    MAX_TOOL_ROUNDS=3（轮数上限）、TOOL_LOOP_BUDGET_SECONDS=25.0（总耗时
    预算）；达轮数上限或超预算 → tool_loop_limit_hit=True 并立即返回。
    LLM 失败/输出解析失败/选择了未知工具 → 视为 done（正常收敛，不触限），
    绝不向编排层抛异常（节点级降级：无工具结果时行为等同无该节点）。

MCP 适配：
    MCPAgentTool 把 MCPClient 的工具包装为 AgentTool（parameters_schema 取
    tools/list 的 inputSchema，execute 走 call_tool）；MCP 连接失败 → 构建
    阶段静默降级（无 MCP 工具）；MCP 工具执行返回 unavailable/timeout/
    permission_denied → 该工具从本轮可用列表剔除（降级不阻断）。
"""

from __future__ import annotations

import json
import shlex
import time

from app.ability import get_llm_client
from app.ability.mcp_client import (
    MCPClient,
    MCPError,
    MCPInvalidParams,
    MCPPermissionError,
    MCPTimeoutError,
)
from app.ability.tools import (
    AgentTool,
    InventoryQueryTool,
    NutritionEstimateTool,
    RecipeDetailTool,
    RecipeSearchTool,
    ToolContext,
    ToolError,
    ToolResult,
    execute_tool,
)
from app.core.config import settings
from app.core.logging import get_logger
from app.graph.nodes.common import make_span
from app.graph.registry import register

logger = get_logger(__name__)

# 工具循环轮数上限（触限置 tool_loop_limit_hit=True）
MAX_TOOL_ROUNDS = 3

# 工具循环总耗时预算（秒；超预算立即返回并置触限标记）
TOOL_LOOP_BUDGET_SECONDS = 25.0

# 单次工具执行超时上限（秒；按剩余预算收紧，但不低于该保底值）
_PER_CALL_TIMEOUT_MAX = 10.0
_PER_CALL_TIMEOUT_MIN = 0.5

# 工具结果摘要截断长度（对齐 tools.py params_summary 口径，防 state/trace 刷屏）
_RESULT_SUMMARY_MAX_CHARS = 200

# MCP 工具剔除的错误码集合（连接类失败：降级剔除，后续轮次不再选择）
_MCP_DROP_CODES: frozenset[str] = frozenset({"unavailable", "timeout", "permission_denied"})

# 内置只读工具单例（测试经 monkeypatch 替换本列表注入 stub 工具）
_BUILTIN_TOOLS: list[AgentTool] = [
    RecipeSearchTool(),
    RecipeDetailTool(),
    NutritionEstimateTool(),
    InventoryQueryTool(),
]

# LLM 工具选择系统提示（严格 JSON 输出约束；{tool_lines} 注入工具清单）
TOOL_SELECT_SYSTEM_PROMPT = (
    "你是烹饪助手的工具调度器，负责决定是否调用工具获取事实数据。\n"
    "可用工具（名称 | 用途 | 参数Schema）：\n{tool_lines}\n"
    "只输出一个 JSON 对象，禁止输出任何解释或其他文本：\n"
    '需要调用工具时：{{"tool": "<工具名>", "params": {{...}}}}\n'
    '不需要工具或已有足够信息时：{{"done": true}}\n'
    "规则：工具名必须来自可用工具列表；params 必须符合该工具的参数 Schema；"
    "若已执行的工具结果足以回答，输出 done；不确定时输出 done。"
)


class MCPAgentTool(AgentTool):
    """MCP 工具的 Agent 适配器（模型类）。

    说明：
        把 MCPClient 发现的远程工具包装为 AgentTool：parameters_schema() 取
        tools/list 返回的 inputSchema（非 object 时回退空 Schema），execute()
        走 call_tool 并把 MCPError 族映射为 ToolError（code 对齐执行框架）：
        timeout → timeout / permission → permission_denied / 参数错 → invalid_params /
        连接与其余错误 → unavailable。read_only 恒为 True（只进只读白名单语义）。

    属性：
        name：MCP 工具名。
        description：MCP 工具描述。
        read_only：恒 True。
    """

    def __init__(self, mcp_client: MCPClient, tool_meta: dict) -> None:
        """构造适配器（函数）。

        参数：
            mcp_client：已握手的 MCP 客户端。
            tool_meta：tools/list 返回的单个工具描述（name/description/inputSchema）。

        返回值：
            None。

        异常：
            无。
        """
        self.name = str(tool_meta.get("name") or "")
        self.description = str(tool_meta.get("description") or f"MCP tool '{self.name}'")
        self.read_only = True
        self._client = mcp_client
        self._meta = tool_meta

    def parameters_schema(self) -> dict:
        """返回工具参数 Schema（函数）。

        返回值：
            dict：tools/list 的 inputSchema（type=object）；缺失/不规范回退空对象 Schema。

        异常：
            无。
        """
        schema = self._meta.get("inputSchema")
        if isinstance(schema, dict) and schema.get("type") == "object":
            return schema
        return {"type": "object", "properties": {}, "required": []}

    def execute(self, params: dict, ctx: ToolContext) -> dict:
        """执行 MCP 工具调用（函数）。

        参数：
            params：已通过 Schema 校验的参数字典。
            ctx：执行上下文（MCP 侧不消费 user_id，接口一致性保留）。

        返回值：
            dict：{"content": 服务端 content 列表, "text": 首个 text 文案}。

        异常：
            ToolError：code ∈ timeout/permission_denied/invalid_params/unavailable（MCPError 族映射）。
        """
        try:
            result = self._client.call_tool(self.name, params)
        except MCPTimeoutError as exc:
            raise ToolError("timeout", str(exc)) from exc
        except MCPPermissionError as exc:
            raise ToolError("permission_denied", str(exc)) from exc
        except MCPInvalidParams as exc:
            raise ToolError("invalid_params", str(exc)) from exc
        except MCPError as exc:  # 连接失败与其余不可用错误统一 unavailable
            raise ToolError("unavailable", str(exc)) from exc
        text = ""
        for item in result.get("content") or []:
            if isinstance(item, dict) and item.get("type") == "text":
                text = str(item.get("text") or "")
                break
        return {"content": result.get("content") or [], "text": text}


# ---------------------------------------------------------------------------
# 工具清单构建（内置 + MCP 可选，全部失败静默降级）
# ---------------------------------------------------------------------------
def _parse_server_command(raw: str) -> list[str]:
    """解析 MCP Server 启动命令（函数）。

    说明：
        优先按 JSON 数组字符串解析（推荐形式 '["python", "-m", "mcp_server"]'），
        失败退化为空格分割（shlex）。

    参数：
        raw：配置的命令字符串（settings.MCP_SERVER_COMMAND）。

    返回值：
        list[str]：argv 列表（解析失败返回空列表）。

    异常：
        无。
    """
    raw = (raw or "").strip()
    if not raw:
        return []
    try:
        parsed = json.loads(raw)
        if isinstance(parsed, list) and all(isinstance(p, str) for p in parsed) and parsed:
            return parsed
    except Exception:  # noqa: BLE001 —— 非 JSON 退化 shlex
        pass
    try:
        return shlex.split(raw)
    except Exception:  # noqa: BLE001
        return []


def _build_mcp_tools() -> tuple[list[AgentTool], MCPClient | None]:
    """按配置构建 MCP 工具列表（函数）。

    说明：
        MCP_ENABLED='on' 且配置了启动命令时：拉起 Server + 握手 + tools/list，
        每个远程工具包装为 MCPAgentTool；任何失败（未开启/命令空/连接失败）
        均静默降级为空列表（不阻断主链路）。

    参数：
        无。

    返回值：
        tuple[list[AgentTool], MCPClient | None]：工具列表与客户端
        （调用方负责在节点结束时 close；无 MCP 时为 ([], None)）。

    异常：
        不抛出（全部异常转降级空结果）。
    """
    if str(settings.MCP_ENABLED).lower() != "on":
        return [], None
    command = _parse_server_command(settings.MCP_SERVER_COMMAND)
    if not command:
        logger.warning("MCP_ENABLED=on but MCP_SERVER_COMMAND empty; skip mcp tools")
        return [], None
    try:
        client = MCPClient(command, timeout_seconds=10.0)
        client.connect()
        metas = client.list_tools()
    except Exception as exc:  # noqa: BLE001 —— MCP 不可用即降级，不阻断
        logger.warning("mcp unavailable, degrade without mcp tools: %s", exc)
        return [], None
    tools = [MCPAgentTool(client, meta) for meta in metas if str(meta.get("name") or "")]
    logger.info("mcp tools attached: %s", [t.name for t in tools])
    return tools, client


# ---------------------------------------------------------------------------
# LLM 决策（严格 JSON；解析失败返回 None → done）
# ---------------------------------------------------------------------------
def _build_tool_lines(tools: list[AgentTool]) -> str:
    """渲染工具清单文本（函数）。

    参数：
        tools：可用工具实例列表。

    返回值：
        str：每行「名称 | 用途 | 参数Schema JSON」的多行文本。

    异常：
        无。
    """
    lines = []
    for tool in tools:
        try:
            schema_text = json.dumps(tool.parameters_schema(), ensure_ascii=False)
        except Exception:  # noqa: BLE001
            schema_text = "{}"
        lines.append(f"- {tool.name} | {tool.description} | {schema_text}")
    return "\n".join(lines)


def _parse_decision(content: str) -> dict | None:
    """解析 LLM 工具决策 JSON（函数）。

    说明：
        提取首个 '{' 到最后一个 '}' 区间后 json.loads（容错前后缀文案）；
        解析失败/非对象返回 None（调用方视为 done）。

    参数：
        content：LLM 输出文本。

    返回值：
        dict | None：{"tool": ..., "params": ...} 或 {"done": true}；解析失败 None。

    异常：
        无。
    """
    if not content:
        return None
    start, end = content.find("{"), content.rfind("}")
    if start == -1 or end <= start:
        return None
    try:
        decision = json.loads(content[start : end + 1])
    except Exception:  # noqa: BLE001
        return None
    return decision if isinstance(decision, dict) else None


def _decide_with_llm(state: dict, tools: list[AgentTool], tool_results: list[dict]) -> dict | None:
    """调用 LLM 做工具决策（函数）。

    说明：
        user 消息 = 输入文本 + 已选食材 +（第二轮起）最近已执行工具结果摘要
        （供 LLM 判断 done）；LLM 失败向上抛 LLMError（调用方按 done 收敛）。

    参数：
        state：编排状态。
        tools：可用工具实例列表。
        tool_results：已执行工具结果摘要列表。

    返回值：
        dict | None：决策字典（解析失败 None）。

    异常：
        LLMError：LLM 调用失败（调用方降级）。
    """
    user = state.get("input_text") or "（用户未输入文本）"
    names = list(state.get("resolved_ingredient_names") or [])
    if names:
        user += "\n（用户已选食材：" + "、".join(str(n) for n in names) + "）"
    if tool_results:
        recent = "; ".join(f"{r.get('tool')}->{r.get('summary')}" for r in tool_results[-3:])
        user += "\n（已执行工具结果：" + recent + "）"
    client = get_llm_client()
    system = TOOL_SELECT_SYSTEM_PROMPT.format(tool_lines=_build_tool_lines(tools))
    result = client.chat(system, user, temperature=0.0)
    return _parse_decision(result.content)


# ---------------------------------------------------------------------------
# 结果摘要与 span
# ---------------------------------------------------------------------------
def _summarize_result(result: ToolResult) -> str:
    """生成工具结果摘要（截断，函数）。

    参数：
        result：execute_tool 结构化结果。

    返回值：
        str：成功为结果 JSON 截断；失败为「error:code:message」。

    异常：
        无。
    """
    if result.status == "ok":
        try:
            text = json.dumps(result.result, ensure_ascii=False, default=str)
        except Exception:  # noqa: BLE001
            text = str(result.result)
    else:
        text = f"error:{result.error_code}:{result.message}"
    if len(text) > _RESULT_SUMMARY_MAX_CHARS:
        text = text[:_RESULT_SUMMARY_MAX_CHARS] + "...(truncated)"
    return text


def _result_entry(result: ToolResult) -> dict:
    """构造 tool_results 列表条目（函数）。

    参数：
        result：execute_tool 结构化结果。

    返回值：
        dict：{tool/status/error_code/cached/attempts/elapsed_ms/summary}。

    异常：
        无。
    """
    return {
        "tool": result.tool_name,
        "status": result.status,
        "error_code": result.error_code,
        "cached": result.cached,
        "attempts": result.attempts,
        "elapsed_ms": result.elapsed_ms,
        "summary": _summarize_result(result),
    }


# ---------------------------------------------------------------------------
# 节点本体
# ---------------------------------------------------------------------------
def make_tool_loop_node():
    """工具循环节点工厂（函数）。

    返回值：
        Callable：节点函数（state → state 更新 dict）。

    异常：
        无。
    """

    def tool_loop_node(state: dict) -> dict:
        """工具循环节点（函数）。

        说明：
            流程：构建可用工具（内置 + MCP 可选，失败降级）→ 至多
            MAX_TOOL_ROUNDS 轮「LLM 决策 → execute_tool → 结果摘要入
            tool_results」→ LLM 输出 done/解析失败/工具失败/触限即停；
            每轮 make_span(node="tool_loop")；总耗时超 TOOL_LOOP_BUDGET_SECONDS
            或达轮数上限 → tool_loop_limit_hit=True。绝不向编排层抛异常。

        参数：
            state：编排状态（input_text/user_id/request_id 等）。

        返回值：
            dict：{"tool_results": 摘要列表（operator.add 累加）,
                   "tool_loop_limit_hit": True（仅触限时写入）,
                   "trace": [span, ...]}。

        异常：
            不抛出（全部异常转降级空结果 + 告警日志）。
        """
        start_s = time.perf_counter()
        deadline_s = start_s + TOOL_LOOP_BUDGET_SECONDS
        request_id = str(state.get("request_id") or "")
        raw_user_id = state.get("user_id")
        user_id = int(raw_user_id) if isinstance(raw_user_id, int) else None
        tool_results: list[dict] = []
        spans: list[dict] = []
        limit_hit = False

        mcp_client: MCPClient | None = None
        try:
            available = list(_BUILTIN_TOOLS)
            try:
                mcp_tools, mcp_client = _build_mcp_tools()
                available.extend(mcp_tools)
            except Exception as exc:  # noqa: BLE001 —— MCP 构建异常不阻断
                logger.warning("tool_loop build mcp tools failed: %s", exc)

            for _round_no in range(1, MAX_TOOL_ROUNDS + 1):
                round_start = time.perf_counter()
                remaining = deadline_s - round_start
                if remaining <= 0:
                    limit_hit = True
                    spans.append(make_span("tool_loop", "degraded", (time.perf_counter() - round_start) * 1000, rule_hit="budget_exhausted"))
                    break
                # 1) LLM 决策（失败/解析失败 → done 收敛）
                try:
                    decision = _decide_with_llm(state, available, tool_results)
                except Exception as exc:  # noqa: BLE001 —— LLMError 等一切失败收敛
                    logger.warning("tool_loop llm decision failed: %s", exc)
                    spans.append(make_span("tool_loop", "degraded", (time.perf_counter() - round_start) * 1000, rule_hit="llm_unavailable"))
                    break
                if not decision or decision.get("done"):
                    spans.append(make_span("tool_loop", "ok", (time.perf_counter() - round_start) * 1000, rule_hit="decision=done"))
                    break
                # 2) 决策合法性（未知工具/参数非 dict → 视为解析失败收敛）
                tool_name = str(decision.get("tool") or "")
                params = decision.get("params")
                tool = next((t for t in available if t.name == tool_name), None)
                if tool is None or not isinstance(params, dict):
                    spans.append(make_span("tool_loop", "ok", (time.perf_counter() - round_start) * 1000, rule_hit=f"decision=invalid:{tool_name}"))
                    break
                # 3) 执行（超时预算按剩余收紧；任何失败转结构化结果）
                per_call = max(_PER_CALL_TIMEOUT_MIN, min(_PER_CALL_TIMEOUT_MAX, deadline_s - time.perf_counter()))
                ctx = ToolContext(user_id=user_id, request_id=request_id, max_timeout_seconds=per_call)
                result = execute_tool(tool, params, ctx)
                tool_results.append(_result_entry(result))
                spans.append(
                    make_span(
                        "tool_loop",
                        "ok" if result.status == "ok" else "degraded",
                        result.elapsed_ms,
                        rule_hit=f"tool={result.tool_name};code={result.error_code or '-'};cached={result.cached}",
                    )
                )
                # 4) 连接类失败的 MCP 工具剔除（降级不阻断）
                if (
                    isinstance(tool, MCPAgentTool)
                    and result.status == "error"
                    and result.error_code in _MCP_DROP_CODES
                ):
                    available = [t for t in available if t is not tool]
                # 5) 工具失败即停（保守收敛，不算触限）
                if result.status != "ok":
                    break
            else:
                # 用尽 MAX_TOOL_ROUNDS 轮仍未 done → 触限
                limit_hit = True
        finally:
            if mcp_client is not None:
                mcp_client.close()

        if limit_hit:
            return {
                "tool_results": tool_results,
                "tool_loop_limit_hit": True,
                "trace": spans,
            }
        return {"tool_results": tool_results, "trace": spans}

    return tool_loop_node


# ---- 注册 ----
register(
    "tool_loop",
    make_tool_loop_node,
    forms="llm",
    timeout_ms=int(TOOL_LOOP_BUDGET_SECONDS * 1000),
    description="工具循环（LLM 决策 + 只读工具执行 + 结果摘要；MCP 可选挂载）",
)


__all__ = ["MCPAgentTool", "MAX_TOOL_ROUNDS", "TOOL_LOOP_BUDGET_SECONDS", "make_tool_loop_node"]
