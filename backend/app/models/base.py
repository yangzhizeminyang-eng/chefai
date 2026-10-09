"""ORM 基类模块。

职责：
    定义 SQLAlchemy 2.0 DeclarativeBase 及统一命名约定（约束/索引命名后缀规范），
    保证 create_all 与阶段二 Alembic 迁移生成稳定的约束名。
"""

from sqlalchemy import MetaData
from sqlalchemy.orm import DeclarativeBase

# 统一命名约定：未显式命名的约束自动按模板命名，避免随机名导致迁移不可重现
NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    """全项目 ORM 基类（模型类）。

    说明：
        所有 28 张业务表 + recipe_embedding 预留表均继承本类；
        metadata 挂载统一命名约定。
    """

    metadata = MetaData(naming_convention=NAMING_CONVENTION)
