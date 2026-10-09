"""菜谱域 ORM 模型。

职责：
    按架构文档 §10.4.12~§10.4.14 建模 recipe / recipe_ingredient / recipe_step，
    并建 §10.4 向量表 recipe_embedding；含 chk_amount_quantified 表级 CHECK
    （CT-6：用量必须量化）与菜谱表 5 个 GIN 索引。
    对 recipe 表做两处最小扩展（UI 需求，来源：03-UI原型 W-03）：tips / substitutes。
    阶段二（迁移 b8d3f5a21c60）升级 recipe_embedding：pgvector 容错向量列 +
    embedding_json 便携列 + 溯源列（owner/innovation/source）与独立 id 主键。
"""

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    SmallInteger,
    String,
    Text,
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


class Recipe(Base):
    """菜谱表（对应 §10.4.12 recipe）。

    说明：
        - allergen_codes：菜谱自带致敏原；ingredient_allergen_codes：由食材聚合（冗余，供 SQL 硬过滤）；
        - equipment/dietary_flags 为 JSONB 数组，走 GIN 索引；
        - 扩展字段 tips（小贴士）/ substitutes（替代食材，JSONB 数组）来自 UI 原型 W-03 需求。
    """

    __tablename__ = "recipe"

    __table_args__ = (
        CheckConstraint("difficulty >= 1 AND difficulty <= 5", name="chk_difficulty_range"),
        CheckConstraint("status IN ('draft','published','offline')", name="chk_status"),
        Index("idx_recipe_status", "status", "difficulty"),
        Index("gin_recipe_allergen", "allergen_codes", postgresql_using="gin"),
        Index("gin_recipe_ing_allergen", "ingredient_allergen_codes", postgresql_using="gin"),
        Index("gin_recipe_dietary", "dietary_flags", postgresql_using="gin"),
        Index("gin_recipe_equipment", "equipment", postgresql_using="gin"),
        # 菜名模糊搜索：GIN trgm（依赖 pg_trgm 扩展，seed 时自动创建；失败则回退方案见 seed/__main__）
        Index(
            "idx_recipe_title_trgm",
            "title",
            postgresql_using="gin",
            postgresql_ops={"title": "gin_trgm_ops"},
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    title: Mapped[str] = mapped_column(String(100), nullable=False)
    cuisine: Mapped[str | None] = mapped_column(String(30), nullable=True)
    cooking_method: Mapped[str | None] = mapped_column(String(20), nullable=True)
    difficulty: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    time_minutes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    servings: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=2, server_default="2")
    calories_kcal: Mapped[int | None] = mapped_column(Integer, nullable=True)
    allergen_codes: Mapped[list] = mapped_column(JSONB, nullable=False, default=list, server_default="[]")
    ingredient_allergen_codes: Mapped[list] = mapped_column(JSONB, nullable=False, default=list, server_default="[]")
    dietary_flags: Mapped[list] = mapped_column(JSONB, nullable=False, default=list, server_default="[]")
    equipment: Mapped[list] = mapped_column(JSONB, nullable=False, default=list, server_default="[]")
    cover_image_url: Mapped[str | None] = mapped_column(String(255), nullable=True)
    source_label: Mapped[str] = mapped_column(String(100), nullable=False)
    source_license: Mapped[str] = mapped_column(String(50), nullable=False)
    status: Mapped[str] = mapped_column(String(10), nullable=False, default="draft", server_default="draft")
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1, server_default="1")
    # ---- UI 需求最小扩展（来源：03-UI原型 W-03「替代食材 / 小贴士」展示位）----
    tips: Mapped[str | None] = mapped_column(Text, nullable=True)
    substitutes: Mapped[list] = mapped_column(JSONB, nullable=False, default=list, server_default="[]")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), **_TS, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), **_TS, nullable=False)

    ingredients: Mapped[list["RecipeIngredient"]] = relationship(
        back_populates="recipe", cascade="all, delete-orphan"
    )
    steps: Mapped[list["RecipeStep"]] = relationship(
        back_populates="recipe", cascade="all, delete-orphan", order_by="RecipeStep.step_no"
    )


class RecipeIngredient(Base):
    """菜谱食材表（对应 §10.4.13 recipe_ingredient）。

    说明：
        用量必须量化：amount_value 或 (amount_min, amount_max) 二者至少其一，
        由表级 CHECK chk_amount_quantified 强制（CT-6：调味料不得「适量/少许」）。
    """

    __tablename__ = "recipe_ingredient"

    __table_args__ = (
        CheckConstraint("amount_type IN ('main','minor','seasoning')", name="chk_amount_type"),
        # 表级约束：用量量化（文档 §10.4.13 chk_amount_quantified）
        CheckConstraint(
            "amount_value IS NOT NULL OR (amount_min IS NOT NULL AND amount_max IS NOT NULL)",
            name="chk_amount_quantified",
        ),
        Index("idx_ri_recipe", "recipe_id", "amount_type"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    recipe_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("recipe.id", ondelete="CASCADE"), nullable=False
    )
    ingredient_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("ingredient.id", ondelete="RESTRICT"), nullable=False
    )
    amount_value: Mapped[float | None] = mapped_column(Numeric(10, 2), nullable=True)
    amount_min: Mapped[float | None] = mapped_column(Numeric(10, 2), nullable=True)
    amount_max: Mapped[float | None] = mapped_column(Numeric(10, 2), nullable=True)
    amount_unit: Mapped[str | None] = mapped_column(String(10), nullable=True)
    amount_note: Mapped[str | None] = mapped_column(String(50), nullable=True)
    amount_type: Mapped[str] = mapped_column(String(10), nullable=False)
    sort_order: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=0, server_default="0")

    recipe: Mapped["Recipe"] = relationship(back_populates="ingredients")
    ingredient: Mapped["Ingredient"] = relationship()


class RecipeStep(Base):
    """菜谱步骤表（对应 §10.4.14 recipe_step）。

    说明：
        (recipe_id, step_no) 唯一；duration_seconds 供一键起计时器，
        key_point/failure_tips 支撑新手模式与失败补救。
    """

    __tablename__ = "recipe_step"

    __table_args__ = (
        UniqueConstraint("recipe_id", "step_no", name="uq_step_recipe_no"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    recipe_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("recipe.id", ondelete="CASCADE"), nullable=False
    )
    step_no: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    duration_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)
    key_point: Mapped[str | None] = mapped_column(String(200), nullable=True)
    failure_tips: Mapped[str | None] = mapped_column(Text, nullable=True)
    amount_hint: Mapped[str | None] = mapped_column(String(100), nullable=True)

    recipe: Mapped["Recipe"] = relationship(back_populates="steps")


class RecipeEmbedding(Base):
    """菜谱向量表（阶段二升级版，对应架构文档 §10.6 向量索引部分）。

    设计说明（重要）：
        - 🔴 embedding 向量列（pgvector vector(1024)）仅存在于数据库迁移中
          （迁移 b8d3f5a21c60 在 pgvector 扩展可用时创建，并建 ivfflat
          vector_cosine_ops 索引 lists=100），**不放 ORM**——避免 pgvector
          类型在无扩展环境（SQLite 测试/开发库）下建模崩溃；
          语义检索层对该列一律使用 raw SQL 访问。
        - embedding_json：1024 维浮点数组的 JSONB 便携存储（SQLite 测试与
          无 pgvector 扩展环境使用）；两者内容同构，写入层应双写。
        - 主键为独立 id（原「recipe_id 即主键」已改造）：source='ai_private'
          的 AI 私有向量行无对应 recipe 行（创新菜存于 innovation_recipe），
          recipe_id 改为可空外键。
        - source='verified' → recipe_id 指向官方菜谱；
          source='ai_private' → innovation_recipe_id + owner_user_id 必填
          （CHECK chk_recipe_embedding_chk_ai_owner 强制）。
    """

    __tablename__ = "recipe_embedding"

    __table_args__ = (
        CheckConstraint("source IN ('verified','ai_private')", name="chk_source"),
        CheckConstraint("source <> 'ai_private' OR owner_user_id IS NOT NULL", name="chk_ai_owner"),
        Index("idx_emb_recipe", "recipe_id"),
        Index("idx_emb_source", "source"),
        Index("idx_emb_owner", "owner_user_id"),
        Index("idx_emb_innovation", "innovation_recipe_id"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    recipe_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("recipe.id", ondelete="CASCADE"), nullable=True
    )
    # pgvector 向量列（vector(1024)）仅在迁移中存在，ORM 不映射（见类 docstring）
    embedding_json: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    owner_user_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("user.id", ondelete="CASCADE"), nullable=True
    )
    innovation_recipe_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("innovation_recipe.id", ondelete="CASCADE"), nullable=True
    )
    source: Mapped[str] = mapped_column(
        String(16), nullable=False, default="verified", server_default="verified"
    )
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), **_TS, nullable=False)
