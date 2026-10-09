"""运营与配置域 ORM 模型。

职责：
    按架构文档 §10.4.23、§10.4.25~§10.4.28 建模：
    order / remote_config / admin_user / operation_log / feedback。
"""

from datetime import datetime

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import INET, JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base

# 时间列公共参数：服务端默认 now()（TIMESTAMPTZ 类型在使用处显式传入）
_TS = {"server_default": func.now()}


class Order(Base):
    """订单表（对应 §10.4.23 order）。

    说明：
        金额以分存储（*_cents，避免浮点）；交易凭证不随用户删除。
    """

    __tablename__ = "order"

    __table_args__ = (
        CheckConstraint(
            "status IN ('pending','paid','failed','refunded','closed')", name="chk_status"
        ),
        UniqueConstraint("order_no", name="uq_order_no"),
        Index("idx_order_user", "user_id", "status"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    order_no: Mapped[str] = mapped_column(String(40), unique=True, nullable=False)
    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("user.id"), nullable=False)
    product_type: Mapped[str] = mapped_column(String(20), nullable=False)
    amount_cents: Mapped[int] = mapped_column(Integer, nullable=False)
    currency: Mapped[str] = mapped_column(String(8), nullable=False, default="CNY", server_default="CNY")
    status: Mapped[str] = mapped_column(String(12), nullable=False)
    wx_transaction_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    paid_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), **_TS, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), **_TS, nullable=False)


class RemoteConfig(Base):
    """远程开关与权重配置表（对应 §10.4.25 remote_config）。

    说明：
        config_key 唯一（switch.* 四开关 + rank.weights 等）；
        阶段一不引入 Redis，应用侧以 60s 内生效的进程内缓存消费本表（spec D6）。
    """

    __tablename__ = "remote_config"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    config_key: Mapped[str] = mapped_column(String(60), unique=True, nullable=False)
    value: Mapped[dict | bool | list] = mapped_column(JSONB, nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1, server_default="1")
    updated_by: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("admin_user.id"), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), **_TS, nullable=False)


class AdminUser(Base):
    """后台账号表（对应 §10.4.26 admin_user）。

    说明：
        三级角色（super_admin/content_ops/readonly，US-K6）；
        password_hash 阶段一使用 pbkdf2_hmac 加盐哈希，阶段二接完整认证体系。
    """

    __tablename__ = "admin_user"

    __table_args__ = (
        CheckConstraint("role IN ('super_admin','content_ops','readonly')", name="chk_role"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    username: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[str] = mapped_column(String(20), nullable=False)
    status: Mapped[str] = mapped_column(String(10), nullable=False, default="active", server_default="active")
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), **_TS, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), **_TS, nullable=False)


class OperationLog(Base):
    """后台操作日志表（对应 §10.4.27 operation_log）。

    说明：
        记录改前/改后快照（US-K6 审计），操作日志不随账号删除。
    """

    __tablename__ = "operation_log"

    __table_args__ = (Index("idx_oplog_module_time", "module", "created_at"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    admin_user_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("admin_user.id"), nullable=True
    )
    module: Mapped[str] = mapped_column(String(30), nullable=False)
    action: Mapped[str] = mapped_column(String(30), nullable=False)
    target_type: Mapped[str | None] = mapped_column(String(30), nullable=True)
    target_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    before_snapshot: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    after_snapshot: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    ip: Mapped[str | None] = mapped_column(INET, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), **_TS, nullable=False)


class Feedback(Base):
    """用户反馈表（对应 §10.4.28 feedback）。

    说明：
        五类反馈工单（content_error/vision_inaccurate/recommend_inaccurate/malfunction/other），
        session_request_id 关联会话日志（US-N1），保留但脱敏。
    """

    __tablename__ = "feedback"

    __table_args__ = (
        CheckConstraint(
            "type IN ('content_error','vision_inaccurate','recommend_inaccurate','malfunction','other')",
            name="chk_type",
        ),
        CheckConstraint(
            "status IN ('pending','processing','resolved','ignored')", name="chk_status"
        ),
        Index("idx_fb_status", "status", "created_at"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("user.id"), nullable=True)
    type: Mapped[str] = mapped_column(String(20), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    images: Mapped[list] = mapped_column(JSONB, nullable=False, default=list, server_default="[]")
    session_request_id: Mapped[str | None] = mapped_column(String(40), nullable=True)
    status: Mapped[str] = mapped_column(String(12), nullable=False, default="pending", server_default="pending")
    reply: Mapped[str | None] = mapped_column(Text, nullable=True)
    replied_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), **_TS, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), **_TS, nullable=False)
