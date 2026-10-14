"""应用配置模块。

职责：
    基于 pydantic-settings 读取 backend/.env 环境配置，提供全局单例 Settings，
    供数据库连接、LLM 客户端、视觉识别（VLM）客户端、应用启动等模块统一消费，
    禁止在代码中硬编码连接参数。

环境变量：
    DB_HOST / DB_PORT / DB_USER / DB_PASSWORD / DB_NAME：PostgreSQL 连接信息
    LLM_BASE_URL / LLM_API_KEY / LLM_MODEL / LLM_TIMEOUT_SECONDS：OpenAI 兼容大模型参数
    VISION_PROVIDER / VISION_BASE_URL / VISION_API_KEY / VISION_MODEL /
    VISION_TIMEOUT_SECONDS / VISION_MAX_ITEMS：真实视觉模型（VLM）参数——
    VISION_PROVIDER 取 'mock'（缺省，确定性 mock）或 'vlm'（阿里云百炼
    qwen omni 系列多模态模型，经 OpenAI 兼容协议调用）；
    VISION_MAX_ITEMS 为单次识别返回条目上限（超出的条目被截断）。
    EMBEDDING_PROVIDER / EMBEDDING_MODEL_NAME / EMBEDDING_BATCH_SIZE /
    EMBEDDING_API_BASE / EMBEDDING_API_KEY / EMBEDDING_TIMEOUT_SECONDS /
    EMBEDDING_WARMUP：向量嵌入（阿里云百炼 qwen3.7-text-embedding，
    OpenAI 兼容协议）参数——EMBEDDING_PROVIDER 取 'hash'（缺省，确定性哈希
    兜底）或 'bailian'（百炼远程语义嵌入，阶段二 'bgem3' 占位）；
    EMBEDDING_API_BASE / EMBEDDING_API_KEY 为空串时回落复用
    VISION_BASE_URL / VISION_API_KEY（百炼同一凭证）；
    EMBEDDING_WARMUP 控制启动期预热（仅 bailian 生效）。
    RETRIEVAL_VECTOR / RETRIEVAL_VECTOR_FOR_INGREDIENTS / RETRIEVAL_FUSION：
    检索开关——RETRIEVAL_VECTOR 为向量路径总开关（'on'/'off'）；
    RETRIEVAL_VECTOR_FOR_INGREDIENTS 控制手选食材合成查询（默认 'off'）；
    RETRIEVAL_FUSION 为三路融合策略（'fixed' 缺省 / 'rrf'）。
    APP_HOST / APP_PORT：应用监听地址与端口

异常：
    pydantic_validation.ValidationError：环境变量类型不合法时抛出。
"""

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

# .env 固定指向 backend/.env（本文件位于 backend/app/core/config.py，向上三级为 backend/）
_ENV_FILE = Path(__file__).resolve().parents[2] / ".env"


class Settings(BaseSettings):
    """全局配置对象（模型类）。

    属性：
        DB_HOST：数据库主机地址，默认 localhost。
        DB_PORT：数据库端口，默认 5432。
        DB_USER：数据库用户名。
        DB_PASSWORD：数据库密码。
        DB_NAME：业务库名（阶段一为 aicook）。
        LLM_BASE_URL：OpenAI 兼容服务地址。
        LLM_API_KEY：大模型 API Key。
        LLM_MODEL：模型名称。
        LLM_TIMEOUT_SECONDS：LLM 请求超时秒数。
        VISION_PROVIDER：视觉识别提供方取值（'mock' 缺省 / 'vlm' 真实视觉模型）。
        VISION_BASE_URL：视觉模型 OpenAI 兼容服务地址（vlm 时必填，如阿里云百炼）。
        VISION_API_KEY：视觉模型 API Key。
        VISION_MODEL：视觉模型名称（如 qwen3.8-omni-flash）。
        VISION_TIMEOUT_SECONDS：视觉模型请求超时秒数（拍照识别 P95 预算对齐 20s）。
        VISION_MAX_ITEMS：单次识别返回条目上限（超出截断，防噪声刷屏）。
        SPEECH_PROVIDER：语音转写提供方取值（'mock' 缺省固定演示文本 /
    'bailian' 阿里云百炼 qwen3-asr-flash，OpenAI 兼容协议）。
    SPEECH_BASE_URL：语音模型 OpenAI 兼容服务地址（空串回落 VISION_BASE_URL）。
    SPEECH_API_KEY：语音模型 API Key（空串回落 VISION_API_KEY）。
    SPEECH_MODEL：语音模型名称（如 qwen3-asr-flash）。
    SPEECH_TIMEOUT_SECONDS：语音识别请求超时秒数（免手语音指令链路，短句快响应）。
    TTS_PROVIDER：语音合成提供方取值（'mock' 缺省静音 /
    'bailian' 阿里云百炼 qwen3-tts-flash，DashScope 多模态生成协议）。
    TTS_BASE_URL：语音合成服务地址（空串用 DashScope 默认端点）。
    TTS_API_KEY：语音合成 API Key（空串回落 SPEECH_API_KEY / VISION_API_KEY）。
    TTS_MODEL：语音合成模型名称（如 qwen3-tts-flash）。
    TTS_VOICE：合成音色（如 Cherry）。
    TTS_TIMEOUT_SECONDS：语音合成请求超时秒数。
    VOICE_INTENT_ENABLED：语音意图理解开关（'on' 缺省 / 'off'）——白名单
    未命中时是否调主 LLM（settings.LLM_*）做兜底意图解析；off 时直接返回
    none（保持纯白名单行为，可随时回退）。
    COOKING_HELP_AGENT_ENABLED：烹饪求助子智能体开关（'on' 缺省 / 'off'）——
    求助回答是否结合当前步骤与用户档案经主 LLM 生成；off 或 LLM 失败时
    回退关键词库/步骤要点模板。
    EMBEDDING_PROVIDER：嵌入提供方取值（'hash' 缺省确定性哈希兜底 /
        'bailian' 百炼远程语义嵌入 / 'bgem3' 阶段二占位）。
        EMBEDDING_MODEL_NAME：嵌入模型名称（如 qwen3.7-text-embedding）。
        EMBEDDING_BATCH_SIZE：嵌入请求单批文本条数上限。
        EMBEDDING_API_BASE：嵌入服务 OpenAI 兼容地址（空串回落 VISION_BASE_URL）。
        EMBEDDING_API_KEY：嵌入服务 API Key（空串回落 VISION_API_KEY）。
        EMBEDDING_TIMEOUT_SECONDS：嵌入请求超时秒数。
        EMBEDDING_WARMUP：启动期预热开关（'on'/'off'，仅 bailian 生效）。
        RETRIEVAL_VECTOR：向量检索路径总开关（'on' 缺省 / 'off'）。
        RETRIEVAL_VECTOR_FOR_INGREDIENTS：手选食材合成查询向量开关（默认 'off'）。
        RETRIEVAL_FUSION：三路融合策略取值（'fixed' 缺省 / 'rrf'）。
        APP_HOST：FastAPI 监听主机。
        APP_PORT：FastAPI 监听端口。

    异常：
        ValidationError：.env 字段缺失类型不匹配时由 pydantic 抛出。
    """

    model_config = SettingsConfigDict(
        env_file=str(_ENV_FILE),
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=True,
    )

    # 数据库
    DB_HOST: str = "localhost"
    DB_PORT: int = 5432
    DB_USER: str = "postgres"
    DB_PASSWORD: str = ""
    DB_NAME: str = "aicook"

    # 大模型（OpenAI 兼容）
    LLM_BASE_URL: str = "https://api.deepseek.com"
    LLM_API_KEY: str = ""
    LLM_MODEL: str = "deepseek-flash"
    LLM_TIMEOUT_SECONDS: int = 20

    # 视觉模型（VLM，OpenAI 兼容协议；VISION_PROVIDER='vlm' 时启用真实识别，
    # 缺省 mock 保持阶段一行为可随时回退）
    VISION_PROVIDER: str = "mock"
    VISION_BASE_URL: str = ""
    VISION_API_KEY: str = ""
    VISION_MODEL: str = ""
    VISION_TIMEOUT_SECONDS: int = 20
    VISION_MAX_ITEMS: int = 12

    # 语音转写（百炼 qwen3-asr-flash，OpenAI 兼容协议；BASE/KEY 空串回落 VISION_*）
    SPEECH_PROVIDER: str = "mock"
    SPEECH_BASE_URL: str = ""
    SPEECH_API_KEY: str = ""
    SPEECH_MODEL: str = "qwen3-asr-flash"
    SPEECH_TIMEOUT_SECONDS: int = 15

    # 语音合成（百炼 qwen3-tts-flash，DashScope 多模态生成协议；KEY 空串回落 SPEECH_/VISION_*）
    TTS_PROVIDER: str = "mock"
    TTS_BASE_URL: str = ""
    TTS_API_KEY: str = ""
    TTS_MODEL: str = "qwen3-tts-flash"
    TTS_VOICE: str = "Cherry"
    TTS_TIMEOUT_SECONDS: int = 20

    # 语音意图理解（白名单未命中时主 LLM 兜底解析；off = 纯白名单行为）
    VOICE_INTENT_ENABLED: str = "on"

    # 烹饪求助子智能体（结合步骤+档案经主 LLM 生成回答；off/失败回退模板）
    COOKING_HELP_AGENT_ENABLED: str = "on"

    # 向量嵌入（百炼 qwen3.7-text-embedding，OpenAI 兼容协议）+ 检索开关
    # （API BASE/KEY 空串时由消费方回落 VISION_BASE_URL/VISION_API_KEY）
    EMBEDDING_PROVIDER: str = "hash"
    EMBEDDING_MODEL_NAME: str = "qwen3.7-text-embedding"
    EMBEDDING_BATCH_SIZE: int = 10
    EMBEDDING_API_BASE: str = ""
    EMBEDDING_API_KEY: str = ""
    EMBEDDING_TIMEOUT_SECONDS: int = 10
    EMBEDDING_WARMUP: str = "on"
    RETRIEVAL_VECTOR: str = "on"
    RETRIEVAL_VECTOR_FOR_INGREDIENTS: str = "off"
    RETRIEVAL_FUSION: str = "fixed"

    # 应用
    APP_HOST: str = "0.0.0.0"
    APP_PORT: int = 8000

    @property
    def database_url(self) -> str:
        """生成 SQLAlchemy 使用的 psycopg2 连接串。

        返回值：
            str：形如 postgresql+psycopg2://user:pass@host:port/dbname 的连接串。

        异常：
            无（字段均有默认值，不主动抛出）。
        """
        return (
            f"postgresql+psycopg2://{self.DB_USER}:{self.DB_PASSWORD}"
            f"@{self.DB_HOST}:{self.DB_PORT}/{self.DB_NAME}"
        )

    @property
    def admin_database_url(self) -> str:
        """生成连接系统库 postgres 的连接串（用于建库前检查）。

        返回值：
            str：指向 postgres 系统库的连接串。

        异常：
            无。
        """
        return (
            f"postgresql+psycopg2://{self.DB_USER}:{self.DB_PASSWORD}"
            f"@{self.DB_HOST}:{self.DB_PORT}/postgres"
        )


# 全局单例：模块导入时即读取 .env，各处统一 from app.core.config import settings 消费
settings = Settings()
