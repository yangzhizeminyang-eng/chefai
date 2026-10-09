# -*- coding: utf-8 -*-
"""Alembic 迁移环境配置模块。

职责：
    1. 为 Alembic 提供 target_metadata（app.models 的 Base.metadata），
       使 `alembic revision --autogenerate` 能对照模型生成全量建表迁移；
    2. 运行时注入数据库连接串（02-V1.1 §10.1：禁止在 alembic.ini 硬编码口令），
       优先级：环境变量 ALEMBIC_DATABASE_URL（临时库/CI 覆盖用）
             > alembic.ini 的 sqlalchemy.url（若非空，留作特殊场景手工覆盖）
             > app.core.config.settings.database_url（读 backend/.env，日常默认）。

环境变量：
    ALEMBIC_DATABASE_URL：可选，覆盖默认连接串（如指向 aicook_migtest 临时验证库）。

异常：
    ConfigError：无法解析出任何可用连接串时抛出（连接串来源全部为空）。
"""

import os
from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

# 将 backend 根目录加入 sys.path（alembic.ini 的 prepend_sys_path 已处理，
# 此处重复设置以保证「任意工作目录执行 alembic 命令」均可导入 app 包）
import sys
from pathlib import Path

_BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(_BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(_BACKEND_ROOT))

# 导入 ORM 元数据：autogenerate 对照的唯一事实来源
from app.core.config import settings  # noqa: E402
from app.models import Base  # noqa: E402  —— 导入即注册全部 29 个 Table（28 业务表 + recipe_embedding）

# this is the Alembic Config object, which provides
# access to the values within the .ini file in use.
config = context.config

# Interpret the config file for Python logging.
# This line sets up loggers basically.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# autogenerate 对照的模型元数据（含统一命名约定 NAMING_CONVENTION）
target_metadata = Base.metadata


def _resolve_database_url() -> str:
    """按优先级解析迁移使用的数据库连接串（函数）。

    优先级：
        1. 环境变量 ALEMBIC_DATABASE_URL（临时库验证 / CI 场景覆盖）；
        2. alembic.ini 的 sqlalchemy.url（仅当非空时生效，默认留空）；
        3. app.core.config.settings.database_url（读 backend/.env，日常默认）。

    返回值：
        str：形如 postgresql+psycopg2://user:pass@host:port/dbname 的连接串。

    异常：
        RuntimeError：三个来源均为空时抛出（配置缺失）。
    """
    # 1. 环境变量优先（临时库验证入口）
    url = os.environ.get("ALEMBIC_DATABASE_URL", "").strip()
    if url:
        return url
    # 2. alembic.ini 显式配置（默认留空，跳过）
    url = (config.get_main_option("sqlalchemy.url") or "").strip()
    if url:
        return url
    # 3. 默认：settings 读取 backend/.env
    url = settings.database_url
    if url:
        return url
    raise RuntimeError(
        "无法解析数据库连接串：ALEMBIC_DATABASE_URL / alembic.ini sqlalchemy.url / "
        "settings.database_url 三者均为空，请检查 backend/.env 配置。"
    )


def run_migrations_offline() -> None:
    """以离线模式执行迁移（函数）。

    说明：
        仅凭连接串生成 SQL 脚本（--sql 模式），不实际连接数据库，
        供 DBA 审核迁移 SQL 时使用。

    异常：
        连接串解析失败时抛 RuntimeError。
    """
    context.configure(
        url=_resolve_database_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """以在线模式执行迁移（函数）。

    说明：
        创建真实 Engine 连接数据库执行迁移；连接串按 _resolve_database_url
        优先级注入，注入方式为写入 config 段后交给 engine_from_config，
        与 alembic 官方推荐做法一致（NullPool：迁移进程短生命周期，无需连接池）。

    异常：
        数据库不可达时由 psycopg2 抛出连接异常向上传递。
    """
    # 将解析出的连接串写回配置段（覆盖 ini 中留空的 sqlalchemy.url）
    config.set_main_option("sqlalchemy.url", _resolve_database_url())

    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            # 对比类型变化（autogenerate 与 upgrade 双向生效）
            compare_type=True,
        )

        with context.begin_transaction():
            context.run_migrations()

    connectable.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
