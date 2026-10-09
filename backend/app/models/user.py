"""用户域 ORM 模型。

职责：
    按架构文档 §10.4.1~§10.4.7 建模：user / disclaimer_consent / consent_record /
    family / family_member / user_skill_profile / diet_goal 七张表，
    含 family_member 的 chk_allergen_required 表级 CHECK（过敏原必选，Q-13）；
    阶段二扩展：User.preferences JSONB 用户偏好列（字号/单位/提醒/语音开关）、
    FavoriteRecipe 收藏表（软删分组收藏）。
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
    SmallInteger,
    String,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import INET, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base

# 时间列公共参数：服务端默认 now()（TIMESTAMPTZ 类型在使用处显式传入）
_TS = {"server_default": func.now()}


class User(Base):
    """用户表（对应 §10.4.1 user）。

    说明：
        阶段一以匿名会话为主（anonymous_id 唯一），微信字段阶段二填充。
        `user` 为 PG 保留字风险项，SQLAlchemy 自动加引号处理，表名照文档保留。
    """

    __tablename__ = "user"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    anonymous_id: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    wx_openid: Mapped[str | None] = mapped_column(String(64), unique=True, nullable=True)
    wx_unionid: Mapped[str | None] = mapped_column(String(64), nullable=True)
    phone: Mapped[str | None] = mapped_column(String(20), nullable=True)
    nickname: Mapped[str | None] = mapped_column(String(50), nullable=True)
    avatar_url: Mapped[str | None] = mapped_column(String(255), nullable=True)
    # 阶段二扩展：用户偏好（字号/单位/提醒/语音开关等），NULL 视为全默认
    preferences: Mapped[dict | None] = mapped_column(JSONB, nullable=True, default=dict,
                                                      server_default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), **_TS, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), **_TS, nullable=False)

    # uq_user_openid：部分唯一索引（仅对非空 wx_openid 生效，§10.6）
    __table_args__ = (
        Index(
            "uq_user_openid",
            "wx_openid",
            unique=True,
            postgresql_where=text("wx_openid IS NOT NULL"),
        ),
    )


class DisclaimerConsent(Base):
    """免责同意记录表（对应 §10.4.2 disclaimer_consent）。

    说明：
        记录用户对免责声明的同意（PRD §6.1 US-A1），随用户注销级联删除。
    """

    __tablename__ = "disclaimer_consent"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("user.id", ondelete="CASCADE"), nullable=False
    )
    agreement_version: Mapped[str] = mapped_column(String(20), nullable=False)
    agreed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    device_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    ip: Mapped[str | None] = mapped_column(INET, nullable=True)


class ConsentRecord(Base):
    """敏感个人信息单独同意表（对应 §10.4.3 consent_record）。

    说明：
        过敏原/健康目标/特殊人群录入前需单独同意（PRD RL-14）。
    """

    __tablename__ = "consent_record"

    __table_args__ = (
        CheckConstraint(
            "scope IN ('allergen','health_goal','special_population')",
            name="chk_scope",
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("user.id", ondelete="CASCADE"), nullable=False
    )
    scope: Mapped[str] = mapped_column(String(30), nullable=False)
    version: Mapped[str] = mapped_column(String(20), nullable=False)
    agreed: Mapped[bool] = mapped_column(Boolean, nullable=False)
    agreed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class Family(Base):
    """家庭档案表（对应 §10.4.4 family）。

    说明：
        一名用户一份家庭档案（软删除），免费档成员上限 4（PRD Q-14）。
    """

    __tablename__ = "family"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("user.id"), nullable=False)
    name: Mapped[str] = mapped_column(String(50), nullable=False)
    member_limit: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=4, server_default="4")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), **_TS, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), **_TS, nullable=False)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    members: Mapped[list["FamilyMember"]] = relationship(
        back_populates="family", cascade="all, delete-orphan"
    )


class FamilyMember(Base):
    """家庭成员表（对应 §10.4.5 family_member，🔴 风控强依赖）。

    说明：
        allergen_codes 为 GB 7718 八类致敏原 code 集合（JSONB + GIN 索引），
        表级 CHECK 强制「过敏原必选」：勾选「暂无已知过敏」或至少选择一项过敏原。
    """

    __tablename__ = "family_member"

    __table_args__ = (
        # 年龄段枚举约束
        CheckConstraint(
            "age_group IN ('0-3','4-12','13-17','18-59','60+')", name="chk_age_group"
        ),
        # 口味三项 0-2 档约束
        CheckConstraint(
            "(taste_spicy IS NULL OR (taste_spicy >= 0 AND taste_spicy <= 2))"
            " AND (taste_salt IS NULL OR (taste_salt >= 0 AND taste_salt <= 2))"
            " AND (taste_sweet IS NULL OR (taste_sweet >= 0 AND taste_sweet <= 2))",
            name="chk_taste_range",
        ),
        # 表级约束：过敏原必选（文档 §10.4.5 chk_allergen_required）
        CheckConstraint(
            "no_known_allergen = true OR jsonb_array_length(allergen_codes) > 0",
            name="chk_allergen_required",
        ),
        Index("idx_member_family", "family_id"),
        Index("gin_member_allergen", "allergen_codes", postgresql_using="gin"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    family_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("family.id", ondelete="CASCADE"), nullable=False
    )
    nickname: Mapped[str] = mapped_column(String(10), nullable=False)
    age_group: Mapped[str] = mapped_column(String(20), nullable=False)
    taste_spicy: Mapped[int | None] = mapped_column(SmallInteger, nullable=True)
    taste_salt: Mapped[int | None] = mapped_column(SmallInteger, nullable=True)
    taste_sweet: Mapped[int | None] = mapped_column(SmallInteger, nullable=True)
    dietary_restrictions: Mapped[list] = mapped_column(JSONB, nullable=False, default=list, server_default="[]")
    allergen_codes: Mapped[list] = mapped_column(JSONB, nullable=False, default=list, server_default="[]")
    no_known_allergen: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")
    special_diet: Mapped[list] = mapped_column(JSONB, nullable=False, default=list, server_default="[]")
    special_population: Mapped[list] = mapped_column(JSONB, nullable=False, default=list, server_default="[]")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), **_TS, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), **_TS, nullable=False)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    family: Mapped["Family"] = relationship(back_populates="members")


class UserSkillProfile(Base):
    """厨艺与设备档案表（对应 §10.4.6 user_skill_profile）。

    说明：
        一人一份（user_id 唯一），equipment 为设备 JSONB 数组（编码须在
        schemas.profile.EQUIPMENT_WHITELIST 白名单内；推荐链路经 runner 载入
        SafetyProfile 供 hard_filter 设备维度差集判定）。
    """

    __tablename__ = "user_skill_profile"

    __table_args__ = (
        CheckConstraint(
            "skill_level IN ('beginner','skilled','expert')", name="chk_skill_level"
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("user.id", ondelete="CASCADE"), unique=True, nullable=False
    )
    skill_level: Mapped[str] = mapped_column(String(12), nullable=False)
    difficulty_cap: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=2, server_default="2")
    equipment: Mapped[list] = mapped_column(JSONB, nullable=False, default=list, server_default="[]")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), **_TS, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), **_TS, nullable=False)


class DietGoal(Base):
    """饮食目标表（对应 §10.4.7 diet_goal）。

    说明：
        5 类目标（balanced/fat_loss/muscle_gain/sugar_control/low_sodium）；
        compliance_ack_at 记录疾病相关目标的合规提示确认（US-G3）。
    """

    __tablename__ = "diet_goal"

    __table_args__ = (
        CheckConstraint(
            "goal_type IN ('balanced','fat_loss','muscle_gain','sugar_control','low_sodium')",
            name="chk_goal_type",
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("user.id", ondelete="CASCADE"), nullable=False
    )
    goal_type: Mapped[str] = mapped_column(String(20), nullable=False)
    target_kcal: Mapped[int | None] = mapped_column(nullable=True)
    effective_from: Mapped[date] = mapped_column(Date, nullable=False)
    effective_to: Mapped[date | None] = mapped_column(Date, nullable=True)
    compliance_ack_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), **_TS, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), **_TS, nullable=False)


class FavoriteRecipe(Base):
    """收藏菜谱表（阶段二扩展，软删除分组收藏）。

    说明：
        - 唯一性由 partial unique index uq_favorite_user_recipe 保证：
          仅对 deleted_at IS NULL 的未删行约束 (user_id, recipe_id) 唯一，
          软删后允许重新收藏；
        - group_name 支持分组收藏（默认「默认分组」），note 为收藏备注；
        - 用户/菜谱删除均级联清理收藏行。
    """

    __tablename__ = "favorite_recipe"

    __table_args__ = (
        Index(
            "uq_favorite_user_recipe",
            "user_id",
            "recipe_id",
            unique=True,
            postgresql_where=text("deleted_at IS NULL"),
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("user.id", ondelete="CASCADE"), nullable=False
    )
    recipe_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("recipe.id", ondelete="CASCADE"), nullable=False
    )
    group_name: Mapped[str] = mapped_column(
        String(64), nullable=False, default="默认分组", server_default="默认分组"
    )
    note: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), **_TS, nullable=False)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
