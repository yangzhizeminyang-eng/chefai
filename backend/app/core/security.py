"""后台管理端安全模块（模块 K 鉴权基础设施）。

职责：
    - passlib pbkdf2_sha256 密码哈希/校验（与 app/seed/configs.py 哈希口径完全一致）；
    - PyJWT HS256 签发/解析管理端 access_token（payload {sub, role, exp:+12h}）；
    - FastAPI 依赖三级角色闸门：
      get_current_admin（JWT → admin_user 存在且 status='active'，否则 401）、
      require_writer（readonly → 403，菜谱/食材/营养/反馈/创新规则等写端点）、
      require_super（非 super_admin → 403，成员管理/开关/订单补发/风控规则）；
    - write_operation_log：统一操作审计（JSONB before/after 快照 + 请求 ip）。

说明：
    JWT 密钥从环境变量 ADMIN_JWT_SECRET 读取，缺省仅用于本地开发/测试——生产必须配置；
    403 属于鉴权通过后的权限拒绝，按任务口径不写操作日志（仅写操作记审计）。
"""

from __future__ import annotations

import ipaddress
import os
from datetime import UTC, datetime, timedelta

import jwt
from fastapi import Depends, HTTPException, Request
from passlib.context import CryptContext
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.models import AdminUser, OperationLog

# JWT 密钥：环境变量 ADMIN_JWT_SECRET，缺省仅供本地开发/测试使用（生产必须配置）
_ADMIN_JWT_SECRET = os.environ.get("ADMIN_JWT_SECRET", "aicook-admin-dev-secret-change-me")

# 签名算法（HS256 对称密钥，阶段一单服务部署够用）
JWT_ALGORITHM = "HS256"

# token 有效期（小时）：后台会话 12 小时过期
TOKEN_EXPIRE_HOURS = 12

# passlib 上下文：pbkdf2_sha256（纯 Python 实现，与 seed/configs.py 完全同口径，
# 保证种子账号与后台创建账号可互验）
_pwd_context = CryptContext(schemes=["pbkdf2_sha256"], deprecated="auto")

# 统一错误码
ERR_UNAUTHORIZED = "UNAUTHORIZED"
ERR_FORBIDDEN = "FORBIDDEN"


def hash_password(password: str) -> str:
    """生成管理员密码哈希（函数）。

    说明：
        passlib pbkdf2_sha256（随机盐），与 app/seed/configs.py 同口径。

    参数：
        password：明文密码。

    返回值：
        str：可存入 admin_user.password_hash 的哈希串。

    异常：
        无。
    """
    return _pwd_context.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    """校验明文密码与库中哈希是否匹配（函数）。

    参数：
        password：待校验明文密码。
        password_hash：admin_user.password_hash 存储串。

    返回值：
        bool：匹配 True；不匹配或哈希格式非法 False。

    异常：
        无（损坏哈希按不匹配处理，不向外抛出）。
    """
    try:
        return _pwd_context.verify(password, password_hash)
    except Exception:  # noqa: BLE001 —— 旧格式/损坏哈希统一按不匹配处理
        return False


def create_access_token(username: str, role: str) -> str:
    """签发管理端 JWT（函数）。

    说明：
        payload {sub: username, role, exp: now+12h}；HS256 签名。

    参数：
        username：管理员用户名（映射 payload.sub）。
        role：三级角色（super_admin / content_ops / readonly）。

    返回值：
        str：编码后的 JWT 字符串。

    异常：
        jwt.PyJWTError：编码异常向上抛出（配置错误应尽早暴露）。
    """
    payload = {
        "sub": username,
        "role": role,
        "exp": datetime.now(UTC) + timedelta(hours=TOKEN_EXPIRE_HOURS),
    }
    return jwt.encode(payload, _ADMIN_JWT_SECRET, algorithm=JWT_ALGORITHM)


def decode_access_token(token: str) -> dict | None:
    """解析并校验管理端 JWT（函数）。

    参数：
        token：JWT 字符串。

    返回值：
        dict | None：合法返回 payload 字典；过期/签名错误/格式非法返回 None。

    异常：
        不抛出（PyJWT 异常统一消化为 None，由调用方转 401）。
    """
    try:
        return jwt.decode(token, _ADMIN_JWT_SECRET, algorithms=[JWT_ALGORITHM])
    except Exception:  # noqa: BLE001 —— 过期/篡改/非法格式一律按未认证处理
        return None


def _unauthorized(message: str) -> HTTPException:
    """构造 401 统一异常（函数）。

    参数：
        message：错误文案。

    返回值：
        HTTPException：401 异常（携带 WWW-Authenticate 头）。

    异常：
        无。
    """
    return HTTPException(
        status_code=401,
        detail={"code": ERR_UNAUTHORIZED, "message": message, "detail": None},
        headers={"WWW-Authenticate": "Bearer"},
    )


def _forbidden(message: str) -> HTTPException:
    """构造 403 统一异常（函数）。

    参数：
        message：错误文案。

    返回值：
        HTTPException：403 异常。

    异常：
        无。
    """
    return HTTPException(
        status_code=403,
        detail={"code": ERR_FORBIDDEN, "message": message, "detail": None},
    )


def get_current_admin(
    request: Request, session: Session = Depends(get_db)
) -> AdminUser:
    """解析 Bearer token 并校验管理员身份（依赖函数）。

    说明：
        Authorization: Bearer <jwt> → decode → admin_user 表校验用户名存在且
        status='active'；任一环节失败统一 401（不区分失败原因，避免信息泄露）。

    参数：
        request：FastAPI 请求对象（读 Authorization 头）。
        session：请求级数据库会话。

    返回值：
        AdminUser：当前登录管理员 ORM 实例。

    异常：
        HTTPException 401：头缺失 / token 非法或过期 / 账号不存在 / 账号被禁用。
    """
    auth_header = request.headers.get("Authorization") or ""
    if not auth_header.startswith("Bearer "):
        raise _unauthorized("未登录或凭证缺失")
    payload = decode_access_token(auth_header[len("Bearer "):])
    if payload is None:
        raise _unauthorized("凭证无效或已过期")
    username = str(payload.get("sub") or "")
    admin = session.execute(
        select(AdminUser).where(AdminUser.username == username)
    ).scalar_one_or_none()
    if admin is None or admin.status != "active":
        raise _unauthorized("账号不存在或已禁用")
    return admin


def require_writer(admin: AdminUser = Depends(get_current_admin)) -> AdminUser:
    """写操作权限闸门（依赖函数）：readonly 拒绝（函数）。

    说明：
        content_ops / super_admin 放行；readonly 仅可 GET。403 不写操作日志。

    参数：
        admin：当前管理员（依赖链自动注入）。

    返回值：
        AdminUser：透传当前管理员。

    异常：
        HTTPException 403：readonly 角色访问写端点。
    """
    if admin.role == "readonly":
        raise _forbidden("只读账号无写权限")
    return admin


def require_super(admin: AdminUser = Depends(get_current_admin)) -> AdminUser:
    """超级管理权限闸门（依赖函数）：非 super_admin 拒绝（函数）。

    说明：
        仅 super_admin 放行（成员管理/开关/订单补发/风控规则）。

    参数：
        admin：当前管理员（依赖链自动注入）。

    返回值：
        AdminUser：透传当前管理员。

    异常：
        HTTPException 403：content_ops / readonly 访问超管端点。
    """
    if admin.role != "super_admin":
        raise _forbidden("仅超级管理员可执行该操作")
    return admin


def _safe_client_ip(request: Request) -> str | None:
    """提取合法请求 IP（函数）。

    说明：
        operation_log.ip 为 PostgreSQL INET 类型；TestClient/反代等场景下
        request.client.host 可能是非 IP 字符串（如 "testclient"），直接落库会
        触发 PG invalid input syntax——先用 ipaddress 校验，非法返回 None。

    参数：
        request：FastAPI 请求对象。

    返回值：
        str | None：合法 IPv4/IPv6 字符串；非法或缺失返回 None。

    异常：
        无。
    """
    host = request.client.host if request.client else None
    if not host:
        return None
    try:
        return str(ipaddress.ip_address(host))
    except ValueError:
        return None


def write_operation_log(
    session: Session,
    admin: AdminUser | None,
    module: str,
    action: str,
    target_type: str | None = None,
    target_id: int | None = None,
    before: dict | None = None,
    after: dict | None = None,
    request: Request | None = None,
) -> OperationLog:
    """写入后台操作审计日志（函数）。

    说明：
        所有管理端写端点在提交业务变更的同一会话内调用；before/after 为
        JSONB 快照（整行关键字段字典）；ip 取合法化后的 client host。
        403 拒绝发生在依赖层，不会进入端点逻辑，天然不产生日志。

    参数：
        session：请求级数据库会话（与业务变更同事务提交）。
        admin：操作者管理员（登录/种子兜底场景可 None）。
        module：业务模块标识（如 recipe / risk_rule / config）。
        action：动作（create / update / publish / toggle / compensate 等）。
        target_type：目标对象类型（如 recipe / ingredient）。
        target_id：目标对象 ID。
        before：变更前快照（可 None）。
        after：变更后快照（可 None）。
        request：FastAPI 请求对象（提取 ip，可 None）。

    返回值：
        OperationLog：已加入会话的日志 ORM 实例（由调用方统一 commit）。

    异常：
        数据库异常向上抛出（由 get_db 回滚，保证审计与业务同事务）。
    """
    log = OperationLog(
        admin_user_id=int(admin.id) if admin is not None else None,
        module=module,
        action=action,
        target_type=target_type,
        target_id=target_id,
        before_snapshot=before,
        after_snapshot=after,
        ip=_safe_client_ip(request) if request is not None else None,
    )
    session.add(log)
    return log
