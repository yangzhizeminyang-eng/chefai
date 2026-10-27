"""ASR / Vision / TTS provider 边界测试（任务 B）。

覆盖：
    - mock 可辨识：三个 Mock 实现类 mode='mock'、真实实现类按渠道声明
      （bailian / vlm）；ASR / TTS / vision 端点响应携带 mode 字段
      （新增可选字段，前端可忽略），provider 异常降级时 mode=None；
    - 工厂降级：speech / tts 配置未知名或凭证缺失 → 回退 mock 且
      logger.warning（不伪装成目标 provider 成功）；vision 未知名回退
      由 test_vision_provider_vlm.py::test_factory_unknown_fallback_mock
      覆盖（复跑确认，不重复）；
    - 边界输入：空音频 / >1MB 音频 / 空文本 / 超长文本 / 空图片 /
      无效图片字节（mock 语义不校验图片格式）；
    - 真实 provider 异常路径（不触网）：Bailian ASR / TTS 无凭证构造抛
      LLMError；网络/超时异常统一包装为 LLMError（路由层降级契约）；
    - 音频不落盘：ASR 端点调用前后 uploads 留档目录快照不变（隐私红线）；
    - 真实 provider smoke：仅当对应凭证已配置（settings 字段非空串判断，
      不打印值）才执行单条最小调用；调用失败（凭证无效/网络不可达）skip
      并标注「待环境验证」，无凭证直接 skip，绝不伪造通过。

既有覆盖（复跑确认，不在本文件重复）：
    - vision 额度 429 / 全低置信不扣额度 / provider 异常降级：
      tests/test_api_vision_speech.py；
    - VLM JSON 解析异常 / 空图片短路 / 向量阈值：
      tests/test_vision_provider_vlm.py。
"""

from __future__ import annotations

import base64
import json
import logging
import struct
import threading
import uuid
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.ability.llm import LLMError
from app.ability.providers import (
    MOCK_ASR_TEXT,
    BailianASRProvider,
    BailianTTSProvider,
    MockASRProvider,
    MockTTSProvider,
    MockVisionProvider,
    MultimodalVisionProvider,
    RealtimeBailianASRProvider,
    _build_speech_provider,
    _build_tts_provider,
)
from app.api.v1 import speech as speech_module
from app.api.v1 import vision as vision_module
from app.core.config import settings
from app.main import app as main_app
from tests.conftest import _RAW_ENV, ensure_router_registered

# ---- 路由接线（幂等）：本文件独立运行时保证端点可达 ----
# 懒加载路由下 main_app.routes 的 path 探测不可靠（_IncludedRouter path=None），
# 统一走 conftest.ensure_router_registered（router 对象身份探测，防重复 include）。
ensure_router_registered(
    main_app,
    (speech_module.router, vision_module.router),
    flag="_provider_boundaries_routes_registered",
    prefix="/v1",
)

# uploads 留档根目录（与 vision 模块同口径：backend/uploads）
_UPLOADS_DIR = Path(__file__).resolve().parents[1] / "uploads"

# 1x1 透明 PNG（真实 VLM smoke 最小合法图片，仅凭证已配置时使用）
_MINIMAL_PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
)


def _uploads_snapshot() -> set[str]:
    """对 uploads 留档目录取文件快照（函数）。

    返回值：
        set[str]：目录下全部文件相对路径字符串（目录不存在返回空集）。

    异常：
        无。
    """
    if not _UPLOADS_DIR.exists():
        return set()
    return {str(p.relative_to(_UPLOADS_DIR)) for p in _UPLOADS_DIR.rglob("*") if p.is_file()}


# ---------------------------------------------------------------------------
# mock 可辨识（mode 标记）
# ---------------------------------------------------------------------------
def test_mock_providers_declare_mock_mode() -> None:
    """三个 Mock 实现类 mode 恒 'mock'（函数）。

    参数：
        无。

    返回值：
        None。

    异常：
        断言失败即测试失败。
    """
    assert MockVisionProvider().mode == "mock"
    assert MockASRProvider().mode == "mock"
    assert MockTTSProvider().mode == "mock"


def test_real_providers_declare_channel_mode() -> None:
    """真实实现类按渠道声明 mode（vlm / bailian）（函数）。

    参数：
        无。

    返回值：
        None。

    异常：
        断言失败即测试失败。
    """
    assert MultimodalVisionProvider.mode == "vlm"
    assert BailianASRProvider.mode == "bailian"
    assert RealtimeBailianASRProvider.mode == "bailian-realtime"
    assert BailianTTSProvider.mode == "bailian"


def test_realtime_asr_sends_wav_pcm_frames_and_returns_final_text(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Realtime ASR strips the WAV container before sending PCM to DashScope."""
    monkeypatch.setattr(settings, "SPEECH_API_KEY", "sdk-test-key")
    monkeypatch.setattr(settings, "VISION_API_KEY", "")
    monkeypatch.setattr(settings, "SPEECH_MODEL", "qwen3-asr-flash-realtime")
    monkeypatch.setattr(
        settings,
        "SPEECH_WEBSOCKET_URL",
        "wss://dashscope.aliyuncs.com/api-ws/v1/realtime",
    )
    pcm = b"\x01\x00" * 9000
    wav = (
        b"RIFF" + struct.pack("<I", 36 + len(pcm)) + b"WAVE"
        + b"fmt " + struct.pack("<IHHIIHH", 16, 1, 1, 16000, 32000, 2, 16)
        + b"data" + struct.pack("<I", len(pcm)) + pcm
    )
    calls: dict[str, object] = {"frames": []}

    class _WebSocketApp:
        def __init__(self, url, header, on_open, on_message, on_error, on_close):
            calls["url"] = url
            calls["header"] = header
            self._on_open = on_open
            self._on_message = on_message
            self._on_close = on_close
            self.closed = threading.Event()

        def send(self, message: str):
            event = json.loads(message)
            calls.setdefault("events", []).append(event)
            if event["type"] == "session.update":
                self._on_message(self, json.dumps({"type": "session.updated"}))
            elif event["type"] == "input_audio_buffer.append":
                calls["frames"].append(base64.b64decode(event["audio"]))
                if sum(map(len, calls["frames"])) == len(pcm):
                    self._on_message(
                        self,
                        json.dumps({
                            "type": "conversation.item.input_audio_transcription.completed",
                            "transcript": "下一步，翻面",
                        }),
                    )

        def run_forever(self, **_kwargs):
            self._on_open(self)
            assert self.closed.wait(timeout=2)

        def close(self):
            self.closed.set()
            self._on_close(self, 1000, "closed")

    monkeypatch.setattr("websocket.WebSocketApp", _WebSocketApp)
    text = RealtimeBailianASRProvider().transcribe(wav)

    assert text == "下一步，翻面"
    assert b"".join(calls["frames"]) == pcm
    assert all(len(frame) <= 3200 for frame in calls["frames"])
    assert calls["url"].endswith("/realtime?model=qwen3-asr-flash-realtime")
    events = calls["events"]
    assert events[0]["type"] == "session.update"
    assert events[0]["session"]["input_audio_format"] == "pcm"
    assert events[-1]["type"] == "input_audio_buffer.append"


def test_realtime_asr_rejects_non_16khz_mono_pcm_wav(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Realtime ASR rejects incompatible WAV instead of mislabeling its PCM."""
    monkeypatch.setattr(settings, "SPEECH_API_KEY", "sdk-test-key")
    monkeypatch.setattr(settings, "VISION_API_KEY", "")
    pcm = b"\x00\x00" * 10
    wav = (
        b"RIFF" + struct.pack("<I", 36 + len(pcm)) + b"WAVE"
        + b"fmt " + struct.pack("<IHHIIHH", 16, 1, 2, 44100, 176400, 4, 16)
        + b"data" + struct.pack("<I", len(pcm)) + pcm
    )
    with pytest.raises(LLMError, match="16 kHz mono PCM WAV"):
        RealtimeBailianASRProvider().transcribe(wav)


def test_asr_endpoint_response_carries_mock_mode(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """ASR 端点 mock 路径响应携带 mode='mock'（函数）。

    参数：
        client：TestClient fixture。
        monkeypatch：固定 speech 工厂为 mock（与部署配置解耦）。

    返回值：
        None。

    异常：
        断言失败即测试失败。
    """
    monkeypatch.setattr(speech_module, "get_speech_provider", lambda: MockASRProvider())
    resp = client.post(
        "/v1/speech/asr", files={"file": ("voice.webm", b"fake-audio", "audio/webm")}
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["mode"] == "mock"
    assert body["text"] == MOCK_ASR_TEXT
    assert body["degraded"] is False


def test_asr_endpoint_degraded_mode_is_none(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """ASR provider 异常降级响应 mode=None（degraded 与 mode 并存，函数）。

    参数：
        client：TestClient fixture。
        monkeypatch：speech 工厂恒抛异常。

    返回值：
        None。

    异常：
        断言失败即测试失败。
    """
    def _boom() -> MockASRProvider:
        """抛异常工厂（内部函数）。

        返回值：
            无（恒抛出）。

        异常：
            RuntimeError：模拟 provider 故障。
        """
        raise RuntimeError("asr boom")

    monkeypatch.setattr(speech_module, "get_speech_provider", _boom)
    resp = client.post(
        "/v1/speech/asr", files={"file": ("voice.webm", b"fake-audio", "audio/webm")}
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["degraded"] is True
    assert body["mode"] is None
    assert body["text"] == ""


def test_tts_endpoint_response_carries_mock_mode(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """TTS 端点 mock 路径响应携带 mode='mock'（函数）。

    参数：
        client：TestClient fixture。
        monkeypatch：固定 tts 工厂为 mock。

    返回值：
        None。

    异常：
        断言失败即测试失败。
    """
    monkeypatch.setattr(speech_module, "get_tts_provider", lambda: MockTTSProvider())
    resp = client.post("/v1/speech/tts", json={"text": "下一步，翻炒两分钟"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["mode"] == "mock"
    assert body["audio_base64"] == ""
    assert body["degraded"] is False


def test_vision_endpoint_response_carries_mock_mode(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """vision 端点 mock 路径响应携带 mode='mock'（函数）。

    说明：
        工厂直连 MockVisionProvider（确定性识别，种子库必含常用食材）。

    参数：
        client：TestClient fixture。
        monkeypatch：固定 vision 工厂为 mock 并将留档目录指向 tmp。

    返回值：
        None。

    异常：
        断言失败即测试失败。
    """
    monkeypatch.setattr(vision_module, "get_vision_provider", lambda: MockVisionProvider())
    resp = client.post(
        "/v1/vision/recognize",
        files={"file": ("photo.jpg", b"boundary-test-image-bytes", "image/jpeg")},
        headers={"X-Anonymous-Id": f"anon_bnd_{uuid.uuid4().hex[:10]}"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["mode"] == "mock"
    assert body["degraded"] is False


def test_vision_endpoint_stub_without_mode_yields_none(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """实现类未声明 mode（如测试桩）→ 响应 mode=None 防御路径（函数）。

    参数：
        client：TestClient fixture。
        monkeypatch：vision 工厂替换为无 mode 声明的桩 provider。

    返回值：
        None。

    异常：
        断言失败即测试失败。
    """
    from app.ability.providers import RecognizedItem, VisionProvider

    class _ModelessStub(VisionProvider):
        """无 mode 声明的桩 provider（模型类，模拟旧式实现）。"""

        def recognize(self, image_bytes: bytes) -> list[RecognizedItem]:
            """返回单项 high 识别项（函数）。

            参数：
                image_bytes：图片字节（忽略）。

            返回值：
                list[RecognizedItem]：单项 high（番茄）。

            异常：
                无。
            """
            return [RecognizedItem(name="番茄", confidence="high", ingredient_id=1)]

    monkeypatch.setattr(vision_module, "get_vision_provider", lambda: _ModelessStub())
    resp = client.post(
        "/v1/vision/recognize",
        files={"file": ("photo.jpg", b"modeless-stub-image", "image/jpeg")},
        headers={"X-Anonymous-Id": f"anon_bnd_{uuid.uuid4().hex[:10]}"},
    )
    assert resp.status_code == 200
    assert resp.json()["mode"] is None


# ---------------------------------------------------------------------------
# 工厂降级（speech / tts；vision 既有覆盖复跑）
# ---------------------------------------------------------------------------
def test_speech_factory_unknown_name_falls_back_with_warning(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """SPEECH_PROVIDER 未知名 → 回退 mock + warning（函数）。

    参数：
        monkeypatch：临时改写 settings.SPEECH_PROVIDER。
        caplog：捕获 providers 模块日志。

    返回值：
        None。

    异常：
        断言失败即测试失败。
    """
    monkeypatch.setattr(settings, "SPEECH_PROVIDER", "no-such-asr")
    with caplog.at_level(logging.WARNING, logger="app.ability.providers"):
        provider = _build_speech_provider()
    assert isinstance(provider, MockASRProvider)
    assert provider.mode == "mock"
    assert any("SPEECH_PROVIDER" in record.message for record in caplog.records)


def test_speech_factory_selects_realtime_dashscope_provider(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Configured realtime mode builds the matching real provider explicitly."""
    monkeypatch.setattr(settings, "SPEECH_PROVIDER", "bailian-realtime")
    monkeypatch.setattr(settings, "SPEECH_API_KEY", "sdk-test-key")
    provider = _build_speech_provider()
    assert isinstance(provider, RealtimeBailianASRProvider)
    assert provider.mode == "bailian-realtime"


def test_tts_factory_unknown_name_falls_back_with_warning(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """TTS_PROVIDER 未知名 → 回退 mock + warning（函数）。

    参数：
        monkeypatch：临时改写 settings.TTS_PROVIDER。
        caplog：捕获 providers 模块日志。

    返回值：
        None。

    异常：
        断言失败即测试失败。
    """
    monkeypatch.setattr(settings, "TTS_PROVIDER", "no-such-tts")
    with caplog.at_level(logging.WARNING, logger="app.ability.providers"):
        provider = _build_tts_provider()
    assert isinstance(provider, MockTTSProvider)
    assert any("TTS_PROVIDER" in record.message for record in caplog.records)


def test_speech_factory_missing_credentials_falls_back_with_warning(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """SPEECH_PROVIDER=bailian 但凭证全空 → 回退 mock + warning（函数）。

    说明：
        工厂捕获构建期 LLMError 后回退 mock——不得伪装成真实转写成功。

    参数：
        monkeypatch：SPEECH_PROVIDER='bailian' 且 SPEECH/VISION API_KEY 置空串。
        caplog：捕获 providers 模块日志。

    返回值：
        None。

    异常：
        断言失败即测试失败。
    """
    monkeypatch.setattr(settings, "SPEECH_PROVIDER", "bailian")
    monkeypatch.setattr(settings, "SPEECH_API_KEY", "")
    monkeypatch.setattr(settings, "VISION_API_KEY", "")
    monkeypatch.setattr(settings, "LLM_API_KEY", "")
    with caplog.at_level(logging.WARNING, logger="app.ability.providers"):
        provider = _build_speech_provider()
    assert isinstance(provider, MockASRProvider)
    assert any("fallback to mock" in record.message for record in caplog.records)


def test_tts_factory_missing_credentials_falls_back_with_warning(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """TTS_PROVIDER=bailian 但三级凭证全空 → 回退 mock + warning（函数）。

    参数：
        monkeypatch：TTS_PROVIDER='bailian' 且 TTS/SPEECH/VISION API_KEY 置空串。
        caplog：捕获 providers 模块日志。

    返回值：
        None。

    异常：
        断言失败即测试失败。
    """
    monkeypatch.setattr(settings, "TTS_PROVIDER", "bailian")
    monkeypatch.setattr(settings, "TTS_API_KEY", "")
    monkeypatch.setattr(settings, "SPEECH_API_KEY", "")
    monkeypatch.setattr(settings, "VISION_API_KEY", "")
    monkeypatch.setattr(settings, "LLM_API_KEY", "")
    with caplog.at_level(logging.WARNING, logger="app.ability.providers"):
        provider = _build_tts_provider()
    assert isinstance(provider, MockTTSProvider)
    assert any("fallback to mock" in record.message for record in caplog.records)


# ---------------------------------------------------------------------------
# 边界输入（mock 语义）
# ---------------------------------------------------------------------------
def test_mock_asr_empty_audio_returns_empty_text() -> None:
    """空音频 → 空文本（不抛、不落盘）（函数）。

    参数：
        无。

    返回值：
        None。

    异常：
        断言失败即测试失败。
    """
    assert MockASRProvider().transcribe(b"") == ""


def test_mock_asr_oversized_audio_still_in_memory() -> None:
    """>1MB 音频 → 恒定演示文本，不做解码不落盘（函数）。

    参数：
        无。

    返回值：
        None。

    异常：
        断言失败即测试失败。
    """
    oversized = b"\x00" * (1024 * 1024 + 1)
    assert MockASRProvider().transcribe(oversized) == MOCK_ASR_TEXT


def test_mock_vision_empty_image_returns_empty() -> None:
    """空图片 → 空识别结果（函数）。

    参数：
        无。

    返回值：
        None。

    异常：
        断言失败即测试失败。
    """
    assert MockVisionProvider().recognize(b"") == []


def test_mock_vision_invalid_image_bytes_no_crash() -> None:
    """无效图片字节（非图片内容）→ 不抛异常，确定性 mock 语义照常返回（函数）。

    说明：
        mock 实现按字节哈希驱动、不校验图片格式（真实 VLM 的格式校验在
        服务端），故非图片字节同样确定性返回库内食材项——本用例锁定该
        语义边界（不崩、可 confirm）。

    参数：
        无。

    返回值：
        None。

    异常：
        断言失败即测试失败。
    """
    items = MockVisionProvider().recognize(b"this-is-not-an-image-at-all")
    assert isinstance(items, list)
    assert all(item.name for item in items)
    assert all(item.ingredient_id is not None for item in items)


def test_mock_tts_empty_and_oversized_text() -> None:
    """空文本 / 超长文本 → 恒空音频占位（mock 无用量）（函数）。

    参数：
        无。

    返回值：
        None。

    异常：
        断言失败即测试失败。
    """
    provider = MockTTSProvider()
    assert provider.synthesize("") == ("", "wav")
    assert provider.synthesize("长" * 5000) == ("", "wav")


def test_mock_tts_stream_empty_text_yields_nothing() -> None:
    """流式合成空文本 → 不产出任何字节块（函数）。

    参数：
        无。

    返回值：
        None。

    异常：
        断言失败即测试失败。
    """
    assert list(MockTTSProvider().synthesize_stream("")) == []


# ---------------------------------------------------------------------------
# 真实 provider 异常路径（不触网）
# ---------------------------------------------------------------------------
def test_bailian_asr_missing_credentials_raises_llm_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Bailian ASR 无凭证构造 → LLMError（函数）。

    参数：
        monkeypatch：SPEECH/VISION API_KEY 置空串。

    返回值：
        None。

    异常：
        未抛 LLMError 即测试失败。
    """
    monkeypatch.setattr(settings, "SPEECH_API_KEY", "")
    monkeypatch.setattr(settings, "VISION_API_KEY", "")
    with pytest.raises(LLMError):
        BailianASRProvider()


def test_bailian_asr_timeout_wrapped_as_llm_error(monkeypatch: pytest.MonkeyPatch) -> None:
    """Bailian ASR 网络/超时异常 → 统一包装 LLMError（降级契约，函数）。

    参数：
        monkeypatch：注入 dummy 凭证构造客户端，并令底层 SDK 调用抛超时。

    返回值：
        None。

    异常：
        未抛 LLMError 即测试失败。
    """
    monkeypatch.setattr(settings, "SPEECH_API_KEY", "dummy-key-for-test")
    provider = BailianASRProvider()

    def _timeout(*args, **kwargs):
        """模拟 SDK 超时（内部函数）。

        参数：
            args / kwargs：透传占位。

        返回值：
            无（恒抛出）。

        异常：
            TimeoutError：模拟网络超时。
        """
        raise TimeoutError("connection timed out")

    monkeypatch.setattr(provider._client.chat.completions, "create", _timeout)
    with pytest.raises(LLMError, match="语音识别"):
        provider.transcribe(b"fake-audio-bytes")


def test_bailian_tts_missing_credentials_raises_llm_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Bailian TTS 无凭证构造 → LLMError（函数）。

    参数：
        monkeypatch：TTS/SPEECH/VISION API_KEY 置空串。

    返回值：
        None。

    异常：
        未抛 LLMError 即测试失败。
    """
    monkeypatch.setattr(settings, "TTS_API_KEY", "")
    monkeypatch.setattr(settings, "SPEECH_API_KEY", "")
    monkeypatch.setattr(settings, "VISION_API_KEY", "")
    with pytest.raises(LLMError):
        BailianTTSProvider()


def test_bailian_tts_does_not_reuse_vision_credentials(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A vision-provider key is not treated as a DashScope speech credential."""
    monkeypatch.setattr(settings, "TTS_API_KEY", "")
    monkeypatch.setattr(settings, "SPEECH_API_KEY", "")
    monkeypatch.setattr(settings, "VISION_API_KEY", "volcengine-only-key")
    with pytest.raises(LLMError, match="TTS_API_KEY/SPEECH_API_KEY"):
        BailianTTSProvider()


def test_bailian_tts_http_error_wrapped_as_llm_error(monkeypatch: pytest.MonkeyPatch) -> None:
    """Bailian TTS HTTP 异常 → 统一包装 LLMError（降级契约，函数）。

    参数：
        monkeypatch：注入 dummy 凭证构造实例，并令 httpx.post 抛连接异常。

    返回值：
        None。

    异常：
        未抛 LLMError 即测试失败。
    """
    import httpx

    monkeypatch.setattr(settings, "TTS_API_KEY", "dummy-key-for-test")
    provider = BailianTTSProvider()

    def _conn_error(*args, **kwargs):
        """模拟建连失败（内部函数）。

        参数：
            args / kwargs：透传占位。

        返回值：
            无（恒抛出）。

        异常：
            httpx.ConnectError：模拟网络不可达。
        """
        raise httpx.ConnectError("connection refused")

    monkeypatch.setattr("app.ability.providers.httpx.post", _conn_error)
    with pytest.raises(LLMError, match="语音合成"):
        provider.synthesize("测试文本")


def test_bailian_tts_uses_dashscope_sdk_and_configured_endpoint(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """TTS invokes the official SDK against the configured native API endpoint."""
    from types import SimpleNamespace

    import dashscope

    monkeypatch.setattr(settings, "TTS_API_KEY", "sdk-test-key")
    monkeypatch.setattr(settings, "TTS_API_BASE_URL", "https://dashscope.example/api/v1")
    monkeypatch.setattr(settings, "TTS_MODEL", "qwen3-tts-flash")
    monkeypatch.setattr(settings, "TTS_VOICE", "Cherry")
    provider = BailianTTSProvider()
    previous_base = dashscope.base_http_api_url
    calls: list[dict] = []

    def _call(**kwargs):
        calls.append({**kwargs, "base_url": dashscope.base_http_api_url})
        return SimpleNamespace(
            status_code=200,
            output=SimpleNamespace(audio=SimpleNamespace(data="UklGRg==", url="")),
        )

    monkeypatch.setattr("dashscope.audio.qwen_tts.SpeechSynthesizer.call", _call)
    audio_base64, audio_format = provider.synthesize("翻炒 2 min")

    assert audio_base64 == "UklGRg=="
    assert audio_format == "wav"
    assert calls == [{
        "model": "qwen3-tts-flash",
        "text": "翻炒 2 分钟",
        "api_key": "sdk-test-key",
        "voice": "Cherry",
        "base_url": "https://dashscope.example/api/v1",
    }]
    assert dashscope.base_http_api_url == previous_base
    assert list(provider.synthesize_stream("翻炒 2 min")) == [b"RIFF"]


def test_bailian_tts_downloads_sdk_audio_url_response(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """TTS extracts the temporary audio URL returned by the actual SDK model."""
    from types import SimpleNamespace

    monkeypatch.setattr(settings, "TTS_API_KEY", "sdk-test-key")
    provider = BailianTTSProvider()
    response = SimpleNamespace(
        status_code=200,
        output=SimpleNamespace(
            audio={"data": "", "url": "https://audio.example/result.wav"}
        ),
    )
    monkeypatch.setattr("dashscope.audio.qwen_tts.SpeechSynthesizer.call", lambda **_: response)
    downloaded: list[str] = []

    def _unexpected_httpx_get(*_args, **_kwargs):
        raise AssertionError("signed temporary URLs must not enter HTTPX request logs")

    monkeypatch.setattr("app.ability.providers.httpx.get", _unexpected_httpx_get)
    monkeypatch.setattr(
        "app.ability.providers.urlopen",
        lambda url, timeout: _UrlResponse(url, downloaded),
    )
    audio_base64, audio_format = provider.synthesize("你好")

    assert downloaded == ["https://audio.example/result.wav"]
    assert base64.b64decode(audio_base64) == b"RIFFwave"
    assert audio_format == "wav"


class _UrlResponse:
    def __init__(self, url: str, downloaded: list[str]) -> None:
        downloaded.append(url)

    def __enter__(self):
        return self

    def __exit__(self, *_args) -> None:
        return None

    def read(self) -> bytes:
        return b"RIFFwave"


# ---------------------------------------------------------------------------
# 音频不落盘（隐私红线）
# ---------------------------------------------------------------------------
def test_asr_audio_never_persisted(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """ASR 端点调用前后 uploads 留档目录快照不变（函数）。

    说明：
        音频字节仅内存处理：上传假音频转写成功后，uploads 目录无任何
        新增/删除（对照 vision 识别成功会留档图片）。

    参数：
        client：TestClient fixture。
        monkeypatch：固定 speech 工厂为 mock。

    返回值：
        None。

    异常：
        断言失败即测试失败。
    """
    monkeypatch.setattr(speech_module, "get_speech_provider", lambda: MockASRProvider())
    before = _uploads_snapshot()
    resp = client.post(
        "/v1/speech/asr", files={"file": ("voice.webm", b"fake-audio-not-persisted", "audio/webm")}
    )
    assert resp.status_code == 200
    assert resp.json()["degraded"] is False
    assert _uploads_snapshot() == before


# ---------------------------------------------------------------------------
# 真实 provider smoke（仅凭证已配置时执行；失败 skip 标注待环境验证）
# ---------------------------------------------------------------------------
# 凭证判定口径（conftest fail-closed 强制覆盖后的 opt-in 适配）：
# conftest 已把本进程环境强制覆写为离线值（settings.* 恒 mock，不再反映
# 调用方预设），故 skipif 改从 conftest._RAW_ENV 读取——conftest 覆盖前对
# 进程环境变量（调用方显式注入）的快照；不消费 .env 文件值。仅在调用方
# 显式向测试进程注入真实凭证时 smoke 才执行（opt-in 语义不变）。
def _asr_credentials_configured() -> bool:
    """判断真实 ASR 是否已配置凭证（函数，不打印值）。

    返回值：
        bool：原始环境 SPEECH_PROVIDER='bailian' 且 SPEECH/VISION API Key
        至少一个非空（依据 conftest._RAW_ENV 覆盖前快照）。

    异常：
        无。
    """
    provider = (_RAW_ENV.get("SPEECH_PROVIDER") or "").strip().lower()
    has_key = bool(
        (_RAW_ENV.get("SPEECH_API_KEY") or "").strip()
        or (_RAW_ENV.get("VISION_API_KEY") or "").strip()
    )
    return provider == "bailian" and has_key


def _tts_credentials_configured() -> bool:
    """判断真实 TTS 是否已配置凭证（函数，不打印值）。

    返回值：
        bool：原始环境 TTS_PROVIDER='bailian' 且 TTS/SPEECH API Key
        至少一个非空（依据 conftest._RAW_ENV 覆盖前快照）。

    异常：
        无。
    """
    provider = (_RAW_ENV.get("TTS_PROVIDER") or "").strip().lower()
    has_key = bool(
        (_RAW_ENV.get("TTS_API_KEY") or "").strip()
        or (_RAW_ENV.get("SPEECH_API_KEY") or "").strip()
    )
    return provider == "bailian" and has_key


def _vlm_credentials_configured() -> bool:
    """判断真实 VLM 是否已配置凭证（函数，不打印值）。

    返回值：
        bool：原始环境 VISION_PROVIDER='vlm' 且 VISION API Key 非空
        （依据 conftest._RAW_ENV 覆盖前快照）。

    异常：
        无。
    """
    provider = (_RAW_ENV.get("VISION_PROVIDER") or "").strip().lower()
    has_key = bool((_RAW_ENV.get("VISION_API_KEY") or "").strip())
    return provider == "vlm" and has_key


@pytest.mark.skipif(
    not _asr_credentials_configured(),
    reason="真实 ASR 凭证未配置（或测试进程强制 mock），待环境验证",
)
def test_real_asr_smoke_min_call() -> None:
    """真实百炼 ASR 单条最小调用（smoke）（函数）。

    说明：
        仅凭证已配置时执行；调用失败（凭证无效/网络不可达）skip 标注
        待环境验证，不伪造通过。

    参数：
        无。

    返回值：
        None。

    异常：
        断言失败即测试失败；LLMError skip。
    """
    try:
        text = BailianASRProvider().transcribe(b"RIFF minimal smoke audio")
    except LLMError as exc:
        pytest.skip(f"真实 ASR 调用失败（待环境验证）：{exc}")
    assert isinstance(text, str)


@pytest.mark.skipif(
    not _tts_credentials_configured(),
    reason="真实 TTS 凭证未配置（或测试进程强制 mock），待环境验证",
)
def test_real_tts_smoke_min_call() -> None:
    """真实百炼 TTS 单条最小调用（smoke）（函数）。

    参数：
        无。

    返回值：
        None。

    异常：
        断言失败即测试失败；LLMError skip。
    """
    try:
        audio_base64, audio_format = BailianTTSProvider().synthesize("好")
    except LLMError as exc:
        pytest.skip(f"真实 TTS 调用失败（待环境验证）：{exc}")
    assert isinstance(audio_base64, str) and audio_base64
    assert isinstance(audio_format, str) and audio_format


@pytest.mark.skipif(
    not _vlm_credentials_configured(),
    reason="真实 VLM 凭证未配置（或测试进程强制 mock），待环境验证",
)
def test_real_vlm_smoke_min_call() -> None:
    """真实 VLM 单条最小调用（smoke）（函数）。

    参数：
        无。

    返回值：
        None。

    异常：
        断言失败即测试失败；LLMError skip。
    """
    try:
        items = MultimodalVisionProvider().recognize(_MINIMAL_PNG)
    except LLMError as exc:
        pytest.skip(f"真实 VLM 调用失败（待环境验证）：{exc}")
    assert isinstance(items, list)
    assert all(item.name for item in items)
