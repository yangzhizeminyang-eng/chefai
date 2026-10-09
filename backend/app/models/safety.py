"""风控与调度域 ORM 模型。

职责：
    按架构文档 §10.4.19~§10.4.22 建模：risk_rule / risk_message / risk_log / agent_trace。
    话术全部来自 risk_message 表（RL-1：不由模型生成）；
    agent_trace.status 为七态编排状态（§12.4）。
"""

from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base

# 时间列公共参数：服务端默认 now()（TIMESTAMPTZ 类型在使用处显式传入）
_TS = {"server_default": func.now()}


class RiskMessage(Base):
    """风控话术模板表（对应 §10.4.20 risk_message）。

    说明：
        message_id 唯一；食品安全类话术 correct_action / after_consumption_advice 必填；
        医疗拒答类 body 使用 PRD TXT-G04 固定口径，伪科学类使用 TXT-G05 口径。
    """

    __tablename__ = "risk_message"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    message_id: Mapped[str] = mapped_column(String(40), unique=True, nullable=False)
    category: Mapped[str] = mapped_column(String(30), nullable=False)
    title: Mapped[str] = mapped_column(String(100), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    correct_action: Mapped[str | None] = mapped_column(Text, nullable=True)
    after_consumption_advice: Mapped[str | None] = mapped_column(Text, nullable=True)
    disclaimer_id: Mapped[str] = mapped_column(String(30), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), **_TS, nullable=False)


class RiskRule(Base):
    """风控规则表（对应 §10.4.19 risk_rule，🔴 阶段一核心）。

    说明：
        trigger_condition 为 JSONB：
        - 任意命中：{"keywords": [...], "any": true}
        - 组合命中（各组内任一命中、组间需全部命中）：
          {"keywords": [...], "any": true, "mode": "all_groups", "groups": [[...], [...]]}
        (rule_code, version) 唯一（uq_rule_code_version）；
        signed_by_expert 阶段一恒 false。
    """

    __tablename__ = "risk_rule"

    __table_args__ = (
        CheckConstraint(
            "category IN ('food_safety_high_risk','special_population','medical_refusal',"
            "'pseudoscience','output_ban')",
            name="chk_category",
        ),
        CheckConstraint("stage_scope IN ('input','output','both')", name="chk_stage_scope"),
        CheckConstraint("risk_level IN ('critical','high','medium')", name="chk_risk_level"),
        Index("idx_rule_stage_enabled", "stage_scope", "enabled"),
        UniqueConstraint("rule_code", "version", name="uq_rule_code_version"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    rule_code: Mapped[str] = mapped_column(String(30), nullable=False)
    category: Mapped[str] = mapped_column(String(30), nullable=False)
    stage_scope: Mapped[str] = mapped_column(String(10), nullable=False)
    trigger_condition: Mapped[dict] = mapped_column(JSONB, nullable=False)
    response_message_id: Mapped[str | None] = mapped_column(
        String(40), ForeignKey("risk_message.message_id", ondelete="RESTRICT"), nullable=True
    )
    block: Mapped[bool] = mapped_column(Boolean, nullable=False)
    risk_level: Mapped[str] = mapped_column(String(10), nullable=False)
    evidence_ref: Mapped[str | None] = mapped_column(String(200), nullable=True)
    signed_by_expert: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")
    version: Mapped[str] = mapped_column(String(20), nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="true")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), **_TS, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), **_TS, nullable=False)

    message: Mapped["RiskMessage | None"] = relationship(foreign_keys=[response_message_id])


class RiskLog(Base):
    """风控日志表（对应 §10.4.21 risk_log）。

    说明：
        每次风控命中/放行留痕；input_digest 为脱敏摘要；按月归档（预留）。
    """

    __tablename__ = "risk_log"

    __table_args__ = (
        CheckConstraint("stage IN ('input','output')", name="chk_stage"),
        CheckConstraint("action IN ('blocked','safe_mode','passed')", name="chk_action"),
        Index("idx_risklog_created", "created_at"),
        Index("idx_risklog_rule", "rule_code", "created_at"),
        Index("idx_risklog_request", "request_id"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    request_id: Mapped[str] = mapped_column(String(40), nullable=False)
    session_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    user_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    stage: Mapped[str] = mapped_column(String(10), nullable=False)
    rule_code: Mapped[str | None] = mapped_column(String(30), nullable=True)
    category: Mapped[str | None] = mapped_column(String(30), nullable=True)
    risk_level: Mapped[str | None] = mapped_column(String(10), nullable=True)
    input_digest: Mapped[str | None] = mapped_column(String(200), nullable=True)
    action: Mapped[str] = mapped_column(String(12), nullable=False)
    message_id: Mapped[str | None] = mapped_column(String(40), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), **_TS, nullable=False)


class AgentTrace(Base):
    """Agent 调用日志表（对应 §10.4.22 agent_trace）。

    说明：
        每个编排节点一条 span；status 七态：
        not_executed / running / ok / degraded / failed / timeout / skipped_by_veto；
        user_id 只存哈希（NFR-7.4 脱敏），健康信息不入 trace。
    """

    __tablename__ = "agent_trace"

    __table_args__ = (
        CheckConstraint(
            "status IN ('not_executed','running','ok','degraded','failed','timeout','skipped_by_veto')",
            name="chk_status",
        ),
        Index("idx_trace_request", "request_id"),
        Index("idx_trace_created_node", "created_at", "node_name"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    request_id: Mapped[str] = mapped_column(String(40), nullable=False)
    thread_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    user_id_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    node_name: Mapped[str] = mapped_column(String(40), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    model_name: Mapped[str | None] = mapped_column(String(50), nullable=True)
    prompt_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    completion_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    cost_cents: Mapped[float | None] = mapped_column(Numeric(10, 4), nullable=True)
    rule_hit: Mapped[str | None] = mapped_column(String(30), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), **_TS, nullable=False)
