"""烹饪求助子智能体测试。

覆盖：
    - _extract_answer_array：合法数组 / 围栏杂字 / 非法输出 None / 条目截断；
    - generate_cooking_help：LLM 正常返回 / LLM 失败抛 LLMError / 空问题抛 LLMError。
"""

from __future__ import annotations

import pytest

from app.ability import cooking_help_agent
from app.ability.cooking_help_agent import generate_cooking_help
from app.ability.llm import LLMError, LLMResult


class _StubLLMClient:
    """桩 LLM 客户端（测试用）：返回预设 content（模型类）。"""

    def __init__(self, content: str) -> None:
        self._content = content

    def chat(self, system: str, user: str, temperature: float = 0.2) -> LLMResult:  # noqa: ARG002
        return LLMResult(content=self._content, prompt_tokens=0, completion_tokens=0, model="stub")


class _BoomLLMClient:
    """恒抛异常的桩 LLM 客户端（测试用）。"""

    def chat(self, system: str, user: str, temperature: float = 0.2) -> LLMResult:  # noqa: ARG002
        raise LLMError("llm boom")


def test_extract_answer_array_valid() -> None:
    """合法数组（含围栏杂字）正确提取（函数）。"""
    raw = '回答如下：["转中小火加盖焖5分钟","补小半碗热水防糊锅","土豆筷子能扎透即软"] 完毕。'
    answers = cooking_help_agent._extract_answer_array(raw)
    assert answers is not None
    assert len(answers) == 3
    assert answers[0] == "转中小火加盖焖5分钟"


def test_extract_answer_array_invalid() -> None:
    """无数组 / 非法 JSON / 空条目返回 None（函数）。"""
    assert cooking_help_agent._extract_answer_array("我建议你加水") is None
    assert cooking_help_agent._extract_answer_array('["","  "]') is None
    assert cooking_help_agent._extract_answer_array('{"a":1}') is None


def test_generate_cooking_help_ok(monkeypatch: pytest.MonkeyPatch) -> None:
    """LLM 正常返回结构化建议（函数）。"""
    monkeypatch.setattr(
        cooking_help_agent,
        "get_llm_client",
        lambda: _StubLLMClient('["转中小火加盖焖5分钟","补小半碗热水"]'),
    )
    answers = generate_cooking_help("火太大了怎么办", {"recipe_title": "西红柿土豆炖牛肉", "current_step_text": "加盖熬煮至土豆变软"})
    assert answers == ["转中小火加盖焖5分钟", "补小半碗热水"]


def test_generate_cooking_help_llm_error(monkeypatch: pytest.MonkeyPatch) -> None:
    """LLM 失败 / 输出非法 / 空问题抛 LLMError（函数）。"""
    monkeypatch.setattr(cooking_help_agent, "get_llm_client", lambda: _BoomLLMClient())
    with pytest.raises(LLMError):
        generate_cooking_help("火太大", {})
    monkeypatch.setattr(
        cooking_help_agent,
        "get_llm_client",
        lambda: _StubLLMClient("我说不清楚"),
    )
    with pytest.raises(LLMError):
        generate_cooking_help("火太大", {})
    with pytest.raises(LLMError):
        generate_cooking_help("  ", {})
