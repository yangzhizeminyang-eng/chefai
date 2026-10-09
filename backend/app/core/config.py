"""应用配置模块。

职责：
    基于 pydantic-settings 读取 backend/.env 环境配置，提供全局单例 Settings，
    供数据库连接、LLM 客户端、应用启动等模块统一消费，禁止在代码中硬编码连接参数。

环境变量：
    DB_HOST / DB_PORT / DB_USER / DB_PASSWORD / DB_NAME：PostgreSQL 连接信息
    LLM_BASE_URL / LLM_API_KEY / LLM_MODEL / LLM_TIMEOUT_SECONDS：OpenAI 兼容大模型参数
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
