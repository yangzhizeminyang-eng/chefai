"""LLM 客户端模块（OpenAI 兼容协议）。

职责：
    封装 openai.OpenAI 客户端对接 DeepSeek（base_url/api_key/model/超时均来自 settings），
    提供 chat() 补全入口与 token/成本记录；
    另提供 chat_with_image() 视觉多模态补全入口（独立 VISION_* 配置的内部客户端，
    与 DeepSeek 文本客户端完全分离，qwen omni 系列统一走流式收集）；
    任何调用异常统一抛 LLMError，由调用方（supervisor / node_free_qa /
    providers.MultimodalVisionProvider）负责降级，
    客户端本身不做重试（避免风控链路等待）。

成本口径：
    按「占位单价常量」估算（人民币/百万 token）——当前按 DeepSeek 公开报价量级设定：
    输入 2 元/百万、输出 8 元/百万；ⓘ 实际单价请按 DeepSeek 官方报价页调整常量。
"""

from __future__ import annotations

import base64
import threading
from dataclasses import dataclass

import openai

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# 占位单价常量（人民币 元/百万 token）——ⓘ 按 DeepSeek 实际报价调整
# ---------------------------------------------------------------------------
PRICE_INPUT_CNY_PER_M = 2.0   # 输入 token 单价（占位）
PRICE_OUTPUT_CNY_PER_M = 8.0  # 输出 token 单价（占位）


class LLMError(Exception):
    """LLM 调用失败异常（模型类）。

    说明：
        网络/超时/鉴权/解析等一切失败均包装为本异常向上抛出，
        调用方据此执行降级（意图识别→关键词兜底；问答→固定话术）。

    属性：
        message：错误描述。
    """

    def __init__(self, message: str) -> None:
        """构造异常（函数）。

        参数：
            message：错误描述。

        返回值：
            None。

        异常：
            无。
        """
        super().__init__(message)
        self.message = message


@dataclass
class LLMResult:
    """LLM 补全结果（模型类）。

    属性：
        content：模型输出文本。
        prompt_tokens：输入 token 数。
        completion_tokens：输出 token 数。
        model：实际使用的模型名。
    """

    content: str
    prompt_tokens: int
    completion_tokens: int
    model: str

    @property
    def cost_cents(self) -> float:
        """按占位单价估算本次调用成本（分）（函数）。

        说明：
            cost_cents = 输入 token/1e6 × 输入单价 + 输出 token/1e6 × 输出单价（元），
            再 ×100 转为分。

        返回值：
            float：估算成本（人民币分，保留 4 位小数）。

        异常：
            无。
        """
        cost_cny = (
            self.prompt_tokens / 1_000_000 * PRICE_INPUT_CNY_PER_M
            + self.completion_tokens / 1_000_000 * PRICE_OUTPUT_CNY_PER_M
        )
        return round(cost_cny * 100, 4)


class LLMClient:
    """OpenAI 兼容大模型客户端（模型类）。

    说明：
        线程安全（openai.OpenAI 客户端线程安全，进程级单例复用）；
        chat() / chat_with_image() 失败统一抛 LLMError，不做内部重试。

    属性：
        _client：openai.OpenAI 实例（DeepSeek 文本客户端，构造即创建）。
        _vision_client：openai.OpenAI 实例（视觉模型客户端，首次调用
            chat_with_image 时按 VISION_* 配置懒加载创建，与文本客户端配置完全分离）。
    """

    def __init__(self) -> None:
        """初始化客户端（函数）。

        说明：
            base_url/api_key 取自 settings（.env），请求超时取 LLM_TIMEOUT_SECONDS。

        返回值：
            None。

        异常：
            openai 异常包装为 LLMError 向上抛出（初始化阶段即失败即报）。
        """
        try:
            self._client = openai.OpenAI(
                base_url=settings.LLM_BASE_URL,
                api_key=settings.LLM_API_KEY,
                timeout=settings.LLM_TIMEOUT_SECONDS,
            )
        except Exception as exc:  # noqa: BLE001 —— 统一包装为 LLMError
            raise LLMError(f"LLM client init failed: {exc}") from exc

    def chat(self, system: str, user: str, temperature: float = 0.2) -> LLMResult:
        """调用对话补全（函数）。

        说明：
            messages 仅含 system + user 两条（阶段一无多轮上下文）；
            超时由客户端 timeout 控制（settings.LLM_TIMEOUT_SECONDS）。

        参数：
            system：系统提示词。
            user：用户消息。
            temperature：采样温度，默认 0.2（偏确定性输出）。

        返回值：
            LLMResult：补全结果（content + token 用量 + 模型名）。

        异常：
            LLMError：网络/超时/鉴权/响应异常时抛出，调用方负责降级。
        """
        try:
            resp = self._client.chat.completions.create(
                model=settings.LLM_MODEL,
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                temperature=temperature,
            )
            content = (resp.choices[0].message.content or "").strip() if resp.choices else ""
            usage = resp.usage
            prompt_tokens = getattr(usage, "prompt_tokens", 0) or 0 if usage else 0
            completion_tokens = getattr(usage, "completion_tokens", 0) or 0 if usage else 0
            return LLMResult(
                content=content,
                prompt_tokens=int(prompt_tokens),
                completion_tokens=int(completion_tokens),
                model=resp.model or settings.LLM_MODEL,
            )
        except Exception as exc:  # noqa: BLE001 —— 一切失败包装为 LLMError
            logger.warning("LLM chat failed: %s", exc)
            raise LLMError(f"LLM chat failed: {exc}") from exc

    def chat_with_image(
        self,
        system: str,
        user: str,
        image_bytes: bytes,
        mime: str = "image/jpeg",
        temperature: float = 0.1,
        max_tokens: int = 800,
    ) -> LLMResult:
        """调用视觉多模态补全（图片 + 文本 → 文本，函数）。

        说明：
            使用独立的视觉客户端（VISION_BASE_URL / VISION_API_KEY /
            VISION_TIMEOUT_SECONDS 配置，首次调用懒加载创建），与 DeepSeek
            文本客户端配置完全分离；🔴 必须传 stream=True（qwen omni 系列
            兼容模式要求流式输出），以 stream_options={"include_usage": True}
            携回用量（取不到按 0 计）；流式 delta.content 逐块拼接为最终文本。
            失败统一包装为 LLMError（与 chat() 同风格），调用方降级。

        参数：
            system：系统提示词（如食材识别约束）。
            user：用户文本消息（如「识别这张冰箱照片中的食材」）。
            image_bytes：图片文件原始字节（jpg/png 等，仅内存处理，不落盘）。
            mime：图片 MIME 类型（默认 image/jpeg，用于 base64 data URL 前缀）。
            temperature：采样温度，默认 0.1（识别任务偏确定性输出）。
            max_tokens：输出 token 上限，默认 800（食材 JSON 数组足够）。

        返回值：
            LLMResult：补全结果（content 为拼接后的完整文本；model 取响应
            resp.model 若可得否则 settings.VISION_MODEL；用量取 usage 块若可得否则 0）。

        异常：
            LLMError：视觉客户端初始化失败 / 网络 / 超时 / 鉴权 / 响应异常时抛出，
            调用方（MultimodalVisionProvider → 路由层）负责降级。
        """
        try:
            # 懒加载独立视觉客户端（与 DeepSeek 文本客户端配置完全分离）
            if getattr(self, "_vision_client", None) is None:
                self._vision_client = openai.OpenAI(
                    base_url=settings.VISION_BASE_URL,
                    api_key=settings.VISION_API_KEY,
                    timeout=settings.VISION_TIMEOUT_SECONDS,
                )
            # 图片字节 → base64 data URL（OpenAI 多模态 image_url 约定格式）
            b64 = base64.b64encode(image_bytes).decode("ascii")
            data_url = f"data:{mime};base64,{b64}"
            # 🔴 qwen omni 系列兼容模式要求 stream=True；include_usage 携回 token 用量
            stream = self._vision_client.chat.completions.create(
                model=settings.VISION_MODEL,
                messages=[
                    {"role": "system", "content": system},
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": user},
                            {"type": "image_url", "image_url": {"url": data_url}},
                        ],
                    },
                ],
                temperature=temperature,
                max_tokens=max_tokens,
                stream=True,
                stream_options={"include_usage": True},
            )
            # 循环收集流式增量：delta.content 拼接为最终文本；usage 块通常在最后一个分片
            parts: list[str] = []
            prompt_tokens = 0
            completion_tokens = 0
            model_name = settings.VISION_MODEL
            for chunk in stream:
                if getattr(chunk, "model", None):
                    model_name = str(chunk.model)
                usage = getattr(chunk, "usage", None)
                if usage is not None:
                    prompt_tokens = int(getattr(usage, "prompt_tokens", 0) or 0)
                    completion_tokens = int(getattr(usage, "completion_tokens", 0) or 0)
                choices = getattr(chunk, "choices", None) or []
                for choice in choices:
                    delta = getattr(choice, "delta", None)
                    piece = getattr(delta, "content", None) if delta is not None else None
                    if piece:
                        parts.append(piece)
            return LLMResult(
                content="".join(parts).strip(),
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                model=model_name,
            )
        except Exception as exc:  # noqa: BLE001 —— 一切失败包装为 LLMError
            logger.warning("LLM chat_with_image failed: %s", exc)
            raise LLMError(f"LLM chat_with_image failed: {exc}") from exc


# 进程级单例
_client: LLMClient | None = None
_client_lock = threading.Lock()


def get_llm_client() -> LLMClient:
    """获取 LLMClient 进程级单例（函数）。

    返回值：
        LLMClient：全局唯一客户端实例。

    异常：
        LLMError：客户端初始化失败时抛出。
    """
    global _client
    if _client is None:
        with _client_lock:
            if _client is None:
                _client = LLMClient()
    return _client
