"""语音识别路由模块（spec 模块 D，tag=识别与语音）。

职责：
    POST /v1/speech/asr：语音转文字（multipart 字段 file，阶段一 mock ASR 适配器）。

红线：
    🔴 音频字节仅在内存中处理，绝不落盘（隐私要求，spec 模块 D）。

降级约定：
    provider 抛出任何异常 → 200 {text:"", degraded:true, message:"语音识别暂不可用，
    请使用文字输入"}（语音为增强入口，失败不阻断用户主链路）。
"""

from __future__ import annotations

from fastapi import APIRouter, File, UploadFile

from app.ability.providers import get_speech_provider
from app.api.v1.deps import ERR_VALIDATION, api_error
from app.core.logging import get_logger
from app.schemas.vision import SpeechAsrResponse

router = APIRouter(prefix="/speech", tags=["识别与语音"])

logger = get_logger(__name__)


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
    except Exception as exc:  # noqa: BLE001 —— provider 失败降级为文字输入引导
        logger.warning("speech provider failed: %s", exc)
        return {"text": "", "degraded": True, "message": "语音识别暂不可用，请使用文字输入"}

    return {"text": text, "degraded": False}
