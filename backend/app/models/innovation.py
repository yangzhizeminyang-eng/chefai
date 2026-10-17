"""模块 O（AI 菜品创新）域 ORM 模型。

职责：
    建模阶段二「AI 菜品创新」数据层四表：
    - ingredient_property：食材质地/含水量/风味/耐热/吸油五属性（创新生成的原料性质依据）；
    - flavor_pairing_rule：食材搭配规则（recommend 推荐 / conflict 冲突 / taboo 禁忌），
      创新生成的搭配依据（rationale 采用烹饪学表述，不含中医性味归经断言）；
    - technique_library：技法白名单库（创新菜技法校验依据）；
    - innovation_recipe：AI 创新菜（JSONB 存储 ingredients/steps/nutrition/basis）。

说明：
    本模块四表由迁移 b8d3f5a21c60 建（down_revision=3740c6411c8a）。
"""

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Numeric,
    SmallInteger,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base

if TYPE_CHECKING:
    from app.models.ingredient import Ingredient

# 时间列公共参数：服务端默认 now()（TIMESTAMPTZ 类型在使用处显式传入）
_TS = {"server_default": func.now()}


class IngredientProperty(Base):
    """食材五属性表（模块 O 创新依据之一）。

    说明：
        与食材一对一（ingredient_id UNIQUE）；五个属性均可为 NULL
        （启发式标注允许缺项，缺失项不参与创新推导）；
        source_note 默认「启发式标注，需专家复核」，标记数据成熟度。
    """

    __tablename__ = "ingredient_property"

    __table_args__ = (
        UniqueConstraint("ingredient_id", name="uq_ingredient_property_ingredient_id"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    ingredient_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("ingredient.id", ondelete="CASCADE"), unique=True, nullable=False
    )
    texture: Mapped[str | None] = mapped_column(String(32), nullable=True)
    moisture: Mapped[str | None] = mapped_column(String(16), nullable=True)
    flavor: Mapped[str | None] = mapped_column(String(64), nullable=True)
    heat_tolerance: Mapped[str | None] = mapped_column(String(16), nullable=True)
    oil_absorption: Mapped[str | None] = mapped_column(String(16), nullable=True)
    source_note: Mapped[str] = mapped_column(
        String(255), nullable=False, default="启发式标注，需专家复核",
        server_default="启发式标注，需专家复核",
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), **_TS, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), **_TS, nullable=False)

    ingredient: Mapped["Ingredient"] = relationship()


class FlavorPairingRule(Base):
    """食材风味搭配规则表（模块 O 创新依据之二）。

    说明：
        relation 三态：recommend（推荐搭配）/ conflict（风味冲突，不建议同烹）/
        taboo（强烈不建议，任何烹法均不推荐）；UNIQUE(a, b, relation)。
        technique_suggestion 语义指向 technique_library.name 但不建外键强制约束
        （白名单可演进，规则先行）；rationale 一律采用烹饪学表述
        （口感互补/风味亲和/风味冲突），禁止中医相克与中毒断言。
    """

    __tablename__ = "flavor_pairing_rule"

    __table_args__ = (
        CheckConstraint("relation IN ('recommend','conflict','taboo')", name="chk_relation"),
        UniqueConstraint("ingredient_a_id", "ingredient_b_id", "relation",
                         name="uq_pairing_a_b_relation"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    ingredient_a_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("ingredient.id", ondelete="CASCADE"), nullable=False
    )
    ingredient_b_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("ingredient.id", ondelete="CASCADE"), nullable=False
    )
    relation: Mapped[str] = mapped_column(String(16), nullable=False)
    technique_suggestion: Mapped[str | None] = mapped_column(String(128), nullable=True)
    rationale: Mapped[str] = mapped_column(String(255), nullable=False)
    weight: Mapped[float] = mapped_column(
        Numeric(4, 2), nullable=False, default=1.0, server_default="1.0"
    )
    signed_by_expert: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), **_TS, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), **_TS, nullable=False)

    ingredient_a: Mapped["Ingredient"] = relationship(foreign_keys=[ingredient_a_id])
    ingredient_b: Mapped["Ingredient"] = relationship(foreign_keys=[ingredient_b_id])


class TechniqueLibrary(Base):
    """技法白名单库表（模块 O 创新技法校验依据）。

    说明：
        name 唯一；in_whitelist=TRUE 的技法才允许出现在创新菜步骤中
        （生成结果约束在用户可理解、可执行的经典技法集合内）。
    """

    __tablename__ = "technique_library"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    description: Mapped[str] = mapped_column(String(255), nullable=False)
    in_whitelist: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="true"
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), **_TS, nullable=False)


class InnovationRecipe(Base):
    """AI 创新菜表（模块 O 核心产出）。

    说明：
        - ingredients/steps/nutrition/basis 均为 JSONB（结构见生成层约定）：
          ingredients=[{ingredient_id,name,amount,unit}]、
          steps=[{no,description,duration_sec,tips}]、
          basis 记录创新依据（食材性质/搭配规则引用，可追溯）；
        - status 状态机：generated → adopted/indexed/removed；
        - visibility 阶段二仅开放 private（CHECK 单值，后续可扩展 public）；
        - source_pairing_rule_ids 记录生成时引用的 flavor_pairing_rule.id 列表。
    """

    __tablename__ = "innovation_recipe"

    __table_args__ = (
        CheckConstraint(
            "status IN ('generated','adopted','indexed','removed')", name="chk_status"
        ),
        CheckConstraint("visibility IN ('private')", name="chk_visibility"),
        Index("idx_innovation_user", "user_id", "status"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("user.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    ingredients: Mapped[list] = mapped_column(JSONB, nullable=False)
    steps: Mapped[list] = mapped_column(JSONB, nullable=False)
    nutrition: Mapped[dict] = mapped_column(JSONB, nullable=False)
    basis: Mapped[dict] = mapped_column(JSONB, nullable=False)
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, default="generated", server_default="generated"
    )
    is_ai_innovated: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="true"
    )
    visibility: Mapped[str] = mapped_column(
        String(16), nullable=False, default="private", server_default="private"
    )
    source_pairing_rule_ids: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    rating: Mapped[int | None] = mapped_column(SmallInteger, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), **_TS, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), **_TS, nullable=False)


class InnovationJob(Base):
    """AI 创新异步任务持久化表（模块 O job 落库，最小兼容升级）。

    说明：
        承载内存 job store（_INNOVATION_JOBS）的写穿副本，解决进程重启后
        pending/running 任务"凭空消失"问题：
        - 提交/转 running/终态变更时同步写穿（失败仅告警，不阻断 job 链路）；
        - 应用启动恢复：把遗留的 pending/running 行置为 failed（终态明确，
          轮询方经 DB fallback 拿到失败文案而非 404）；
        - 终态即冻结语义与内存 store 一致（succeeded/failed/blocked 不可逆）；
        - recipe/issues 以 JSONB 存储（结构同内存记录）；user_id 无外键约束
          （与内存 store 的 user_db_id 语义一致，用户注销后行保留供审计）。
        由迁移 9c3e1f7a52b8 建表（down_revision=d8f2b7c91e43）。
    """

    __tablename__ = "innovation_job"

    __table_args__ = (
        CheckConstraint(
            "status IN ('pending','running','succeeded','failed','blocked')",
            name="chk_job_status",
        ),
        Index("idx_innovation_job_user", "user_id", "created_at"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    job_id: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    user_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, default="pending", server_default="pending"
    )
    request_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    recipe: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    issues: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    error: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), **_TS, nullable=False)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
