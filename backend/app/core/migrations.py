"""数据库结构迁移模块（Alembic 程序化入口）。

职责：
    提供 ensure_schema()，供 python -m app.seed 等入口在数据填充前
    统一收敛表结构管理，落实 02-V1.1 §10.1「表结构由 Alembic 管理，
    禁止手工改线上表结构」与 05-V1.1 §3.2/§3.3 的迁移口径。

    ensure_schema() 分支决策（幂等，可重复执行）：
        1. alembic_version 表已存在（库已被 Alembic 纳管）
           → 执行 upgrade head（若落后于 head 则推进）；
        2. alembic_version 不存在、但业务表已存在
           （如历史 create_all 建出的 aicook 存量库）
           → 执行 stamp head：登记当前版本，不改动任何既有表与数据；
        3. 库为空（既无 alembic_version 也无业务表）
           → 执行 upgrade head：一次建全 28 张业务表 + recipe_embedding 预留表。

    连接串由 alembic/env.py 按「ALEMBIC_DATABASE_URL > settings.database_url」
    优先级注入；本模块不硬编码任何连接参数。
"""

from pathlib import Path

from alembic.config import Config
from sqlalchemy import create_engine, inspect

from alembic import command
from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger("app.core.migrations")

# 判定「存量库已有业务表」的代表性表（历史 create_all 一定建出的两张核心表）
_EXISTENCE_SENTINEL_TABLES = ("user", "recipe")


def _build_alembic_config() -> Config:
    """构造 Alembic 程序化调用配置（函数）。

    说明：
        指向 backend/alembic.ini 并显式设置 script_location 为绝对路径；
        将 config_file_name 置空以跳过 env.py 中的 fileConfig 调用，
        避免迁移过程的 ini 日志配置覆盖应用已装配的 JSON 结构化日志。

    返回值：
        Config：可直接交给 alembic.command 使用的配置对象。

    异常：
        alembic.ini 缺失时由 Config 抛出文件读取异常。
    """
    # backend 根目录（本文件位于 backend/app/core/migrations.py，向上三级）
    backend_root = Path(__file__).resolve().parents[2]
    ini_path = backend_root / "alembic.ini"
    cfg = Config(str(ini_path))
    # script_location 用绝对路径，保证任意工作目录调用均有效
    cfg.set_main_option("script_location", str(backend_root / "alembic"))
    # 跳过 env.py 的 fileConfig：不覆盖应用日志装配（见 env.py 注释）
    cfg.config_file_name = None
    return cfg


def ensure_schema() -> str:
    """确保数据库表结构已由 Alembic 纳管并推进到 head（函数）。

    返回值：
        str：实际执行的分支，"upgrade"（建表/推进版本）或 "stamp"（存量库登记）。

    异常：
        数据库不可达、迁移脚本执行失败时：先以中文记录错误日志，
        再将异常向上抛出（由调用方决定回滚与退出策略）。
    """
    cfg = _build_alembic_config()
    # 检查用临时引擎（alembic.command 内部自建引擎，二者独立，用毕即释放）
    probe_engine = create_engine(settings.database_url, pool_pre_ping=True)
    try:
        inspector = inspect(probe_engine)
        has_version_table = inspector.has_table("alembic_version")
        # 业务表存在性：两枚举表齐全才认定「存量 create_all 库」，
        # 避免半建表状态被误 stamp（半建状态应走 upgrade 报错暴露问题）
        has_business_tables = all(
            inspector.has_table(table) for table in _EXISTENCE_SENTINEL_TABLES
        )
    finally:
        probe_engine.dispose()

    try:
        if has_version_table:
            # 分支 1：已纳管 → 推进到 head（幂等：已在 head 时为 no-op）
            logger.info("迁移分支：alembic_version 已存在，执行 upgrade head")
            command.upgrade(cfg, "head")
            return "upgrade"
        if has_business_tables:
            # 分支 2：create_all 存量库兼容 → stamp 登记版本，不碰既有表结构与数据
            logger.info("迁移分支：存量库已有业务表，执行 stamp head（兼容历史 create_all）")
            command.stamp(cfg, "head")
            return "stamp"
        # 分支 3：空库 → 全量建表
        logger.info("迁移分支：空库，执行 upgrade head 全量建表")
        command.upgrade(cfg, "head")
        return "upgrade"
    except Exception as exc:
        # 中文记录后原样上抛：迁移失败必须让调用方感知（05-V1.1 §3.3）
        logger.error("Alembic 迁移执行失败：%s", exc)
        raise
