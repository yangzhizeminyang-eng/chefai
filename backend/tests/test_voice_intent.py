"""语音意图理解测试（混合架构：白名单未命中时 LLM 兜底解析）。

覆盖：
    - _extract_intent_json：合法 JSON 提取 / 围栏杂字容错 / 非法输出返回 None /
      action 枚举校验归一 / minutes/step_no 类型归一；
    - POST /v1/speech/intent：LLM 正常返回结构化意图 / LLM 失败降级
      action=none + degraded=true / 空文本 422 / 开关关闭直接降级。
"""

from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient

from app.ability import voice_intent
from app.ability.llm import LLMError, LLMResult


def _llm_result(content: str) -> LLMResult:
    """构造 LLMResult 桩（内部函数）。"""
    return LLMResult(content=content, prompt_tokens=0, completion_tokens=0, model="stub")


class _StubLLMClient:
    """桩 LLM 客户端（测试用）：返回预设 content（模型类）。"""

    def __init__(self, content: str) -> None:
        self._content = content

    def chat(self, system: str, user: str, temperature: float = 0.2) -> LLMResult:  # noqa: ARG002
        return _llm_result(self._content)


class _BoomLLMClient:
    """恒抛异常的桩 LLM 客户端（测试用）。"""

    def chat(self, system: str, user: str, temperature: float = 0.2) -> LLMResult:  # noqa: ARG002
        raise LLMError("llm boom")


def test_extract_intent_json_valid() -> None:
    """合法 JSON（含围栏杂字）正确提取并归一（函数）。"""
    raw = '好的，解析如下：{"action":"timer_open","minutes":"5","step_no":null,"question":"","reply":null} 以上。'
    intent = voice_intent._extract_intent_json(raw)
    assert intent is not None
    assert intent["action"] == "timer_open"
    assert intent["minutes"] == 5
    assert intent["question"] is None


def test_extract_intent_json_invalid_action_falls_back_none() -> None:
    """action 不在枚举内归一为 none（函数）。"""
    intent = voice_intent._extract_intent_json('{"action":"delete_all","minutes":1}')
    assert intent is not None
    assert intent["action"] == "none"


def test_extract_intent_json_garbage_returns_none() -> None:
    """无 JSON / 非法 JSON / 顶层非 dict 返回 None（函数）。"""
    assert voice_intent._extract_intent_json("我没有听懂") is None
    assert voice_intent._extract_intent_json("{broken json") is None
    assert voice_intent._extract_intent_json('["next"]') is None


def test_intent_endpoint_ok(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    """LLM 正常返回结构化意图（函数）。"""
    from app.core.config import settings

    monkeypatch.setattr(settings, "VOICE_INTENT_ENABLED", "on")
    monkeypatch.setattr(
        voice_intent,
        "get_llm_client",
        lambda: _StubLLMClient('{"action":"help","minutes":null,"step_no":null,'
                               '"question":"火太大怎么办","reply":null}'),
    )
    resp = client.post(
        "/v1/speech/intent",
        json={"text": "锅里的火太大了怎么办", "context": {"current_step_no": 2, "total_steps": 8}},
        headers={"X-Anonymous-Id": f"anon_vi_{uuid.uuid4().hex[:8]}"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["action"] == "help"
    assert body["question"] == "火太大怎么办"
    assert body["degraded"] is False


def test_intent_endpoint_llm_error_degraded(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    """LLM 失败降级为 action=none + degraded=true（函数）。"""
    monkeypatch.setattr(voice_intent, "get_llm_client", lambda: _BoomLLMClient())
    resp = client.post("/v1/speech/intent", json={"text": "随便说点啥"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["action"] == "none"
    assert body["degraded"] is True


def test_intent_endpoint_empty_text_422(client: TestClient) -> None:
    """空文本 422（函数）。"""
    resp = client.post("/v1/speech/intent", json={"text": "   "})
    assert resp.status_code == 422


def test_intent_endpoint_disabled_degrades(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    """开关关闭时直接降级，不触达 LLM（函数）。"""
    from app.core.config import settings

    monkeypatch.setattr(settings, "VOICE_INTENT_ENABLED", "off")
    resp = client.post("/v1/speech/intent", json={"text": "下一步"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["action"] == "none"
    assert body["degraded"] is True
