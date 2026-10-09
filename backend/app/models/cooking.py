"""烹饪与记录域 ORM 模型。

职责：
    按架构文档 §10.4.15~§10.4.18、§10.4.24 建模：
    cooking_session / cooking_help_log / recipe_feedback / shopping_list_item / meal_record。
"""

from datetime import date, datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Numeric,
    SmallInteger,
    String,
    Text,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base

# 时间列公共参数：服务端默认 now()（TIMESTAMPTZ 类型在使用处显式传入）
_TS = {"server_default": func.now()}


class InventoryItem(Base):
    """库存条目表（对应 §10.4.11 inventory_item）。

    说明：
        数量三档（has/little/enough）与五态状态机（normal/expiring/consumed/expired/deleted）；
        expiry_date 为用户自填，仅提醒用途（RL-3）；
        idx_inv_expiry 为部分索引（仅索引 status IN (normal,expiring) 行，临期窗口扫描）。
    """

    __tablename__ = "inventory_item"

    __table_args__ = (
        CheckConstraint("quantity_level IN ('has','little','enough')", name="chk_quantity_level"),
        CheckConstraint("storage IN ('fridge','freezer','room','dry')", name="chk_storage"),
        CheckConstraint(
            "status IN ('normal','expiring','consumed','expired','deleted')", name="chk_status"
        ),
        CheckConstraint("source IN ('manual','vision','recipe')", name="chk_source"),
        Index("idx_inv_user_status", "user_id", "status"),
        # 部分索引：临期窗口扫描只覆盖在库状态行（§10.6 索引设计原则 2）
        Index(
            "idx_inv_expiry",
            "user_id",
            "expiry_date",
            postgresql_where=text("status IN ('normal','expiring')"),
        ),
        Index("idx_inv_ingredient", "ingredient_id"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("user.id", ondelete="CASCADE"), nullable=False
    )
    ingredient_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("ingredient.id", ondelete="RESTRICT"), nullable=False
    )
    quantity_level: Mapped[str] = mapped_column(String(10), nullable=False)
    storage: Mapped[str] = mapped_column(String(10), nullable=False)
    purchase_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    expiry_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    status: Mapped[str] = mapped_column(String(12), nullable=False, default="normal", server_default="normal")
    source: Mapped[str] = mapped_column(String(10), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), **_TS, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), **_TS, nullable=False)


class CookingSession(Base):
    """烹饪会话表（对应 §10.4.15 cooking_session）。

    说明：
        会话 ID 即 LangGraph thread_id；status 状态机见架构文档 §12.1；
        current_step_no 支撑断点续做。
    """

    __tablename__ = "cooking_session"

    __table_args__ = (
        CheckConstraint(
            "status IN ('not_started','allergen_checking','ongoing','rating','completed')",
            name="chk_status",
        ),
        Index("idx_session_user_status", "user_id", "status"),
        Index("idx_session_recipe", "recipe_id"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("user.id", ondelete="CASCADE"), nullable=False
    )
    recipe_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("recipe.id", ondelete="RESTRICT"), nullable=False
    )
    servings: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    current_step_no: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=1, server_default="1")
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    allergen_conflict: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")
    allergen_conflict_ack: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")
    abandoned_step_no: Mapped[int | None] = mapped_column(SmallInteger, nullable=True)
    timers: Mapped[list] = mapped_column(JSONB, nullable=False, default=list, server_default="[]")
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), **_TS, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), **_TS, nullable=False)


class CookingHelpLog(Base):
    """烹饪求助记录表（对应 §10.4.16 cooking_help_log）。

    说明：
        烹饪中的即时问答（≤3 条要点），risk_hit 记录是否命中风控规则。
    """

    __tablename__ = "cooking_help_log"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    session_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("cooking_session.id", ondelete="CASCADE"), nullable=False
    )
    question: Mapped[str] = mapped_column(String(500), nullable=False)
    answer: Mapped[str] = mapped_column(Text, nullable=False)
    risk_hit: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")
    rule_code: Mapped[str | None] = mapped_column(String(30), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), **_TS, nullable=False)


class RecipeFeedback(Base):
    """菜谱评分与反馈表（对应 §10.4.17 recipe_feedback）。

    说明：
        feedback_type（like/dislike/cooked）为推荐排序的历史偏好信号。
    """

    __tablename__ = "recipe_feedback"

    __table_args__ = (
        CheckConstraint("rating IS NULL OR (rating >= 1 AND rating <= 5)", name="chk_rating_range"),
        CheckConstraint("feedback_type IN ('like','dislike','cooked')", name="chk_feedback_type"),
        Index("idx_fb_user_recipe", "user_id", "recipe_id"),
        Index("idx_fb_type", "recipe_id", "feedback_type"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("user.id", ondelete="CASCADE"), nullable=False
    )
    recipe_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("recipe.id"), nullable=False)
    session_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("cooking_session.id"), nullable=True
    )
    rating: Mapped[int | None] = mapped_column(SmallInteger, nullable=True)
    tags: Mapped[list] = mapped_column(JSONB, nullable=False, default=list, server_default="[]")
    feedback_type: Mapped[str] = mapped_column(String(10), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), **_TS, nullable=False)


class ShoppingListItem(Base):
    """购物清单条目表（对应 §10.4.18 shopping_list_item）。

    说明：
        支持自定义条目（ingredient_id 可空），source_recipe_ids 记录多道菜合并来源。
    """

    __tablename__ = "shopping_list_item"

    __table_args__ = (Index("idx_sl_user_checked", "user_id", "checked"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("user.id", ondelete="CASCADE"), nullable=False
    )
    ingredient_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("ingredient.id"), nullable=True
    )
    name: Mapped[str] = mapped_column(String(50), nullable=False)
    category: Mapped[str | None] = mapped_column(String(20), nullable=True)
    source_recipe_ids: Mapped[list] = mapped_column(JSONB, nullable=False, default=list, server_default="[]")
    checked: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), **_TS, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), **_TS, nullable=False)


class MealRecord(Base):
    """饮食记录表（对应 §10.4.24 meal_record）。

    说明：
        做菜完成自动记录（source=cooking）或手动补录（source=manual）；
        营养字段为估算值，NULL 表示未纳入统计。
    """

    __tablename__ = "meal_record"

    __table_args__ = (
        CheckConstraint("meal_type IN ('breakfast','lunch','dinner','snack')", name="chk_meal_type"),
        CheckConstraint("source IN ('cooking','manual')", name="chk_source"),
        Index("idx_meal_user_date", "user_id", "recorded_date"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("user.id", ondelete="CASCADE"), nullable=False
    )
    recorded_date: Mapped[date] = mapped_column(Date, nullable=False)
    meal_type: Mapped[str] = mapped_column(String(10), nullable=False)
    recipe_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("recipe.id"), nullable=True)
    custom_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    servings: Mapped[float | None] = mapped_column(Numeric(5, 2), nullable=True)
    kcal: Mapped[float | None] = mapped_column(Numeric(8, 2), nullable=True)
    protein_g: Mapped[float | None] = mapped_column(Numeric(8, 2), nullable=True)
    fat_g: Mapped[float | None] = mapped_column(Numeric(8, 2), nullable=True)
    carbs_g: Mapped[float | None] = mapped_column(Numeric(8, 2), nullable=True)
    sodium_mg: Mapped[float | None] = mapped_column(Numeric(8, 2), nullable=True)
    source: Mapped[str] = mapped_column(String(10), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), **_TS, nullable=False)
