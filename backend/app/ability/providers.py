"""识别与语音能力适配器模块（provider 模式，spec 模块 D 后半）。

职责：
    定义视觉识别与语音转写的抽象接口及阶段一 Mock 实现：
    - VisionProvider / RecognizedItem：视觉识别接口（图片字节 → 食材识别项列表）；
    - MockVisionProvider：确定性 mock——按图片字节 sha256 哈希从 ingredient 表常用
      子集中确定性挑 3~6 个（75% 概率 high 置信）；只返回 ingredient 表真实存在的
      食材名（否则 confirm 校验会失败）；
    - ASRProvider：语音转写接口（音频字节 → 文本）；
    - MockASRProvider：返回固定演示文本（不落盘、无网络调用）；
    - get_vision_provider / get_speech_provider：进程级单例工厂，读环境变量
      VISION_PROVIDER / SPEECH_PROVIDER（缺省 mock）。

接入真实模型：
    小程序阶段接入真实视觉模型只需实现 VisionProvider（真实 ASR 同理实现
    ASRProvider），并在工厂 _build_vision_provider / _build_speech_provider 中
    按环境变量扩展分支即可，调用方（vision/speech 路由）零改动。
    provider 内任何异常由上层（路由层）捕获后降级：识别降级为手动选食材、
    语音降级为文字输入，绝不向上抛出阻断主链路。
"""

from __future__ import annotations

import hashlib
import os
import random
import threading
from abc import ABC, abstractmethod
from dataclasses import dataclass

from sqlalchemy import select

from app.core.db import SessionLocal
from app.core.logging import get_logger
from app.models import Ingredient

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


def _build_vision_provider() -> VisionProvider:
    """按环境变量构建视觉识别 provider 实例（函数）。

    说明：
        读环境变量 VISION_PROVIDER（缺省 mock）；未知取值告警并回退 mock。
        小程序阶段接入真实视觉模型只需在此扩展工厂分支。

    返回值：
        VisionProvider：视觉识别 provider 实例。

    异常：
        不抛出（任何异常回退 Mock 实现，保证识别链路可降级）。
    """
    name = (os.getenv("VISION_PROVIDER") or "mock").strip().lower() or "mock"
    try:
        if name == "mock":
            return MockVisionProvider()
    except Exception as exc:  # noqa: BLE001 —— 构建失败回退 mock
        logger.warning("build vision provider %s failed, fallback to mock: %s", name, exc)
    if name != "mock":
        logger.warning("未知的 VISION_PROVIDER=%s，回退 mock（真实模型接入后在此扩展工厂分支）", name)
    return MockVisionProvider()


def _build_speech_provider() -> ASRProvider:
    """按环境变量构建语音转写 provider 实例（函数）。

    说明：
        读环境变量 SPEECH_PROVIDER（缺省 mock）；未知取值告警并回退 mock。

    返回值：
        ASRProvider：语音转写 provider 实例。

    异常：
        不抛出（任何异常回退 Mock 实现）。
    """
    name = (os.getenv("SPEECH_PROVIDER") or "mock").strip().lower() or "mock"
    try:
        if name == "mock":
            return MockASRProvider()
    except Exception as exc:  # noqa: BLE001 —— 构建失败回退 mock
        logger.warning("build speech provider %s failed, fallback to mock: %s", name, exc)
    if name != "mock":
        logger.warning("未知的 SPEECH_PROVIDER=%s，回退 mock（真实模型接入后在此扩展工厂分支）", name)
    return MockASRProvider()


# ---- 进程级单例工厂（与 llm.py 的 get_llm_client 同款加锁单例风格）----
_vision_provider: VisionProvider | None = None
_vision_lock = threading.Lock()
_speech_provider: ASRProvider | None = None
_speech_lock = threading.Lock()


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


__all__ = [
    "RecognizedItem",
    "VisionProvider",
    "ASRProvider",
    "MockVisionProvider",
    "MockASRProvider",
    "MOCK_ASR_TEXT",
    "MOCK_VISION_COMMON_NAMES",
    "get_vision_provider",
    "get_speech_provider",
]
