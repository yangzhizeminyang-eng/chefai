"""tool_loop 节点单测（LLM 决策序列 × stub 工具，全部离线确定性）。

覆盖：
    ① LLM「选工具 → done」正常收敛：tool_results 恰 1 条、不触限；
    ② LLM 永不 done → 3 轮触限：tool_loop_limit_hit=True、tool_results 3 条；
    ③ LLM 输出解析失败 → 立即 done：tool_results 空、不触限。

隔离手段：
    monkeypatch app.graph.nodes.tool_loop._BUILTIN_TOOLS（注入 stub 工具，不触 DB）；
    monkeypatch app.graph.nodes.tool_loop.get_llm_client（预设 JSON 响应序列）。
"""

from __future__ import annotations

import pytest

from app.ability.llm import LLMResult
from app.ability.tools import AgentTool, ToolContext, clear_tool_cache
from app.graph.nodes import tool_loop as tool_loop_mod


class StubEchoTool(AgentTool):
    """回声 stub 工具（模型类）：原样返回参数，验证 tool_results 摘要链路。

    属性：
        name：stub_echo。
        description：测试用回声工具。
        read_only：True。
    """

    name = "stub_echo"
    description = "测试用回声工具"
    read_only = True

    def parameters_schema(self) -> dict:
        """返回参数 Schema（函数）。

        返回值：
            dict：{"q": 必填字符串}。

        异常：
            无。
        """
        return {"type": "object", "properties": {"q": {"type": "string"}}, "required": ["q"]}

    def execute(self, params: dict, ctx: ToolContext) -> dict:
        """执行回声（函数）。

        参数：
            params：{"q": 任意字符串}。
            ctx：执行上下文（未使用）。

        返回值：
            dict：{"echo": q}。

        异常：
            无。
        """
        return {"echo": params.get("q")}


class SequenceLLM:
    """预设 JSON 响应序列的 stub LLM 客户端（模型类）。

    说明：
        chat() 依次返回预设文本；序列耗尽时返回 '{"done": true}'（防越界）。

    属性：
        calls：chat 调用次数（断言轮次）。
    """

    def __init__(self, responses: list[str]) -> None:
        """构造（函数）。

        参数：
            responses：预设响应文本序列。

        返回值：
            None。

        异常：
            无。
        """
        self._responses = list(responses)
        self.calls = 0

    def chat(self, system: str, user: str, temperature: float = 0.2) -> LLMResult:
        """返回下一条预设响应（函数）。

        参数：
            system：系统提示词（未使用）。
            user：用户消息（未使用）。
            temperature：采样温度（未使用）。

        返回值：
            LLMResult：content 为预设文本的伪结果。

        异常：
            无。
        """
        self.calls += 1
        content = self._responses.pop(0) if self._responses else '{"done": true}'
        return LLMResult(content=content, prompt_tokens=1, completion_tokens=1, model="stub-llm")


@pytest.fixture(autouse=True)
def _stub_env(monkeypatch: pytest.MonkeyPatch):
    """注入 stub 工具并清空幂等缓存（fixture）。

    参数：
        monkeypatch：pytest 打桩器。

    异常：
        无。
    """
    clear_tool_cache()
    monkeypatch.setattr(tool_loop_mod, "_BUILTIN_TOOLS", [StubEchoTool()])
    yield
    clear_tool_cache()


def _run_node(monkeypatch: pytest.MonkeyPatch, responses: list[str]) -> dict:
    """以预设 LLM 响应序列运行 tool_loop 节点（函数）。

    参数：
        monkeypatch：pytest 打桩器。
        responses：预设 LLM 响应文本序列。

    返回值：
        dict：节点返回的 state 更新。

    异常：
        无。
    """
    llm = SequenceLLM(responses)
    monkeypatch.setattr(tool_loop_mod, "get_llm_client", lambda: llm)
    node = tool_loop_mod.make_tool_loop_node()
    return node({"request_id": "t_tool_loop", "input_text": "帮我找番茄菜谱"})


class TestToolLoopNode:
    """tool_loop 节点行为（测试类）。"""

    def test_select_tool_then_done_converges(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """①选工具 → done：1 条结果、状态 ok、不触限、span 可见（函数）。

        异常：
            断言失败即测试失败。
        """
        out = _run_node(monkeypatch, ['{"tool": "stub_echo", "params": {"q": "番茄"}}', '{"done": true}'])
        assert len(out["tool_results"]) == 1
        entry = out["tool_results"][0]
        assert entry["tool"] == "stub_echo"
        assert entry["status"] == "ok"
        assert '"echo": "番茄"' in entry["summary"] or '"echo":"番茄"' in entry["summary"]
        assert "tool_loop_limit_hit" not in out
        assert out["trace"], "收敛轮也应产出 span"
        assert all(span["node_name"] == "tool_loop" for span in out["trace"])

    def test_never_done_hits_round_limit(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """②永不 done → 3 轮触限：tool_loop_limit_hit=True 且 3 条结果（函数）。

        异常：
            断言失败即测试失败。
        """
        pick = '{"tool": "stub_echo", "params": {"q": "循环"}}'
        out = _run_node(monkeypatch, [pick, pick, pick])
        assert len(out["tool_results"]) == tool_loop_mod.MAX_TOOL_ROUNDS == 3
        assert out["tool_loop_limit_hit"] is True

    def test_parse_failure_converges_immediately(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """③解析失败 → 立即 done：结果为空、不触限（函数）。

        异常：
            断言失败即测试失败。
        """
        out = _run_node(monkeypatch, ["这不是 JSON 输出"])
        assert out["tool_results"] == []
        assert "tool_loop_limit_hit" not in out
        assert out["trace"], "解析失败轮也应产出 span"

    def test_llm_failure_degrades_without_exception(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """补充：LLM 抛异常 → 节点降级收敛不抛出（函数）。

        异常：
            断言失败即测试失败。
        """

        def _boom():
            raise RuntimeError("llm down")

        monkeypatch.setattr(tool_loop_mod, "get_llm_client", _boom)
        node = tool_loop_mod.make_tool_loop_node()
        out = node({"request_id": "t_tool_loop", "input_text": "x"})
        assert out["tool_results"] == []
        assert "tool_loop_limit_hit" not in out

    def test_unknown_tool_treated_as_invalid_decision(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """补充：LLM 选择了不存在的工具 → 视为解析失败立即收敛（函数）。

        异常：
            断言失败即测试失败。
        """
        out = _run_node(monkeypatch, ['{"tool": "no_such_tool", "params": {}}'])
        assert out["tool_results"] == []
        assert "tool_loop_limit_hit" not in out
