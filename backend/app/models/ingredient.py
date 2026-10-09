"""食材域 ORM 模型。

职责：
    按架构文档 §10.4.8~§10.4.10 建模：ingredient / ingredient_alias / ingredient_nutrition，
    含 10 分类 CHECK、GIN 致敏原索引与营养数据一对一关系。
"""

from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Numeric,
    String,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base

# 时间列公共参数：服务端默认 now()（TIMESTAMPTZ 类型在使用处显式传入）
_TS = {"server_default": func.now()}


class Ingredient(Base):
    """食材表（对应 §10.4.8 ingredient）。

    说明：
        category 为 10 分类（veg/meat/seafood/egg_milk/soy/staple/seasoning/dry/frozen/other）；
        allergen_codes 为 GB 7718 八类 code；allergen_verified=false 时前端展示「待核实」。
    """

    __tablename__ = "ingredient"

    __table_args__ = (
        CheckConstraint(
            "category IN ('veg','meat','seafood','egg_milk','soy','staple',"
            "'seasoning','dry','frozen','other')",
            name="chk_category",
        ),
        Index("idx_ing_category", "category"),
        Index("gin_ing_allergen", "allergen_codes", postgresql_using="gin"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(50), nullable=False)
    category: Mapped[str] = mapped_column(String(20), nullable=False)
    allergen_codes: Mapped[list] = mapped_column(JSONB, nullable=False, default=list, server_default="[]")
    allergen_verified: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")
    unit_conversion: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="true")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), **_TS, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), **_TS, nullable=False)

    aliases: Mapped[list["IngredientAlias"]] = relationship(
        back_populates="ingredient", cascade="all, delete-orphan"
    )
    nutrition: Mapped["IngredientNutrition | None"] = relationship(
        back_populates="ingredient", cascade="all, delete-orphan", uselist=False
    )


class IngredientAlias(Base):
    """食材别名表（对应 §10.4.9 ingredient_alias）。

    说明：
        支持别名检索（西红柿/番茄/洋柿子），随食材级联删除。
    """

    __tablename__ = "ingredient_alias"

    __table_args__ = (Index("idx_alias_text", "alias"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    ingredient_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("ingredient.id", ondelete="CASCADE"), nullable=False
    )
    alias: Mapped[str] = mapped_column(String(50), nullable=False)

    ingredient: Mapped["Ingredient"] = relationship(back_populates="aliases")


class IngredientNutrition(Base):
    """营养数据表（对应 §10.4.10 ingredient_nutrition）。

    说明：
        与食材一对一；字段为 NULL 即「未纳入统计」，不得按 0 计算（PRD §8.4）。
    """

    __tablename__ = "ingredient_nutrition"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    ingredient_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("ingredient.id", ondelete="CASCADE"), unique=True, nullable=False
    )
    kcal_100g: Mapped[float | None] = mapped_column(Numeric(8, 2), nullable=True)
    protein_g: Mapped[float | None] = mapped_column(Numeric(8, 2), nullable=True)
    fat_g: Mapped[float | None] = mapped_column(Numeric(8, 2), nullable=True)
    carbs_g: Mapped[float | None] = mapped_column(Numeric(8, 2), nullable=True)
    sodium_mg: Mapped[float | None] = mapped_column(Numeric(8, 2), nullable=True)
    data_source: Mapped[str] = mapped_column(String(100), nullable=False)
    source_license: Mapped[str] = mapped_column(String(50), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), **_TS, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), **_TS, nullable=False)

    ingredient: Mapped["Ingredient"] = relationship(back_populates="nutrition")
