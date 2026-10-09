"""数据库引擎与会话模块。

职责：
    提供 SQLAlchemy 2.0 同步引擎（连接串来自 app.core.config.settings，pool_pre_ping 防连接失效）、
    SessionLocal 会话工厂，以及 FastAPI 依赖 get_db（请求级会话，异常回滚，用毕关闭）。
"""

from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import settings

# 同步引擎：pool_pre_ping=True 在取连接前探活，避免 PG 重启/超时导致的死连接
engine = create_engine(
    settings.database_url,
    pool_pre_ping=True,
    pool_size=5,
    max_overflow=10,
    echo=False,
)

# 会话工厂：业务代码统一通过 get_db 获取会话
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def get_db() -> Generator[Session]:
    """FastAPI 依赖：提供请求级数据库会话。

    返回值：
        Generator[Session, None, None]：yield 一个 SQLAlchemy Session。

    异常：
        将业务异常向上抛出由全局异常处理器兜底；任何异常发生时先 rollback 再关闭会话。
    """
    db = SessionLocal()
    try:
        yield db
    except Exception:
        # 业务异常时回滚，保证不留半提交状态
        db.rollback()
        raise
    finally:
        db.close()
