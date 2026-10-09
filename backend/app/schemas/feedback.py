"""用户反馈 Schema 模块（模块 N）。

职责：
    /v1/feedback 的请求与响应模型：
    - POST /v1/feedback：提交反馈（先过 RiskEngine input 闸门，命中 200 拦截不落库，
      未命中 201 创建并返回回执）；
    - GET  /v1/feedback/{feedback_id}:本人反馈状态查询（回执）。

类型映射说明（🔴 不改 feedback 表 CHECK 约束）：
    API 契约三类 bug/suggestion/other → 表 CHECK 五类枚举：
    bug → malfunction（功能故障）、suggestion → other（建议归入其他）、other → other。
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

# 反馈类型（API 契约口径；落库前按模块头映射为表 CHECK 五类枚举）
FeedbackType = Literal["bug", "suggestion", "other"]


class FeedbackCreateRequest(BaseModel):
    """提交反馈请求体（模型类）。

    属性：
        content：反馈内容（1~1000 字符，必填）。
        type：反馈类型（bug/suggestion/other，默认 other）。
        request_id：关联的会话/推荐 request_id（可空，落 feedback.session_request_id）。
        image_paths：截图路径列表（可空，落 feedback.images JSONB）。
    """

    content: str = Field(min_length=1, max_length=1000)
    type: FeedbackType = "other"
    request_id: str | None = None
    image_paths: list[str] = Field(default_factory=list)


class FeedbackBlockedResponse(BaseModel):
    """风控拦截响应体（模型类）。

    说明：
        content 命中 RiskEngine input 闸门时返回（HTTP 200，不落库）。

    属性：
        blocked：是否被拦截（恒 true）。
        rule_id：命中的风控规则编码（如 FS-003；风控不可用时为 None）。
        message：拦截提示文案。
    """

    blocked: Literal[True] = True
    rule_id: str | None = None
    message: str = ""


class FeedbackCreateResponse(BaseModel):
    """反馈创建响应体（模型类）。

    属性：
        feedback_id：反馈 ID。
        receipt_no：回执号（"FB" + feedback_id 派生，无独立列）。
        expected_reply_within_hours：承诺回复时效（小时）。
    """

    feedback_id: int
    receipt_no: str
    expected_reply_within_hours: int = 24


class FeedbackStatusResponse(BaseModel):
    """反馈回执查询响应体（模型类）。

    属性：
        status：处理状态（pending/processing/resolved/ignored，来自表字段）。
        receipt_no：回执号。
        created_at：提交时间（ISO 8601）。
    """

    status: str
    receipt_no: str
    created_at: str | None = None
