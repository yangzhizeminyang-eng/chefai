"""识别与语音能力适配器模块（provider 模式，spec 模块 D 后半）。

职责：
    定义视觉识别与语音转写的抽象接口及各提供方实现：
    - VisionProvider / RecognizedItem：视觉识别接口（图片字节 → 食材识别项列表）；
    - MockVisionProvider：确定性 mock——按图片字节 sha256 哈希从 ingredient 表常用
      子集中确定性挑 3~6 个（75% 概率 high 置信）；只返回 ingredient 表真实存在的
      食材名（否则 confirm 校验会失败）；
    - MultimodalVisionProvider：真实视觉模型（VLM）实现——经 LLMClient.chat_with_image
      调用阿里云百炼 qwen omni 系列多模态模型识别冰箱照片中的食材，输出经
      JSON 容错解析 + 名称归一化三路（精确 / 别名 / 向量最近邻）映射为库内
      真实食材项；🔴 库外名字绝不返回（否则 confirm 校验必失败，用户感知
      「认出来却用不了」）；绝不输出任何可食性/安全性结论（RL-3 红线）；
    - ASRProvider：语音转写接口（音频字节 → 文本）；
    - MockASRProvider：返回固定演示文本（不落盘、无网络调用）；
    - BailianASRProvider：真实语音转写——经 OpenAI 兼容协议调用阿里云百炼
      qwen3-asr-flash（base_url/api_key 空串回落 VISION_*，百炼同一凭证）；
    - get_vision_provider / get_speech_provider：进程级单例工厂；视觉工厂读
      settings.VISION_PROVIDER（pydantic-settings 自 .env 加载，缺省 mock），
      语音工厂读 settings.SPEECH_PROVIDER（缺省 mock）。

接入真实模型：
    provider 内任何异常由上层（路由层）捕获后降级：识别降级为手动选食材、
    语音降级为文字输入，绝不向上抛出阻断主链路。
"""

from __future__ import annotations

import base64
import hashlib
import json
import random
import re
import threading
from abc import ABC, abstractmethod
from collections.abc import Iterator
from dataclasses import dataclass

import httpx
import openai
from sqlalchemy import select

from app.ability.embedding import get_embedding_provider
from app.ability.llm import LLMError, get_llm_client
from app.core.config import settings
from app.core.db import SessionLocal
from app.core.logging import get_logger
from app.models import Ingredient, IngredientAlias

logger = get_logger(__name__)

# Mock 视觉常用食材子集（均为家常高频食材；实际返回前会再查 ingredient 表过滤，
# 子集中不存在的名字会被自动剔除，保证返回项必可 confirm）
MOCK_VISION_COMMON_NAMES: list[str] = [
    "番茄", "鸡蛋", "土豆", "青椒", "黄瓜", "胡萝卜", "洋葱",
    "西兰花", "大蒜", "猪五花肉", "豆腐", "小葱",
]

# Mock ASR 固定演示文本（阶段一无真实语音模型，演示链路用）
MOCK_ASR_TEXT = "用鸡蛋和西红柿做菜"

# high 置信概率（spec：75% 概率 high，其余 low）
_HIGH_CONFIDENCE_PROBABILITY = 0.75


# ---------------------------------------------------------------------------
# TTS 文本中文归一化（用户要求：所有语音输出必须是中文）
# ---------------------------------------------------------------------------

# 领域单位替换表（顺序敏感：长词组在前，防 "cm³" 被 "cm" 先吃掉）
_TTS_UNIT_REPLACEMENTS: list[tuple[str, str]] = [
    ("cm³", "立方厘米"),
    ("cm3", "立方厘米"),
    ("m³", "立方米"),
    ("kg", "千克"),
    ("cm", "厘米"),
    ("mm", "毫米"),
    ("ml", "毫升"),
    ("℃", "摄氏度"),
    ("°c", "摄氏度"),
    ("°f", "华氏度"),
    ("min", "分钟"),
]

# 数字后紧跟的孤立克单位 g（如「盐 2g」→「2克」；避免误伤其他拉丁词）
_TTS_GRAM_RE = re.compile(r"(?<=\d)\s*g(?![a-za-z])", re.IGNORECASE)
# 兜底：剔除剩余拉丁字母串（保证合成的语音永远不含英文读音）
_TTS_LATIN_RE = re.compile(r"[a-z]+", re.IGNORECASE)


def normalize_tts_text(text: str) -> str:
    """TTS 前文本中文归一化（纯函数）。

    说明：
        菜谱步骤常含英文单位（2-10cm / 1cm³ / 盐 2g），qwen3-tts 会按英文
        读音朗读；先按领域替换表转中文单位，再兜底剔除剩余拉丁字母串，
        保证合成的语音全部为中文读法。数字/标点保留（中文音色按中文读）。

    参数：
        text：原始待合成文本。

    返回值：
        str：归一化后的文本（纯中文读法；空串透传）。

    异常：
        不抛出（纯字符串运算）。
    """
    result = text or ""
    for src, dst in _TTS_UNIT_REPLACEMENTS:
        result = result.replace(src, dst).replace(src.upper(), dst).replace(src.capitalize(), dst)
    result = _TTS_GRAM_RE.sub("克", result)
    # 数字区间读法：2-10 → 2到10（防 TTS 读成「减」）
    result = re.sub(r"(?<=\d)\s*-\s*(?=\d)", "到", result)
    result = _TTS_LATIN_RE.sub("", result)
    return result


@dataclass
class RecognizedItem:
    """单个视觉识别结果项（模型类）。

    属性：
        name：食材名（Mock 实现保证为 ingredient 表真实存在的名字）。
        confidence：置信度档位（high / low，前端按档位渲染勾选态）。
        ingredient_id：食材 ID（已与库内记录对齐时非空；mock 实现恒非空）。
    """

    name: str
    confidence: str  # 'high' | 'low'
    ingredient_id: int | None = None


class VisionProvider(ABC):
    """视觉识别提供方抽象接口（抽象类）。

    说明：
        阶段一仅 Mock 实现；真实模型（多模态 LLM / 端侧视觉）接入时继承本类，
        实现 recognize()，输入为原始图片字节。

    异常：
        实现方抛出的任何异常由调用方捕获并降级（识别结果置空 + degraded 标注）。
    """

    @abstractmethod
    def recognize(self, image_bytes: bytes) -> list[RecognizedItem]:
        """识别图片中的食材（抽象方法）。

        参数：
            image_bytes：图片文件原始字节（jpg/png 等，由调用方读取上传文件获得）。

        返回值：
            list[RecognizedItem]：识别出的食材项列表（可为空列表）。

        异常：
            实现方可抛出任意异常（网络/模型/解析失败），调用方统一降级。
        """
        raise NotImplementedError


class ASRProvider(ABC):
    """语音转写提供方抽象接口（抽象类）。

    说明：
        阶段一仅 Mock 实现；接入真实 ASR（微信同传 / 云厂商语音）时继承本类。

    异常：
        实现方抛出的任何异常由调用方捕获并降级（返回空文本 + degraded 标注）。
    """

    @abstractmethod
    def transcribe(self, audio_bytes: bytes) -> str:
        """将音频转写为文本（抽象方法）。

        参数：
            audio_bytes：音频文件原始字节（🔴 仅内存处理，调用方保证不落盘）。

        返回值：
            str：转写文本（可为空串）。

        异常：
            实现方可抛出任意异常，调用方统一降级。
        """
        raise NotImplementedError


class TTSProvider(ABC):
    """语音合成提供方抽象接口（抽象类）。

    说明：
        缺省 Mock 实现；真实 TTS（阿里云百炼 qwen3-tts-flash 等）接入时继承本类。

    异常：
        实现方抛出的任何异常由调用方捕获并降级（degraded 标注，前端静默不播）。
    """

    @abstractmethod
    def synthesize(self, text: str) -> tuple[str, str]:
        """将文本合成为音频（抽象方法）。

        参数：
            text：待合成文本（步骤描述等）。

        返回值：
            tuple[str, str]：(音频 base64, 音频格式)（如 ("SUQz...", "mp3")）。

        异常：
            实现方可抛出任意异常，调用方统一降级。
        """
        raise NotImplementedError

    def synthesize_stream(self, text: str) -> Iterator[bytes]:
        """流式合成音频（可选覆写，缺省退化为整段合成后单块产出）。

        参数：
            text：待合成文本。

        返回值：
            Iterator[bytes]：音频字节分片迭代器（按序拼接为完整音频文件）。

        异常：
            实现方可抛出任意异常，调用方统一降级。
        """
        audio_base64, _format = self.synthesize(text)
        if not audio_base64:
            return iter(())
        return iter([base64.b64decode(audio_base64)])


class MockVisionProvider(VisionProvider):
    """确定性 Mock 视觉识别实现（模型类）。

    说明：
        同一图片字节恒定返回同一结果（sha256 哈希驱动随机序列）：
        - 从 ingredient 表真实存在的常用子集中确定性挑 3~6 个食材；
        - 每项 75% 概率 high 置信、否则 low；
        - 库查询失败时返回空列表（上层不扣额度，等同全低置信路径）。
    """

    def recognize(self, image_bytes: bytes) -> list[RecognizedItem]:
        """确定性识别图片字节（函数）。

        参数：
            image_bytes：图片文件原始字节。

        返回值：
            list[RecognizedItem]：3~6 个识别项（库内常用子集不足时按实有数量返回）。

        异常：
            不抛出（数据库查询异常按空结果降级，由上层走「不扣额度」路径）。
        """
        if not image_bytes:
            return []
        available = self._load_common_ingredients()
        if not available:
            logger.warning("mock vision: 常用食材子集在 ingredient 表中为空，返回空识别结果")
            return []
        # 图片字节哈希驱动确定性随机序列（同一图片 → 同一识别结果）
        digest = hashlib.sha256(image_bytes).digest()
        rng = random.Random(int.from_bytes(digest[:8], "big"))
        count = min(len(available), 3 + rng.randint(0, 3))  # 3~6 个
        picked = rng.sample(available, count)
        items: list[RecognizedItem] = []
        for ing_id, name in picked:
            confidence = "high" if rng.random() < _HIGH_CONFIDENCE_PROBABILITY else "low"
            items.append(RecognizedItem(name=name, confidence=confidence, ingredient_id=int(ing_id)))
        return items

    def _load_common_ingredients(self) -> list[tuple[int, str]]:
        """查询 ingredient 表中常用子集真实存在的食材（函数）。

        返回值：
            list[tuple[int, str]]：(ingredient_id, name) 列表（保持 MOCK_VISION_COMMON_NAMES 顺序）。

        异常：
            不抛出（查询异常返回空列表，由 recognize 降级）。
        """
        try:
            with SessionLocal() as session:
                rows = session.execute(
                    select(Ingredient.id, Ingredient.name).where(
                        Ingredient.name.in_(MOCK_VISION_COMMON_NAMES),
                        Ingredient.is_active.is_(True),
                    )
                ).all()
            by_name = {str(name): int(ing_id) for ing_id, name in rows}
            return [(by_name[name], name) for name in MOCK_VISION_COMMON_NAMES if name in by_name]
        except Exception as exc:  # noqa: BLE001 —— mock 查库失败按空结果降级
            logger.warning("mock vision load ingredients failed: %s", exc)
            return []


class MockASRProvider(ASRProvider):
    """Mock 语音转写实现（模型类）。

    说明：
        不做任何音频解码，恒定返回固定演示文本（MOCK_ASR_TEXT），
        用于演示「拍照 → 语音 → 推荐」全链路。
    """

    def transcribe(self, audio_bytes: bytes) -> str:
        """返回固定演示文本（函数）。

        参数：
            audio_bytes：音频文件原始字节（仅校验非空，不做解码）。

        返回值：
            str：固定演示文本（空音频返回空串）。

        异常：
            无。
        """
        if not audio_bytes:
            return ""
        return MOCK_ASR_TEXT


class BailianASRProvider(ASRProvider):
    """阿里云百炼 qwen3-asr-flash 语音转写实现（模型类）。

    说明：
        经 OpenAI 兼容协议调用百炼非实时语音识别：音频 base64 编码为
        data URI 放入 input_audio 消息（编码后总大小须 ≤10MB，前端分段
        短句上传远低于该上限）；asr_options 指定中文 + 逆文本标准化
        （「下一步」等指令场景数字归一化）。网络/超时/鉴权失败统一抛
        LLMError，由路由层既有降级捕获（degraded=true 引导文字输入）。
        🔴 音频字节仅在内存中转 base64，绝不落盘（隐私红线）。

        配置同源：BASE_URL / API_KEY 空串时回落 VISION_BASE_URL /
        VISION_API_KEY（百炼同一凭证，与 EMBEDDING 回落策略一致）。
    """

    def __init__(self) -> None:
        """初始化客户端（函数）。

        说明：
            base_url/api_key 按 SPEECH_* 取值（空回落 VISION_*），模型名
            缺省 qwen3-asr-flash；客户端构造即创建，超时取 SPEECH_TIMEOUT_SECONDS。

        异常：
            LLMError：API Key 缺失（无可用凭证）时抛出。
        """
        base_url = settings.SPEECH_BASE_URL.strip() or settings.VISION_BASE_URL.strip()
        api_key = settings.SPEECH_API_KEY.strip() or settings.VISION_API_KEY.strip()
        if not api_key:
            raise LLMError("SPEECH/VISION API Key 均未配置，无法调用百炼语音识别")
        self._client = openai.OpenAI(
            api_key=api_key,
            base_url=base_url or None,
            timeout=float(settings.SPEECH_TIMEOUT_SECONDS),
        )
        self._model = settings.SPEECH_MODEL.strip() or "qwen3-asr-flash"

    def transcribe(self, audio_bytes: bytes) -> str:
        """将音频转写为文本（百炼 qwen3-asr-flash，函数）。

        参数：
            audio_bytes：音频文件原始字节（🔴 仅内存处理，调用方保证不落盘）。

        返回值：
            str：转写文本（模型输出空内容返回空串）。

        异常：
            LLMError：网络/超时/鉴权/响应解析失败时抛出（路由层统一降级）。
        """
        data_uri = "data:audio/wav;base64," + base64.b64encode(audio_bytes).decode("ascii")
        try:
            completion = self._client.chat.completions.create(
                model=self._model,
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "input_audio",
                                "input_audio": {"data": data_uri},
                            }
                        ],
                    }
                ],
                stream=False,
                extra_body={"asr_options": {"language": "zh", "enable_itn": True}},
            )
        except Exception as exc:  # noqa: BLE001 —— openai 异常统一包装为 LLMError
            raise LLMError(f"百炼语音识别调用失败: {exc}") from exc
        return str(completion.choices[0].message.content or "").strip()


class MockTTSProvider(TTSProvider):
    """Mock 语音合成实现（模型类）。

    说明：
        不做任何合成，恒返回空音频（前端按 degraded 静默跳过播放）。
    """

    def synthesize(self, text: str) -> tuple[str, str]:
        """返回空音频（函数）。

        参数：
            text：待合成文本（忽略）。

        返回值：
            tuple[str, str]：("", "wav")（空 base64，前端跳过播放）。

        异常：
            无。
        """
        return "", "wav"


class BailianTTSProvider(TTSProvider):
    """阿里云百炼 qwen3-tts-flash 语音合成实现（模型类）。

    说明：
        经 DashScope 多模态生成协议调用（官方 SDK SpeechSynthesizer 同源端点）：
        POST {base}/services/aigc/multimodal-generation/generation，
        input: {text, voice, format}；非流式响应直接携带 Base64 音频。
        文档存在多种响应形态（output.audio.data /
        output.choices[0].message.content[].audio.data），_extract_audio
        逐路容错提取；任何失败抛 LLMError 由路由层降级。
        配置同源：API_KEY 空串回落 SPEECH_API_KEY / VISION_API_KEY；
        BASE_URL 空串用 DashScope 默认端点。
    """

    # DashScope 多模态生成默认端点（qwen3-tts-flash 官方调用地址）
    _DEFAULT_BASE_URL = "https://dashscope.aliyuncs.com/api/v1"

    def __init__(self) -> None:
        """初始化客户端（函数）。

        说明：
            base_url 按 TTS_BASE_URL（空串用 DashScope 默认），api_key 按
            TTS_API_KEY → SPEECH_API_KEY → VISION_API_KEY 三级回落。

        异常：
            LLMError：API Key 缺失（无可用凭证）时抛出。
        """
        base_url = settings.TTS_BASE_URL.strip() or self._DEFAULT_BASE_URL
        api_key = (
            settings.TTS_API_KEY.strip()
            or settings.SPEECH_API_KEY.strip()
            or settings.VISION_API_KEY.strip()
        )
        if not api_key:
            raise LLMError("TTS/SPEECH/VISION API Key 均未配置，无法调用百炼语音合成")
        self._base_url = base_url.rstrip("/")
        self._api_key = api_key
        self._model = settings.TTS_MODEL.strip() or "qwen3-tts-flash"
        self._voice = settings.TTS_VOICE.strip() or "Cherry"

    def synthesize(self, text: str) -> tuple[str, str]:
        """将文本合成为音频（百炼 qwen3-tts-flash，函数）。

        参数：
            text：待合成文本（🔴 仅内存处理，不落盘）。

        返回值：
            tuple[str, str]：(音频 base64, 音频格式)。

        异常：
            LLMError：网络/超时/鉴权/响应解析失败时抛出（路由层统一降级）。
        """
        payload = {
            "model": self._model,
            "input": {"text": normalize_tts_text(text), "voice": self._voice, "format": "wav"},
        }
        try:
            resp = httpx.post(
                f"{self._base_url}/services/aigc/multimodal-generation/generation",
                headers={
                    "Authorization": f"Bearer {self._api_key}",
                    "Content-Type": "application/json",
                },
                json=payload,
                timeout=float(settings.TTS_TIMEOUT_SECONDS),
            )
            resp.raise_for_status()
        except Exception as exc:  # noqa: BLE001 —— httpx 异常统一包装为 LLMError
            raise LLMError(f"百炼语音合成调用失败: {exc}") from exc
        try:
            body = resp.json()
        except ValueError as exc:
            raise LLMError(f"百炼语音合成响应非 JSON: {exc}") from exc
        audio_base64, audio_format = self._extract_audio(body)
        audio_url = self._extract_audio_url(body)
        if not audio_base64 and audio_url:
            # 实测 qwen3-tts-flash 返回 OSS 临时 URL 而非 base64：服务端拉取转 base64
            # （🔴 仅内存中转，不落盘；URL 有效期短，不透传给前端避免过期失效）
            try:
                dl = httpx.get(audio_url, timeout=float(settings.TTS_TIMEOUT_SECONDS))
                dl.raise_for_status()
                audio_base64 = base64.b64encode(dl.content).decode("ascii")
            except Exception as exc:  # noqa: BLE001 —— 下载失败统一降级
                raise LLMError(f"百炼语音合成音频下载失败: {exc}") from exc
        if not audio_base64:
            raise LLMError(f"百炼语音合成响应中未找到音频数据: {str(body)[:200]}")
        return audio_base64, audio_format or "wav"

    def synthesize_stream(self, text: str) -> Iterator[bytes]:
        """流式合成音频（SSE 边合成边产出，函数）。

        说明：
            携 X-DashScope-SSE: enable 头请求，逐行解析 SSE data JSON，
            增量音频 base64（audio.delta / audio.data 等形态容错）解码后
            即刻产出，前端可边收边播；请求格式 mp3（浏览器可渐进播放）。
            🔴 迭代期任何异常（建连失败/限流 429/解析失败）就地记日志并
            终止产出——流式响应已发出，异常穿透会打穿 ASGI 致进程异常。

        参数：
            text：待合成文本（🔴 仅内存处理，不落盘）。

        返回值：
            Iterator[bytes]：音频字节分片迭代器。

        异常：
            不抛出（流式响应无法变更状态码，错误就地降级为提前收流）。
        """
        try:
            yield from self._synthesize_stream_impl(text)
        except Exception as exc:  # noqa: BLE001 —— 流式响应中异常只能优雅收流
            logger.warning("tts stream aborted: %s", exc)

    def _synthesize_stream_impl(self, text: str) -> Iterator[bytes]:
        """流式合成实现（内部函数，异常由 synthesize_stream 捕获）。"""
        payload = {
            "model": self._model,
            "input": {"text": normalize_tts_text(text), "voice": self._voice, "format": "mp3"},
        }
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
            "X-DashScope-SSE": "enable",
        }
        with httpx.stream(
            "POST",
            f"{self._base_url}/services/aigc/multimodal-generation/generation",
            headers=headers,
            json=payload,
            timeout=float(settings.TTS_TIMEOUT_SECONDS),
        ) as resp:
            if resp.status_code != 200:
                raise LLMError(f"百炼语音合成流式调用失败: HTTP {resp.status_code}")
            for line in resp.iter_lines():
                if not line.startswith("data:"):
                    continue
                data = line[len("data:"):].strip()
                if not data or data == "[DONE]":
                    continue
                try:
                    chunk = json.loads(data)
                except ValueError:
                    continue
                for piece in self._extract_stream_audio(chunk):
                    if piece:
                        yield piece

    @staticmethod
    def _extract_stream_audio(chunk: dict) -> list[bytes]:
        """从单个 SSE 事件中提取增量音频字节（纯内部函数）。

        说明：
            容错候选：output.audio.delta（流式增量形态）、output.audio.data、
            output.choices[0].message.content[].audio.{delta,data}。

        参数：
            chunk：单条 SSE data JSON 对象。

        返回值：
            list[bytes]：解码后的音频分片（无音频返回空列表）。

        异常：
            不抛出（base64 非法片段跳过）。
        """
        output = chunk.get("output") or {}
        candidates: list[str] = []
        audio = output.get("audio") or {}
        if isinstance(audio, dict):
            candidates.append(str(audio.get("delta") or ""))
            candidates.append(str(audio.get("data") or ""))
        for choice in output.get("choices") or []:
            message = choice.get("message") or {}
            content = message.get("content")
            if isinstance(content, list):
                for item in content:
                    if isinstance(item, dict):
                        item_audio = item.get("audio") or {}
                        if isinstance(item_audio, dict):
                            candidates.append(str(item_audio.get("delta") or ""))
                            candidates.append(str(item_audio.get("data") or ""))
        pieces: list[bytes] = []
        for cand in candidates:
            if cand:
                try:
                    pieces.append(base64.b64decode(cand))
                except (ValueError, TypeError):
                    continue
        return pieces

    @staticmethod
    def _extract_audio_url(body: dict) -> str:
        """从容错提取响应中的音频下载 URL（纯内部函数）。

        参数：
            body：响应 JSON 对象。

        返回值：
            str：音频 URL；未命中返回空串。

        异常：
            不抛出（键缺失按空串处理）。
        """
        output = body.get("output") or {}
        audio = output.get("audio") or {}
        return str(audio.get("url") or "")

    @staticmethod
    def _extract_audio(body: dict) -> tuple[str, str]:
        """从容错提取响应中的 Base64 音频与格式（纯内部函数）。

        说明：
            逐路尝试文档出现过的响应形态：
            ① output.choices[0].message.content 数组内 {type:audio,audio:{data,format}}；
            ② output.audio.{data,format}（SDK SpeechSynthesizer 非流式形态）；
            ③ output.choices[0].text（旧形态直接放 base64）。

        参数：
            body：响应 JSON 对象。

        返回值：
            tuple[str, str]：(音频 base64, 格式)；未命中返回 ("", "")。

        异常：
            不抛出（键缺失按空串处理）。
        """
        output = body.get("output") or {}
        choices = output.get("choices") or []
        for choice in choices:
            message = choice.get("message") or {}
            content = message.get("content")
            if isinstance(content, list):
                for item in content:
                    if isinstance(item, dict):
                        audio = item.get("audio") or {}
                        data = str(audio.get("data") or "")
                        if data:
                            return data, str(audio.get("format") or "wav")
            text = choice.get("text")
            if isinstance(text, str) and len(text) > 64:
                return text, "wav"
        audio = output.get("audio") or {}
        data = str(audio.get("data") or "")
        if data:
            return data, str(audio.get("format") or "wav")
        return "", ""


# ---------------------------------------------------------------------------
# 真实视觉模型（VLM）相关常量与辅助（spec：integrate-vlm-report-actions A 节）
# ---------------------------------------------------------------------------

# VLM system prompt（🔴 RL-3 红线：显式禁止输出任何可食性/安全性结论）
VLM_SYSTEM_PROMPT = (
    "你是冰箱食材识别助手。请只输出一个 JSON 数组，不要输出任何解释文字。"
    "数组每一项形如 {\"name\": \"食材名\"}，name 使用中文家常叫法"
    "（如「番茄」「鸡蛋」「猪五花肉」）。"
    "只列出照片中的可食用食材，忽略容器、包装、电器、人体、保鲜盒、瓶罐等非食材物体。"
    "最多列出 12 项。"
    "🔴 严格禁止输出任何关于可食性或安全性判断的表述（如「能吃」「不能吃」「变质」「安全」「危险」"
    "「新鲜」「过期」等），你只负责识别食材名字，不判断状态。"
    "如果认不出任何食材，输出空数组 []。"
)

# VLM user prompt（简短提示）
VLM_USER_PROMPT = "识别这张冰箱照片中的食材。"

# 噪声词表（名字含任一词即丢弃；在向量路之前过滤，防「保鲜盒」等非食材混入）
_NOISE_WORDS: frozenset[str] = frozenset({
    "保鲜盒", "保鲜袋", "保鲜膜", "冰箱", "冷藏", "冷冻", "塑料袋", "塑料",
    "瓶盖", "包装", "纸箱", "抹布", "手", "宠物", "瓶", "盒", "罐头盒",
    "标签", "菜板", "灶台", "隔板",
})

# 名称长度上限（超长视为噪声描述而非食材名）
_MAX_NAME_LENGTH = 12

# 纯 ASCII 品牌样的长度下限（无中文字符且长度超过该值 → 视为品牌/英文噪声丢弃）
_ASCII_NOISE_MIN_LENGTH = 6

# 向量相似度阈值（hash 嵌入点积即余弦）：≥0.85 high / 0.60~0.85 low / <0.60 丢弃
_SIM_HIGH = 0.85
_SIM_LOW = 0.60

# 数量+量词剥离正则（首尾各一；单位含中英文，英文单位支持 ml/mL/kg/KG/g/G）
_QUANTITY_UNITS = r"(毫升|千克|公斤|[个只根条盒袋瓶颗把块片罐包份箱板听支束串滴勺碗杯斤两克]|[mM][lL]|[kK][gG]|[gG])"
_QUANTITY_TAIL_RE = re.compile(
    r"[0-9０-９一二两三四五六七八九十百千万半几]+\s*" + _QUANTITY_UNITS + r"\s*$"
)
_QUANTITY_HEAD_RE = re.compile(
    r"^[0-9０-９一二两三四五六七八九十百千万半几]+\s*" + _QUANTITY_UNITS + r"\s*"
)

# 库内食材向量模块级缓存：键=(活跃食材行数, 最大ID)，食材表变化才重算
_ING_VEC_CACHE: dict[tuple[int, int], tuple[list[tuple[int, str]], list[list[float]]]] = {}
_ING_VEC_LOCK = threading.Lock()


def _strip_quantity(name: str) -> str:
    """剥离食材名首尾的「数量+量词」片段（纯函数）。

    说明：
        如「鸡蛋 6个」→「鸡蛋」、「一盒鸡蛋」→「鸡蛋」、「6个鸡蛋」→「鸡蛋」；
        循环剥离直到首尾均无「数字+量词」模式；剥离后为空则返回空串（由调用方丢弃）。
        中间夹量词的情况（如「西红柿炒鸡蛋」中的「蛋」）不受影响——仅处理首尾。

    参数：
        name：原始食材名（已 strip）。

    返回值：
        str：剥离数量量词后的名字（可能为空串）。

    异常：
        无。
    """
    result = name
    # 循环剥离尾部（如「鸡蛋 6个」→「鸡蛋」）与前导（如「一盒鸡蛋」→「鸡蛋」）
    while True:
        stripped = _QUANTITY_TAIL_RE.sub("", result).strip()
        if stripped != result:
            result = stripped
            if not result:
                return ""
            continue
        stripped = _QUANTITY_HEAD_RE.sub("", result).strip()
        if stripped != result:
            result = stripped
            if not result:
                return ""
            continue
        break
    return result


def _is_noise(name: str) -> bool:
    """判定候选名是否为噪声（纯函数，在向量路之前调用）。

    说明：
        三条判据（命中任一即噪声）：①名字含噪声词子串（保鲜盒/冰箱/瓶/盒/手等，
        防容器、包装、人体部位混入）；②长度 >12（超长多为描述性句子而非食材名）；
        ③纯 ASCII 品牌样（无中文字符且长度 >6，如「Coca-Cola」）。

    参数：
        name：候选食材名（已剥数量量词）。

    返回值：
        bool：True 噪声（丢弃）/ False 正常候选。

    异常：
        无。
    """
    if any(word in name for word in _NOISE_WORDS):
        return True
    if len(name) > _MAX_NAME_LENGTH:
        return True
    # 无任何中文字符且超长的 ASCII 串 → 品牌样噪声
    if len(name) > _ASCII_NOISE_MIN_LENGTH and not any("\u4e00" <= ch <= "\u9fff" for ch in name):
        return True
    return False


def _extract_json_array(text: str) -> list:
    """从 VLM 原始输出中容错解析出 JSON 数组（独立纯函数，便于单测）。

    说明：
        剥离 ```json 围栏与前后杂文本：定位首个 '[' 到最后一个 ']' 截取，
        json.loads 失败（截取后仍非法 / 无数组结构 / 顶层非 list）抛 LLMError，
        由路由层既有降级捕获（degraded=true 不扣额度）。

    参数：
        text：VLM 原始输出文本（可能含围栏/解释文字）。

    返回值：
        list：解析出的 JSON 数组（原始元素，name 提取在归一化阶段处理）。

    异常：
        LLMError：文本中无 '[' / 截取片段非法 JSON / 顶层不是数组时抛出。
    """
    start = text.find("[")
    end = text.rfind("]")
    if start < 0 or end <= start:
        raise LLMError(f"VLM 输出中未找到 JSON 数组: {text[:120]!r}")
    snippet = text[start : end + 1]
    try:
        data = json.loads(snippet)
    except (json.JSONDecodeError, ValueError) as exc:
        raise LLMError(f"VLM 输出 JSON 解析失败: {exc}") from exc
    if not isinstance(data, list):
        raise LLMError("VLM 输出顶层不是 JSON 数组")
    return data


def _load_ingredient_vectors() -> tuple[list[tuple[int, str]], list[list[float]]]:
    """加载库内全部活跃食材名并计算向量（模块级缓存，函数）。

    说明：
        缓存键 = (活跃食材行数, 最大 ID)，食材表增删后键变化即重算（种子导入、
        管理端增删食材后自动失效）；向量由 get_embedding_provider() 产出
        （1024 维 L2 归一化，点积即余弦）。

    返回值：
        tuple[list[tuple[int, str]], list[list[float]]]：(id, name) 行列表
        与按行序对齐的归一化向量列表。

    异常：
        查询/嵌入异常向上抛出（由调用方捕获降级，绝不阻断主链路）。
    """
    with SessionLocal() as session:
        rows = session.execute(
            select(Ingredient.id, Ingredient.name).where(Ingredient.is_active.is_(True))
        ).all()
    normalized_rows = [(int(ing_id), str(name)) for ing_id, name in rows]
    key = (len(normalized_rows), max((ing_id for ing_id, _ in normalized_rows), default=0))
    cached = _ING_VEC_CACHE.get(key)
    if cached is not None:
        return cached
    vectors = (
        get_embedding_provider().embed([name for _, name in normalized_rows])
        if normalized_rows
        else []
    )
    with _ING_VEC_LOCK:
        _ING_VEC_CACHE.clear()  # 仅保留最新键一份，防食材表频繁增删导致膨胀
        _ING_VEC_CACHE[key] = (normalized_rows, vectors)
    return normalized_rows, vectors


class MultimodalVisionProvider(VisionProvider):
    """真实视觉模型（VLM）识别实现（模型类，spec：真实视觉识别 provider）。

    说明：
        两步走：_call_vlm 经 LLMClient.chat_with_image 调用阿里云百炼
        qwen omni 系列多模态模型（网络/超时/鉴权/JSON 解析失败 → 抛异常，
        路由层既有降级捕获 → degraded=true 不扣额度）；_normalize 将模型
        输出的原始名字归一化为 ingredient 表真实存在的识别项（解析成功但
        归一化后为空 → 返回 []，走全低置信不扣额度路径）。
        🔴 库外名字绝不返回（否则 confirm 校验必失败，用户感知
        「认出来却用不了」）；🔴 输出仅含 name/confidence/ingredient_id，
        绝不携带任何可食性/安全性结论（RL-3 红线，system prompt 已显式禁止）。

    属性：
        无实例状态（库内向量缓存在模块级 _ING_VEC_CACHE）。
    """

    def recognize(self, image_bytes: bytes) -> list[RecognizedItem]:
        """识别图片中的食材（VLM 两步走，函数）。

        参数：
            image_bytes：图片文件原始字节（jpg/png 等，仅内存处理不落盘）。

        返回值：
            list[RecognizedItem]：识别项列表（每项 name 必为 ingredient 表
            真实存在的名字或别名命中；可为空列表）。

        异常：
            LLMError 及底层网络异常：VLM 调用失败或 JSON 解析失败时向上抛出
            （路由层降级 degraded=true 不扣额度）；归一化阶段自身不抛出。
        """
        if not image_bytes:
            return []
        raw_text = self._call_vlm(image_bytes)
        raw_entries = _extract_json_array(raw_text)
        return self._normalize(raw_entries)

    def _call_vlm(self, image_bytes: bytes) -> str:
        """调用 VLM 获取原始输出文本（函数）。

        参数：
            image_bytes：图片文件原始字节。

        返回值：
            str：VLM 输出文本（可能含 JSON 围栏/解释文字，由解析层容错）。

        异常：
            LLMError：网络/超时/鉴权/客户端异常时抛出（chat_with_image 统一包装）。
        """
        result = get_llm_client().chat_with_image(
            system=VLM_SYSTEM_PROMPT,
            user=VLM_USER_PROMPT,
            image_bytes=image_bytes,
        )
        return result.content

    def _normalize(self, raw: list) -> list[RecognizedItem]:
        """将 VLM 原始输出归一化为库内真实识别项（纯内部方法，永不抛出）。

        说明：
            处理链：提取 name → strip → 剥离首尾「数量+量词」（鸡蛋 6个→鸡蛋）
            → 噪声过滤（噪声词/超长/纯 ASCII 品牌样，在向量路之前）→ 三路归一化
            （① ingredient.name 精确命中→high；② IngredientAlias.alias 命中→high；
            ③ 向量最近邻 ≥0.85→high、0.60~0.85→low、<0.60 丢弃）→ 同名去重
            （只留第一个）→ 截断 settings.VISION_MAX_ITEMS。embedding 查询失败
            时跳过向量路（记 WARNING），已命中的精确/别名项照常返回。

        参数：
            raw：_extract_json_array 解析出的原始数组元素（dict 或标量均可容错）。

        返回值：
            list[RecognizedItem]：归一化后的识别项列表（可为空列表）。

        异常：
            不抛出（embedding 失败按跳过向量路降级）。
        """
        # ① 库内映射表：精确名 → id；别名 → id
        exact_map, alias_map = self._load_name_maps()
        # ② 预处理 + 噪声过滤 + 精确/别名两路先命中
        candidates: list[str] = []  # 进入向量路的候选名（保序）
        items: list[RecognizedItem] = []
        seen: set[str] = set()  # 同名去重（含已命中与候选）
        for entry in raw:
            name = self._entry_name(entry)
            if not name:
                continue
            name = _strip_quantity(name.strip())
            if not name or name in seen or _is_noise(name):
                continue
            seen.add(name)
            if name in exact_map:
                items.append(RecognizedItem(name=name, confidence="high", ingredient_id=exact_map[name]))
                continue
            if name in alias_map:
                items.append(RecognizedItem(name=name, confidence="high", ingredient_id=alias_map[name]))
                continue
            candidates.append(name)
        # ③ 向量最近邻路（≥0.85 high / 0.60~0.85 low / <0.60 丢弃）
        for item in self._vector_match(candidates):
            items.append(item)
        # ④ 同名去重（向量路与精确路理论不重，兜底保序去重）+ 截断上限
        deduped: list[RecognizedItem] = []
        deduped_seen: set[str] = set()
        for item in items:
            if item.name in deduped_seen:
                continue
            deduped_seen.add(item.name)
            deduped.append(item)
        return deduped[: max(0, int(settings.VISION_MAX_ITEMS))]

    @staticmethod
    def _entry_name(entry) -> str:
        """从 VLM 数组元素中容错提取食材名（函数）。

        说明：
            元素为 dict 时取 name 字段（其他字段如「可食性」一律忽略，
            🔴 RL-3：输出绝不携带任何可食性/安全性结论）；元素为标量时按
            字符串处理；其余类型返回空串丢弃。

        参数：
            entry：JSON 数组元素（任意类型）。

        返回值：
            str：食材名（无效元素返回空串）。

        异常：
            无。
        """
        if isinstance(entry, dict):
            value = entry.get("name")
            return str(value).strip() if isinstance(value, (str, int, float)) else ""
        if isinstance(entry, str):
            return entry.strip()
        return ""

    @staticmethod
    def _load_name_maps() -> tuple[dict[str, int], dict[str, int]]:
        """加载 ingredient / ingredient_alias 两张名称映射表（函数）。

        返回值：
            tuple[dict[str, int], dict[str, int]]：(精确名→id, 别名→id) 两个映射。

        异常：
            查询异常向上抛出（由 _normalize 的调用链在 recognize 阶段抛出，
            走路由降级——映射表加载失败意味着库不可用，识别无从谈起）。
        """
        with SessionLocal() as session:
            ing_rows = session.execute(
                select(Ingredient.id, Ingredient.name).where(Ingredient.is_active.is_(True))
            ).all()
            alias_rows = session.execute(
                select(IngredientAlias.alias, IngredientAlias.ingredient_id)
            ).all()
        exact_map = {str(name): int(ing_id) for ing_id, name in ing_rows}
        alias_map = {str(alias): int(ing_id) for alias, ing_id in alias_rows}
        return exact_map, alias_map

    def _vector_match(self, candidates: list[str]) -> list[RecognizedItem]:
        """向量最近邻归一化路（函数）。

        说明：
            对候选名与库内全部活跃食材名各算一次嵌入（库内向量走模块级缓存），
            点积即余弦；取最大相似度：≥0.85→high、0.60~0.85→low（均带
            ingredient_id）、<0.60→丢弃（库外名字绝不返回）。embedding 调用
            失败时记 WARNING 返回空列表（不抛出，精确/别名已命中项不受影响）。

        参数：
            candidates：进入向量路的候选名列表（已过噪声过滤与精确/别名匹配）。

        返回值：
            list[RecognizedItem]：向量命中的识别项列表（失败/无命中返回空列表）。

        异常：
            不抛出（embedding 异常捕获降级为空结果）。
        """
        if not candidates:
            return []
        try:
            ing_rows, ing_vectors = _load_ingredient_vectors()
            if not ing_rows:
                return []
            cand_vectors = get_embedding_provider().embed(candidates)
        except Exception as exc:  # noqa: BLE001 —— 向量路失败降级，不阻断已命中项
            logger.warning("vlm vector match failed: %s", exc)
            return []
        items: list[RecognizedItem] = []
        for name, cand_vec in zip(candidates, cand_vectors, strict=True):
            best_id: int | None = None
            best_score = 0.0
            for (ing_id, _ing_name), ing_vec in zip(ing_rows, ing_vectors, strict=True):
                score = sum(a * b for a, b in zip(cand_vec, ing_vec, strict=True))
                if score > best_score:
                    best_score = score
                    best_id = ing_id
            if best_id is None or best_score < _SIM_LOW:
                continue  # <0.60：库外名字丢弃，绝不返回
            confidence = "high" if best_score >= _SIM_HIGH else "low"
            items.append(RecognizedItem(name=name, confidence=confidence, ingredient_id=int(best_id)))
        return items


def _build_vision_provider() -> VisionProvider:
    """按 settings（.env）构建视觉识别 provider 实例（函数）。

    说明：
        读 settings.VISION_PROVIDER（pydantic-settings 自 .env 加载，缺省 mock）：
        'mock' → MockVisionProvider、'vlm' → MultimodalVisionProvider（真实视觉模型，
        阿里云百炼 qwen omni 系列，🔴 库外名字绝不返回、绝不出具可食性/安全性结论）；
        未知取值告警并回退 mock；构建异常同样回退 mock，保证识别链路可降级可回退。
        （修复记录：原 os.getenv("VISION_PROVIDER") 读进程环境变量，而 pydantic-settings
        从 .env 读的值不注入 os.environ，导致服务进程恒为 mock、VLM 配置被绕过；
        测试隔离依赖 conftest 顶层 os.environ.setdefault 先于 settings 单例创建，
        改读 settings 后隔离语义不变。）

    返回值：
        VisionProvider：视觉识别 provider 实例。

    异常：
        不抛出（任何异常回退 Mock 实现，保证识别链路可降级）。
    """
    name = (settings.VISION_PROVIDER or "mock").strip().lower() or "mock"
    try:
        if name == "mock":
            return MockVisionProvider()
        if name == "vlm":
            return MultimodalVisionProvider()
    except Exception as exc:  # noqa: BLE001 —— 构建失败回退 mock
        logger.warning("build vision provider %s failed, fallback to mock: %s", name, exc)
        return MockVisionProvider()
    logger.warning("未知的 VISION_PROVIDER=%s，回退 mock（真实模型接入后在此扩展工厂分支）", name)
    return MockVisionProvider()


def _build_speech_provider() -> ASRProvider:
    """按 settings（.env）构建语音转写 provider 实例（函数）。

    说明：
        读 settings.SPEECH_PROVIDER（pydantic-settings 自 .env 加载，缺省 mock；
        与 VISION 同口径——os.getenv 读不到 .env 值，必须走 settings）：
        'mock' → MockASRProvider、'bailian' → BailianASRProvider（百炼
        qwen3-asr-flash）；未知取值告警并回退 mock；构建异常同样回退 mock，
        保证语音链路可降级可回退。

    返回值：
        ASRProvider：语音转写 provider 实例。

    异常：
        不抛出（任何异常回退 Mock 实现）。
    """
    name = (settings.SPEECH_PROVIDER or "mock").strip().lower() or "mock"
    try:
        if name == "mock":
            return MockASRProvider()
        if name == "bailian":
            return BailianASRProvider()
    except Exception as exc:  # noqa: BLE001 —— 构建失败回退 mock
        logger.warning("build speech provider %s failed, fallback to mock: %s", name, exc)
        return MockASRProvider()
    logger.warning("未知的 SPEECH_PROVIDER=%s，回退 mock（真实模型接入后在此扩展工厂分支）", name)
    return MockASRProvider()


def _build_tts_provider() -> TTSProvider:
    """按 settings（.env）构建语音合成 provider 实例（函数）。

    说明：
        读 settings.TTS_PROVIDER（pydantic-settings 自 .env 加载，缺省 mock）：
        'mock' → MockTTSProvider、'bailian' → BailianTTSProvider（百炼
        qwen3-tts-flash）；未知取值告警并回退 mock；构建异常同样回退 mock，
        保证朗读链路可降级可回退（失败静默不影响步骤引导主链路）。

    返回值：
        TTSProvider：语音合成 provider 实例。

    异常：
        不抛出（任何异常回退 Mock 实现）。
    """
    name = (settings.TTS_PROVIDER or "mock").strip().lower() or "mock"
    try:
        if name == "mock":
            return MockTTSProvider()
        if name == "bailian":
            return BailianTTSProvider()
    except Exception as exc:  # noqa: BLE001 —— 构建失败回退 mock
        logger.warning("build tts provider %s failed, fallback to mock: %s", name, exc)
        return MockTTSProvider()
    logger.warning("未知的 TTS_PROVIDER=%s，回退 mock", name)
    return MockTTSProvider()


# ---- 进程级单例工厂（与 llm.py 的 get_llm_client 同款加锁单例风格）----
_vision_provider: VisionProvider | None = None
_vision_lock = threading.Lock()
_speech_provider: ASRProvider | None = None
_speech_lock = threading.Lock()
_tts_provider: TTSProvider | None = None
_tts_lock = threading.Lock()


def get_vision_provider() -> VisionProvider:
    """获取视觉识别 provider 进程级单例（函数）。

    说明：
        首次调用读取环境变量 VISION_PROVIDER 并构建（缺省 mock）；
        小程序阶段接入真实视觉模型只需实现 VisionProvider 并扩展工厂分支。

    返回值：
        VisionProvider：全局唯一视觉识别 provider 实例。

    异常：
        不抛出（构建异常回退 Mock 实现）。
    """
    global _vision_provider
    if _vision_provider is None:
        with _vision_lock:
            if _vision_provider is None:
                _vision_provider = _build_vision_provider()
    return _vision_provider


def get_speech_provider() -> ASRProvider:
    """获取语音转写 provider 进程级单例（函数）。

    说明：
        首次调用读取环境变量 SPEECH_PROVIDER 并构建（缺省 mock）。

    返回值：
        ASRProvider：全局唯一语音转写 provider 实例。

    异常：
        不抛出（构建异常回退 Mock 实现）。
    """
    global _speech_provider
    if _speech_provider is None:
        with _speech_lock:
            if _speech_provider is None:
                _speech_provider = _build_speech_provider()
    return _speech_provider


def get_tts_provider() -> TTSProvider:
    """获取语音合成 provider 进程级单例（函数）。

    说明：
        首次调用读取 settings.TTS_PROVIDER 并构建（缺省 mock）。

    返回值：
        TTSProvider：全局唯一语音合成 provider 实例。

    异常：
        不抛出（构建异常回退 Mock 实现）。
    """
    global _tts_provider
    if _tts_provider is None:
        with _tts_lock:
            if _tts_provider is None:
                _tts_provider = _build_tts_provider()
    return _tts_provider


__all__ = [
    "RecognizedItem",
    "VisionProvider",
    "ASRProvider",
    "TTSProvider",
    "MockVisionProvider",
    "MockASRProvider",
    "MockTTSProvider",
    "BailianASRProvider",
    "BailianTTSProvider",
    "MultimodalVisionProvider",
    "VLM_SYSTEM_PROMPT",
    "VLM_USER_PROMPT",
    "MOCK_ASR_TEXT",
    "MOCK_VISION_COMMON_NAMES",
    "normalize_tts_text",
    "get_vision_provider",
    "get_speech_provider",
    "get_tts_provider",
]
