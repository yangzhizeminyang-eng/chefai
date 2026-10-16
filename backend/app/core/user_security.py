"""用户端安全模块（web 注册/登录 JWT）。

职责：
    - 复用 core/security.py 的 pbkdf2_sha256 哈希/校验（与 admin_user 同口径）；
    - PyJWT HS256 签发/解析用户端 access_token（payload {sub: user_id, typ: 'user', exp:+7d}）；
    - user_jwt_from_request：从 Authorization 头解析合法用户 token 中的 user_id。

说明：
    密钥独立于后台 ADMIN_JWT_SECRET（USER_JWT_SECRET，缺省仅供本地开发/测试），
    payload 携带 typ='user' 与后台 token 互不通用。
"""

from __future__ import annotations

import os
from datetime import UTC, datetime, timedelta

import jwt
from fastapi import Request

from app.core.security import JWT_ALGORITHM, hash_password, verify_password  # noqa: F401  (re-export)

# JWT 密钥：环境变量 USER_JWT_SECRET，缺省仅供本地开发/测试使用（生产必须配置）
_USER_JWT_SECRET = os.environ.get("USER_JWT_SECRET", "aicook-user-dev-secret-change-me")

# token 有效期（天）：用户端会话 7 天过期
USER_TOKEN_EXPIRE_DAYS = 7

__all__ = ["hash_password", "verify_password", "create_user_token", "decode_user_token", "user_id_from_request"]


def create_user_token(user_id: int) -> str:
    """签发用户端 JWT（函数）。

    参数：
        user_id：用户表主键。

    返回值：
        str：编码后的 JWT 字符串。

    异常：
        jwt.PyJWTError：编码异常向上抛出。
    """
    payload = {
        "sub": str(user_id),
        "typ": "user",
        "exp": datetime.now(UTC) + timedelta(days=USER_TOKEN_EXPIRE_DAYS),
    }
    return jwt.encode(payload, _USER_JWT_SECRET, algorithm=JWT_ALGORITHM)


def decode_user_token(token: str) -> int | None:
    """解析用户端 JWT 并返回 user_id（函数）。

    参数：
        token：JWT 字符串。

    返回值：
        int | None：合法用户 token 返回 user_id；过期/签名错误/typ 不符返回 None。

    异常：
        不抛出（PyJWT 异常统一消化为 None）。
    """
    try:
        payload = jwt.decode(token, _USER_JWT_SECRET, algorithms=[JWT_ALGORITHM])
    except Exception:  # noqa: BLE001 —— 过期/篡改/非法格式一律按未认证处理
        return None
    if payload.get("typ") != "user":
        return None
    try:
        return int(payload.get("sub"))
    except (TypeError, ValueError):
        return None


def user_id_from_request(request: Request) -> int | None:
    """从请求 Authorization 头解析用户身份（函数）。

    说明：
        仅识别 Bearer 用户 token；无头/非法/后台 token 一律返回 None，
        由调用方决定回退匿名解析。

    参数：
        request：FastAPI 请求对象。

    返回值：
        int | None：user_id 或 None。

    异常：
        无。
    """
    auth_header = request.headers.get("Authorization") or ""
    if not auth_header.startswith("Bearer "):
        return None
    return decode_user_token(auth_header[len("Bearer "):])
