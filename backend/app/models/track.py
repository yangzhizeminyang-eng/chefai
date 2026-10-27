"""用户行为埋点域 ORM 模型。

职责：
    建模埋点接收闭环数据层单表：
    - track_event：客户端行为埋点事件（匿名 ID + 事件名 + JSONB 属性），
      由 POST /v1/track/events 批量接收写入，供管理员 GET /v1/track/events
      审计查询与按 TRACK_RETENTION_DAYS 超期清理。

说明：
    本表由迁移 b2f6d9a4c7e1 建（down_revision=9c3e1f7a52b8）。
    敏感字段剥离（password/token/cookie/authorization/api_key 等）在 API 层
    写入前完成，本表不存原值；事件名以白名单校验（38 客户端事件 + app_error）。
"""

from datetime import datetime

from sqlalchemy import BigInteger, DateTime, Index, String, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base

# 时间列公共参数：服务端默认 now()（与 innovation.py 同口径）
_TS = {"server_default": func.now()}


class TrackEvent(Base):
    """用户行为埋点事件表（埋点接收闭环核心表）。

    说明：
        - anonymous_id：客户端 X-Anonymous-Id 头透传；无头请求记 NULL
          （纯匿名），不建用户行、不建外键（埋点与用户生命周期解耦，
          用户注销后事件保留至保留期自然过期）；
        - event_name：白名单事件名（客户端 38 事件 + 运维事件 app_error）；
        - properties：事件属性 JSONB（写入前已剥离敏感键值，≤4KB）；
        - request_id：生成事件时的客户端幂等键（与服务端日志对账用）；
        - client_ts：客户端本地事件时间（毫秒时间戳转 UTC，非法/缺失为 NULL）；
        - created_at：服务端接收时间（保留期清理依据）；
        - 索引：按匿名 ID 与事件名的时间窗口查询（管理员审计/统计口径）。
    """

    __tablename__ = "track_event"

    __table_args__ = (
        Index("idx_track_event_anonymous", "anonymous_id", "created_at"),
        Index("idx_track_event_name", "event_name", "created_at"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    anonymous_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    event_name: Mapped[str] = mapped_column(String(64), nullable=False)
    properties: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    request_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    client_ts: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), **_TS, nullable=False)
