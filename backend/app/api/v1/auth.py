"""认证路由模块。

职责：
    POST /v1/auth/anonymous：匿名会话（upsert user，返回 user_id 与 anonymous_id）。
    幂等：传入已存在的 anonymous_id 直接复用既有用户行（不重复建行）。
    POST /v1/auth/register：注册（绑定/新建用户，签发 JWT）。
    POST /v1/auth/login：用户名密码登录（签发 JWT）。
    GET  /v1/auth/me：当前登录用户信息（JWT 鉴权）。
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.v1.deps import api_error, get_or_create_user, resolve_anonymous_id
from app.core.db import get_db
from app.core.user_security import (
    create_user_token,
    hash_password,
    user_id_from_request,
    verify_password,
)
from app.models import User
from app.schemas.auth import (
    AnonymousRequest,
    AnonymousResponse,
    AuthResponse,
    LoginRequest,
    MeResponse,
    RegisterRequest,
)

router = APIRouter(prefix="/auth", tags=["auth"])

# 统一错误码
ERR_CONFLICT = "STATE_CONFLICT"
ERR_BAD_REQUEST = "BAD_REQUEST"
ERR_UNAUTHORIZED = "UNAUTHORIZED"


def _auth_response(user: User) -> AuthResponse:
    return AuthResponse(
        user_id=int(user.id),
        username=str(user.username),
        nickname=user.nickname,
        anonymous_id=user.anonymous_id,
        access_token=create_user_token(int(user.id)),
    )


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


@router.post("/register", response_model=AuthResponse, summary="注册账号（可绑定匿名身份延续数据）")
def register(
    payload: RegisterRequest,
    request: Request = None,
    session: Session = Depends(get_db),
) -> AuthResponse:
    """注册账号（函数）。

    说明：
        - 用户名全局唯一（部分唯一索引），重复返回 409；
        - 携带 anonymous_id（请求体优先，其次 X-Anonymous-Id 头）且该匿名用户
          存在时：若已绑定过账号（username 非空）返回 409，否则原行回填
          username/password_hash/nickname（匿名期间数据按 user_id 延续）；
        - 未携带匿名身份时新建用户（anonymous_id 自动生成 anon_ 前缀）。

    参数：
        payload：{username, password, nickname?, anonymous_id?}。
        request：FastAPI 请求对象（读 X-Anonymous-Id 头）。
        session：请求级数据库会话。

    返回值：
        AuthResponse：{user_id, username, nickname, anonymous_id, access_token, token_type}。

    异常：
        HTTPException 409：用户名已存在 / 匿名身份已绑定账号；
        数据库异常向上抛出（全局异常处理器兜底 500）。
    """
    username = payload.username.strip()
    existing = session.execute(
        select(User).where(User.username == username).limit(1)
    ).scalar_one_or_none()
    if existing is not None:
        raise api_error(409, ERR_CONFLICT, "用户名已被占用")

    anon_id = resolve_anonymous_id(payload.anonymous_id, request)
    if anon_id:
        target = session.execute(
            select(User).where(User.anonymous_id == anon_id).limit(1)
        ).scalar_one_or_none()
        if target is not None and target.username:
            raise api_error(409, ERR_CONFLICT, "该匿名身份已绑定账号，请直接登录")

    user = target if (anon_id and target is not None) else None
    if user is None:
        user = User(anonymous_id=anon_id or f"anon_{uuid.uuid4().hex[:12]}")
        session.add(user)
        session.flush()

    user.username = username
    user.password_hash = hash_password(payload.password)
    user.nickname = payload.nickname or username
    session.commit()
    return _auth_response(user)


@router.post("/login", response_model=AuthResponse, summary="用户名密码登录")
def login(
    payload: LoginRequest,
    session: Session = Depends(get_db),
) -> AuthResponse:
    """用户名密码登录（函数）。

    参数：
        payload：{username, password}。
        session：请求级数据库会话。

    返回值：
        AuthResponse：{user_id, username, nickname, anonymous_id, access_token, token_type}。

    异常：
        HTTPException 400：用户名或密码错误（不区分二者，避免账号枚举）。
    """
    user = session.execute(
        select(User).where(User.username == payload.username.strip()).limit(1)
    ).scalar_one_or_none()
    if user is None or not user.password_hash or not verify_password(payload.password, user.password_hash):
        raise api_error(400, ERR_BAD_REQUEST, "用户名或密码错误")
    return _auth_response(user)


@router.get("/me", response_model=MeResponse, summary="当前登录用户信息")
def me(
    request: Request = None,
    session: Session = Depends(get_db),
) -> MeResponse:
    """当前登录用户信息（函数）。

    参数：
        request：FastAPI 请求对象（读 Authorization 头）。
        session：请求级数据库会话。

    返回值：
        MeResponse：{user_id, username, nickname, anonymous_id}。

    异常：
        HTTPException 401：未携带合法用户 token。
    """
    user_id = user_id_from_request(request)
    if user_id is None:
        raise api_error(401, ERR_UNAUTHORIZED, "未登录或凭证无效")
    user = session.get(User, user_id)
    if user is None or not user.username:
        raise api_error(401, ERR_UNAUTHORIZED, "账号不存在或已注销")
    return MeResponse(
        user_id=int(user.id),
        username=str(user.username),
        nickname=user.nickname,
        anonymous_id=user.anonymous_id,
    )
