"""语音识别路由模块（spec 模块 D，tag=识别与语音）。

职责：
    POST /v1/speech/asr：语音转文字（multipart 字段 file，百炼 qwen3-asr-flash）。
    POST /v1/speech/tts：文字转语音（JSON {text}，百炼 qwen3-tts-flash）。

红线：
    🔴 音频字节仅在内存中处理，绝不落盘（隐私要求，spec 模块 D）。

降级约定：
    provider 抛出任何异常 → 200 degraded:true（语音为增强入口，失败不阻断
    用户主链路；asr 引导文字输入，tts 引导自行看屏幕步骤文本）。
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

from fastapi import APIRouter, File, UploadFile
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from app.ability.llm import LLMError
from app.ability.providers import get_speech_provider, get_tts_provider
from app.ability.voice_intent import parse_voice_intent
from app.api.v1.deps import ERR_VALIDATION, api_error
from app.core.config import settings
from app.core.logging import get_logger
from app.schemas.vision import SpeechAsrResponse

router = APIRouter(prefix="/speech", tags=["识别与语音"])

logger = get_logger(__name__)

# TTS 单次合成文本长度上限（步骤描述远短于此，防异常长文刷用量）
_TTS_MAX_TEXT_LENGTH = 300


class SpeechTtsRequest(BaseModel):
    """TTS 请求体（模型类）。

    属性：
        text：待合成文本（步骤描述等，≤300 字符）。
    """

    text: str = Field(..., min_length=1, description="待合成文本")


class SpeechTtsResponse(BaseModel):
    """TTS 响应体（模型类）。

    属性：
        audio_base64：合成音频的 Base64（degraded 时为空串）。
        format：音频格式（如 wav）。
        degraded：降级标记（provider 失败时 true，前端静默不播）。
        message：降级说明（仅 degraded 时存在）。
    """

    audio_base64: str = ""
    format: str = "wav"
    degraded: bool = False
    message: str | None = None


@router.post(
    "/asr",
    response_model=SpeechAsrResponse,
    summary="语音转文字（阶段一 mock ASR 适配器，音频不落盘）",
)
def post_speech_asr(
    file: UploadFile = File(..., description="音频文件（webm/mp3/wav 等）"),
) -> dict:
    """语音转文字端点（函数）。

    说明：
        音频字节读入内存后直接交给 provider 转写（mock 实现返回固定演示文本）；
        provider 异常时降级返回空文本 + degraded 标注，引导用户改用文字输入。

    参数：
        file：上传音频文件（multipart 字段名 file）。

    返回值：
        dict：{text: str, degraded: bool, message?: str}。

    异常：
        HTTPException 422：上传文件为空；provider 异常内部捕获降级为 200。
    """
    # 🔴 隐私红线：音频字节仅在内存中处理，绝不写盘
    audio_bytes = file.file.read() or b""
    if not audio_bytes:
        raise api_error(422, ERR_VALIDATION, "请上传音频文件")

    try:
        text = get_speech_provider().transcribe(audio_bytes)
        logger.info("asr transcript: %r (bytes=%d)", text, len(audio_bytes))
    except Exception as exc:  # noqa: BLE001 —— provider 失败降级为文字输入引导
        logger.warning("speech provider failed: %s", exc)
        return {"text": "", "degraded": True, "message": "语音识别暂不可用，请使用文字输入"}

    return {"text": text, "degraded": False}


@router.post(
    "/tts",
    response_model=SpeechTtsResponse,
    summary="文字转语音（百炼 qwen3-tts-flash，音频不落盘）",
)
def post_speech_tts(body: SpeechTtsRequest) -> dict:
    """文字转语音端点（函数）。

    说明：
        步骤描述等文本合成为语音（base64 交前端播放）；provider 异常时降级
        返回 degraded=true（前端静默跳过播放，用户仍可看屏幕文本）。

    参数：
        body：{text} 待合成文本。

    返回值：
        dict：{audio_base64, format, degraded, message?}。

    异常：
        HTTPException 422：文本为空/超长；provider 异常内部捕获降级为 200。
    """
    text = body.text.strip()
    if not text:
        raise api_error(422, ERR_VALIDATION, "请提供待合成文本")
    if len(text) > _TTS_MAX_TEXT_LENGTH:
        raise api_error(422, ERR_VALIDATION, "文本过长（≤300 字符）")

    try:
        audio_base64, audio_format = get_tts_provider().synthesize(text)
        logger.info("tts synthesized: chars=%d bytes=%d", len(text), len(audio_base64))
    except Exception as exc:  # noqa: BLE001 —— provider 失败降级为静默跳过
        logger.warning("tts provider failed: %s", exc)
        return {"audio_base64": "", "format": "wav", "degraded": True, "message": "语音合成暂不可用"}

    return {"audio_base64": audio_base64, "format": audio_format, "degraded": False}


@router.get(
    "/tts/stream",
    summary="文字转语音流式（SSE 边合成边播，音频不落盘）",
)
def get_speech_tts_stream(text: str) -> StreamingResponse:
    """文字转语音流式端点（函数）。

    说明：
        mp3 分片直出（media_type=audio/mpeg），前端 <audio> 原生渐进播放，
        首声延迟显著低于整段 base64 方案；provider 建连失败抛 502（前端
        Audio error 事件静默跳过）；流中断即结束（已播部分保留）。

    参数：
        text：待合成文本（query 传入，≤300 字符）。

    返回值：
        StreamingResponse：audio/mpeg 音频流。

    异常：
        HTTPException 422：文本为空/超长；502：provider 建连失败。
    """
    text = text.strip()
    if not text:
        raise api_error(422, ERR_VALIDATION, "请提供待合成文本")
    if len(text) > _TTS_MAX_TEXT_LENGTH:
        raise api_error(422, ERR_VALIDATION, "文本过长（≤300 字符）")

    try:
        iterator: Iterator[bytes] = get_tts_provider().synthesize_stream(text)
    except Exception as exc:  # noqa: BLE001 —— 建连失败直接报错，前端静默
        logger.warning("tts stream provider failed: %s", exc)
        raise api_error(502, "TTS_UPSTREAM_FAILED", "语音合成暂不可用") from exc

    def _safe_iter() -> Iterator[bytes]:
        """兜底包裹：迭代期异常就地收流（流式响应无法改状态码，防打穿 ASGI）。"""
        try:
            yield from iterator
        except Exception as exc:  # noqa: BLE001 —— 限流/网络中断按提前结束处理
            logger.warning("tts stream error mid-flight: %s", exc)

    return StreamingResponse(_safe_iter(), media_type="audio/mpeg")


class VoiceIntentRequest(BaseModel):
    """语音意图解析请求体（模型类）。

    属性：
        text：白名单未命中的转写文本。
        context：烹饪上下文（当前步骤号/计时器状态等，供 LLM 合理性判断）。
    """

    text: str = Field(..., min_length=1, description="转写文本")
    context: dict[str, Any] = Field(default_factory=dict, description="烹饪上下文")


class VoiceIntentResponse(BaseModel):
    """语音意图解析响应体（模型类）。

    属性：
        action：指令枚举（与前端白名单一一对应；none=不可执行）。
        minutes：计时分钟数（timer_open 用，可空）。
        step_no：目标步骤号（step_jump 用，可空）。
        question：求助问题正文（help 用，可空）。
        reply：给用户的简短语音回应（none 时可空串）。
        degraded：降级标记（开关关闭 / LLM 失败时 true，前端静默忽略）。
    """

    action: str = "none"
    minutes: int | None = None
    step_no: int | None = None
    question: str | None = None
    reply: str | None = None
    degraded: bool = False


@router.post(
    "/intent",
    response_model=VoiceIntentResponse,
    summary="语音指令意图解析（白名单未命中时主 LLM 兜底）",
)
def post_speech_intent(body: VoiceIntentRequest) -> dict:
    """语音意图解析端点（函数）。

    说明：
        混合架构第二级：前端白名单未命中的转写交给主 LLM（DeepSeek）
        零样本解析为结构化指令。开关 VOICE_INTENT_ENABLED=off 或 LLM
        失败时降级返回 action=none + degraded=true（前端静默忽略，
        语音主链路不受影响——高频指令完全不经过本端点）。

    参数：
        body：{text, context}。

    返回值：
        dict：{action, minutes, step_no, question, reply, degraded}。

    异常：
        HTTPException 422：文本为空；LLM 失败内部捕获降级为 200。
    """
    text = body.text.strip()
    if not text:
        raise api_error(422, ERR_VALIDATION, "请提供转写文本")

    if (settings.VOICE_INTENT_ENABLED or "on").strip().lower() != "on":
        return {"action": "none", "degraded": True, "reply": None}

    try:
        intent = parse_voice_intent(text, body.context)
    except LLMError as exc:
        logger.warning("voice intent failed: %s", exc)
        return {"action": "none", "degraded": True, "reply": None}
    logger.info("voice intent: %r -> %s", text[:60], intent["action"])
    return {**intent, "degraded": False}
