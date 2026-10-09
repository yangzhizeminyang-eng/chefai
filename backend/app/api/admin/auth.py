"""后台认证与成员管理路由模块（模块 K）。

职责：
    - POST /admin/v1/auth/login：用户名密码登录（passlib pbkdf2_sha256 校验，
      错误统一 401），成功签发 HS256 JWT（12h）并更新 last_login_at；
    - GET  /admin/v1/auth/me：当前登录身份（JWT 依赖）；
    - GET/POST /admin/v1/admin-users、PUT /admin/v1/admin-users/{id}：
      成员管理（require_super，仅 super_admin；响应不含 password_hash），
      全部写操作记 operation_log（module='admin_user'）。
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.admin import ERR_CONFLICT, ERR_NOT_FOUND, api_error, page_args
from app.core.db import get_db
from app.core.logging import get_logger
from app.core.security import (
    create_access_token,
    get_current_admin,
    hash_password,
    require_super,
    verify_password,
    write_operation_log,
)
from app.models import AdminUser
from app.schemas.admin import AdminLoginRequest, AdminUserCreate, AdminUserUpdate

router = APIRouter(tags=["后台-认证与成员"])

logger = get_logger(__name__)


def _admin_brief(admin: AdminUser) -> dict:
    """管理员脱敏序列化（函数，不含 password_hash）。

    参数：
        admin：管理员 ORM 实例。

    返回值：
        dict：{id, username, role, status, last_login_at, created_at}。

    异常：
        无。
    """
    return {
        "id": int(admin.id),
        "username": admin.username,
        "role": admin.role,
        "status": admin.status,
        "last_login_at": admin.last_login_at.isoformat() if admin.last_login_at else None,
        "created_at": admin.created_at.isoformat() if admin.created_at else None,
    }


def _admin_snapshot(admin: AdminUser) -> dict:
    """管理员审计快照（函数）。

    说明：
        仅取可变关键字段（role/status），不落密码哈希（审计不存敏感凭证）。

    参数：
        admin：管理员 ORM 实例。

    返回值：
        dict：{username, role, status}。

    异常：
        无。
    """
    return {"username": admin.username, "role": admin.role, "status": admin.status}


@router.post("/auth/login", summary="后台登录（用户名密码 → JWT）")
def login(
    payload: AdminLoginRequest, session: Session = Depends(get_db)
) -> dict:
    """登录端点（函数）。

    说明：
        校验链：用户名存在 → status='active' → pbkdf2_sha256 密码匹配；
        任一失败统一 401（不泄露失败原因）。成功签发 {sub, role, exp:+12h}
        JWT 并更新 last_login_at。

    参数：
        payload：登录请求体 {username, password}。
        session：请求级数据库会话。

    返回值：
        dict：{access_token, token_type:'bearer', role, username}。

    异常：
        HTTPException 401：用户名不存在 / 密码错误 / 账号禁用。
    """
    admin = session.execute(
        select(AdminUser).where(AdminUser.username == payload.username)
    ).scalar_one_or_none()
    if admin is None or admin.status != "active" or not verify_password(
        payload.password, admin.password_hash
    ):
        raise api_error(401, "UNAUTHORIZED", "用户名或密码错误", None)
    admin.last_login_at = func.now()
    session.commit()
    token = create_access_token(admin.username, admin.role)
    return {
        "access_token": token,
        "token_type": "bearer",
        "role": admin.role,
        "username": admin.username,
    }


@router.get("/auth/me", summary="当前登录身份")
def me(admin: AdminUser = Depends(get_current_admin)) -> dict:
    """当前身份端点（函数）。

    参数：
        admin：当前管理员（JWT 依赖注入）。

    返回值：
        dict：{username, role}。

    异常：
        HTTPException 401：token 非法/账号失效（依赖层抛出）。
    """
    return {"username": admin.username, "role": admin.role}


@router.get("/admin-users", summary="管理员列表（super_admin）")
def list_admin_users(
    _admin: AdminUser = Depends(require_super),
    session: Session = Depends(get_db),
    offset_limit: tuple[int, int] = Depends(page_args),
) -> dict:
    """管理员列表端点（函数）。

    说明：
        仅 super_admin（require_super）；响应不含 password_hash。

    参数：
        _admin：当前管理员（占位，仅鉴权）。
        session：请求级数据库会话。
        offset_limit：(offset, limit) 分页参数。

    返回值：
        dict：{items: [管理员对象], total}。

    异常：
        HTTPException 403：非 super_admin。
    """
    offset, limit = offset_limit
    total = session.execute(select(func.count(AdminUser.id))).scalar_one()
    rows = session.execute(
        select(AdminUser).order_by(AdminUser.id).offset(offset).limit(limit)
    ).scalars().all()
    return {"items": [_admin_brief(a) for a in rows], "total": int(total)}


@router.post("/admin-users", status_code=201, summary="创建管理员（super_admin）")
def create_admin_user(
    payload: AdminUserCreate,
    request: Request,
    admin: AdminUser = Depends(require_super),
    session: Session = Depends(get_db),
) -> dict:
    """创建管理员端点（函数）。

    说明：
        用户名唯一冲突 → 409；密码 pbkdf2_sha256 哈希落库；写审计日志。

    参数：
        payload：创建请求体（username/password/role/status）。
        request：FastAPI 请求对象（取 ip）。
        admin：当前管理员（super_admin）。
        session：请求级数据库会话。

    返回值：
        dict：创建后的管理员对象（不含 password_hash）。

    异常：
        HTTPException 409：用户名已存在；422：参数校验失败。
    """
    exists = session.execute(
        select(AdminUser.id).where(AdminUser.username == payload.username)
    ).scalar_one_or_none()
    if exists is not None:
        raise api_error(409, ERR_CONFLICT, "用户名已存在", f"username={payload.username}")
    user = AdminUser(
        username=payload.username,
        password_hash=hash_password(payload.password),
        role=payload.role,
        status=payload.status,
    )
    session.add(user)
    session.flush()
    write_operation_log(
        session, admin, "admin_user", "create",
        target_type="admin_user", target_id=int(user.id),
        before=None, after=_admin_snapshot(user), request=request,
    )
    session.commit()
    return _admin_brief(user)


@router.put("/admin-users/{admin_id}", summary="更新管理员（super_admin）")
def update_admin_user(
    admin_id: int,
    payload: AdminUserUpdate,
    request: Request,
    admin: AdminUser = Depends(require_super),
    session: Session = Depends(get_db),
) -> dict:
    """更新管理员端点（函数）。

    说明：
        role/status/password 全可选（None 跳过）；密码明文哈希落库；
        before/after 快照写审计日志；不能修改自身角色（防自锁，缺省校验）。

    参数：
        admin_id：目标管理员 ID。
        payload：更新请求体。
        request：FastAPI 请求对象（取 ip）。
        admin：当前管理员（super_admin）。
        session：请求级数据库会话。

    返回值：
        dict：更新后的管理员对象（不含 password_hash）。

    异常：
        HTTPException 404：目标不存在；403/422 同上。
    """
    target = session.get(AdminUser, admin_id)
    if target is None:
        raise api_error(404, ERR_NOT_FOUND, "管理员不存在", f"admin_id={admin_id}")
    before = _admin_snapshot(target)
    if payload.role is not None:
        target.role = payload.role
    if payload.status is not None:
        target.status = payload.status
    if payload.password is not None:
        target.password_hash = hash_password(payload.password)
    write_operation_log(
        session, admin, "admin_user", "update",
        target_type="admin_user", target_id=admin_id,
        before=before, after=_admin_snapshot(target), request=request,
    )
    session.commit()
    return _admin_brief(target)
