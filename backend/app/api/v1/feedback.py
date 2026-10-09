"""用户反馈路由模块（模块 N）。

职责：
    POST /v1/feedback：提交反馈（content 先过 RiskEngine input 闸门；
    命中 → 200 {blocked:true, rule_id, message} 不落库；未命中 → 201 创建并返回回执）。
    GET  /v1/feedback/{feedback_id}：本人反馈状态查询（回执）。

落库映射（🔴 不改 feedback 表模型与 CHECK 约束）：
    - type：API 契约三类 → 表 CHECK 五类枚举：bug→malfunction（功能故障）、
      suggestion→other（建议归入其他）、other→other；
    - request_id：落 feedback.session_request_id 列（String(40)，超长截断）；
    - image_paths：落 feedback.images JSONB 列；
    - receipt_no：无独立列，由 "FB" + feedback_id 派生（查询时同样派生，口径一致）。

风控语义：
    - verdict.status='HIT'：命中规则即拦截（UGC 反馈属入库内容，命中即拦，
      不区分规则 block 标记），message 取 risk_message 话术兜底固定文案；
    - verdict.status='UNKNOWN'：风控不可用按「绝不放过」原则一并拦截
      （D9 红线同源），提示稍后重试。
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.v1.deps import ERR_NOT_FOUND, api_error, get_or_create_user, resolve_anonymous_id
from app.core.db import get_db
from app.core.logging import get_logger
from app.models import Feedback, User
from app.safety.engine import get_risk_engine
from app.schemas.feedback import FeedbackCreateRequest

router = APIRouter(prefix="/feedback", tags=["用户反馈"])

logger = get_logger(__name__)

# 回执号前缀（receipt_no = "FB" + feedback_id，派生口径无独立列）
RECEIPT_PREFIX = "FB"

# 承诺回复时效（小时）
EXPECTED_REPLY_HOURS = 24

# session_request_id 列宽（String(40)），超长截断落库
_REQUEST_ID_MAX_LEN = 40

# API 反馈类型 → feedback 表 CHECK 五类枚举映射（🔴 不改模型，见模块头）
_TYPE_TO_DB: dict[str, str] = {
    "bug": "malfunction",
    "suggestion": "other",
    "other": "other",
}

# 风控拦截兜底文案（risk_message 查询失败/UNKNOWN 时使用）
_FALLBACK_BLOCK_MESSAGE = "反馈内容包含违规信息，请修改后重新提交"
_UNKNOWN_BLOCK_MESSAGE = "安全校验暂不可用，请稍后重试"


def _receipt_no(feedback_id: int) -> str:
    """派生回执号（函数）。

    参数：
        feedback_id：反馈 ID。

    返回值：
        str："FB" + feedback_id（如 FB42）。

    异常：
        无。
    """
    return f"{RECEIPT_PREFIX}{feedback_id}"


@router.post("", summary="提交用户反馈（风控闸门 + 回执）")
def create_feedback(
    payload: FeedbackCreateRequest,
    request: Request,
    session: Session = Depends(get_db),
) -> JSONResponse:
    """提交反馈端点（函数）。

    说明：
        content 先过 RiskEngine input 闸门：HIT/UNKNOWN → 200 {blocked,...}
        不落库；放行 → 201 创建（type 按 CHECK 枚举映射落库）并返回回执。
        content 1~1000 字符由 Pydantic 校验（越界 422）。

    参数：
        payload：反馈请求体（content/type/request_id/image_paths）。
        request：FastAPI 请求对象（读 X-Anonymous-Id 头）。
        session：请求级数据库会话。

    返回值：
        JSONResponse：200 拦截体 {blocked:true, rule_id, message} 或
        201 创建体 {feedback_id, receipt_no, expected_reply_within_hours}。

    异常：
        数据库异常向上抛出（全局处理器兜底）；风控异常已由引擎内部消化。
    """
    user = get_or_create_user(session, resolve_anonymous_id(None, request))

    # 风控 input 闸门：命中（或风控不可用）即拦截，不落库
    verdict = get_risk_engine().scan("input", payload.content)
    if verdict.status == "HIT":
        message_obj = get_risk_engine().get_message(verdict.message_id) or {}
        message = str(message_obj.get("body") or message_obj.get("title") or _FALLBACK_BLOCK_MESSAGE)
        return JSONResponse(
            status_code=200,
            content={"blocked": True, "rule_id": verdict.rule_code, "message": message},
        )
    if verdict.status == "UNKNOWN":
        # 风控不可用：绝不放过（D9），提示稍后重试
        return JSONResponse(
            status_code=200,
            content={"blocked": True, "rule_id": None, "message": _UNKNOWN_BLOCK_MESSAGE},
        )

    feedback = Feedback(
        user_id=int(user.id),
        type=_TYPE_TO_DB[payload.type],
        content=payload.content,
        images=list(payload.image_paths or []),
        session_request_id=(payload.request_id or "")[:_REQUEST_ID_MAX_LEN] or None,
        status="pending",
    )
    session.add(feedback)
    session.commit()
    return JSONResponse(
        status_code=201,
        content={
            "feedback_id": int(feedback.id),
            "receipt_no": _receipt_no(int(feedback.id)),
            "expected_reply_within_hours": EXPECTED_REPLY_HOURS,
        },
    )


@router.get("/{feedback_id}", summary="反馈状态查询（回执）")
def get_feedback_status(
    feedback_id: int,
    request: Request,
    session: Session = Depends(get_db),
) -> JSONResponse:
    """反馈回执查询端点（函数）。

    说明：
        仅限本人查询（user_id 不匹配或不存在一律 404，不泄露他人工单）；
        status 来自 feedback.status 表字段（pending/processing/resolved/ignored）。

    参数：
        feedback_id：路径反馈 ID。
        request：FastAPI 请求对象（读 X-Anonymous-Id 头）。
        session：请求级数据库会话。

    返回值：
        JSONResponse：200 {status, receipt_no, created_at}。

    异常：
        HTTPException 404：反馈不存在或不属于本人。
    """
    user = session.execute(
        select(User).where(User.anonymous_id == (resolve_anonymous_id(None, request) or ""))
    ).scalar_one_or_none()
    if user is None:
        raise api_error(404, ERR_NOT_FOUND, "反馈不存在", f"feedback_id={feedback_id}")

    feedback = session.get(Feedback, feedback_id)
    if feedback is None or int(feedback.user_id or 0) != int(user.id):
        raise api_error(404, ERR_NOT_FOUND, "反馈不存在", f"feedback_id={feedback_id}")

    return JSONResponse(
        content={
            "status": feedback.status,
            "receipt_no": _receipt_no(int(feedback.id)),
            "created_at": feedback.created_at.isoformat() if feedback.created_at else None,
        }
    )
