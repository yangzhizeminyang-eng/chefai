"""API 通用 Schema 模块。

职责：
    定义跨域复用的响应模型：RiskDetailOut（风险详情，一票否决响应与 trace 判定共用）。
    字段命名以前端 web-stage1/src/api/types.ts 为权威契约：
    - rule_code / rule_id 同值并存（W-05 消费 rule_code，W-06 消费 rule_id）；
    - blocked 响应体不声明 results/candidates/nutrition 字段（D9 红线：结构上无承载位）。
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class RiskDetailOut(BaseModel):
    """风险详情（模型类）。

    说明：
        一票否决短路响应 risk 对象与 GET /v1/trace 判定卡共用的结构；
        话术字段（title/body/correct_action/after_consumption_advice）来自 risk_message 表。

    属性：
        category：风险类别（food_safety_high_risk / medical_refusal / pseudoscience / injection 等）。
        rule_code：命中规则编码（如 FS-018 / INJ-001）。
        rule_id：规则 ID（与 rule_code 同值，兼容前端 TraceRisk.rule_id 读取）。
        risk_level：风险等级（critical / high / medium）。
        message_id：话术模板 ID（risk_message 表，内置内存规则可为 None）。
        title：风险说明标题。
        body：风险说明正文。
        correct_action：正确做法。
        after_consumption_advice：已食用处置建议（就医引导）。
        evidence_ref：依据来源引用（如 ["FS-001@rules-v1.0"]）。
    """

    category: str | None = None
    rule_code: str | None = None
    rule_id: str | None = None
    risk_level: str | None = None
    message_id: str | None = None
    title: str | None = None
    body: str | None = None
    correct_action: str | None = None
    after_consumption_advice: str | None = None
    evidence_ref: list[str] = Field(default_factory=list)
