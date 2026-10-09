"""认证路由模块。

职责：
    POST /v1/auth/anonymous：匿名会话（upsert user，返回 user_id 与 anonymous_id）。
    幂等：传入已存在的 anonymous_id 直接复用既有用户行（不重复建行）。
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app.api.v1.deps import get_or_create_user, resolve_anonymous_id
from app.core.db import get_db
from app.schemas.auth import AnonymousRequest, AnonymousResponse

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/anonymous", response_model=AnonymousResponse, summary="创建/复用匿名会话")
def create_anonymous_session(
    payload: AnonymousRequest | None = None,
    request: Request = None,
    session: Session = Depends(get_db),
) -> AnonymousResponse:
    """创建或复用匿名会话（函数）。

    说明：
        传 anonymous_id 时复用既有用户（upsert），否则生成 anon_ 前缀新用户；
        请求体可整体缺省（前端首次进入仅发送 client_type）。

    参数：
        payload：请求体（可 None）。
        request：FastAPI 请求对象（读 X-Anonymous-Id 头）。
        session：请求级数据库会话。

    返回值：
        AnonymousResponse：{user_id, anonymous_id}。

    异常：
        数据库异常向上抛出（全局异常处理器兜底 500）。
    """
    body = payload or AnonymousRequest()
    anon_id = resolve_anonymous_id(body.anonymous_id, request)
    user = get_or_create_user(session, anon_id)
    session.commit()
    return AnonymousResponse(user_id=int(user.id), anonymous_id=user.anonymous_id)
