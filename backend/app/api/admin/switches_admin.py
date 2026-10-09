"""后台远程开关管理路由模块（模块 K，super_admin 专属）。

职责：
    - GET /admin/v1/config/switches：五模块开关（口径与 GET /v1/config/switches
      一致，另附 version/updated_at）；
    - PUT /admin/v1/config/switches：全量更新 switch.*（version+1 + 审计日志）；
    - POST /admin/v1/config/switches/rollback {log_id}：按 before_snapshot 恢复。
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.admin import ERR_NOT_FOUND, ERR_VALIDATION, api_error
from app.core.db import get_db
from app.core.security import require_super, write_operation_log
from app.models import OperationLog, RemoteConfig
from app.schemas.admin import SwitchesPutRequest

router = APIRouter(prefix="/config", tags=["后台-远程开关"])

_MODULE = "config"

# switch.* 键 → 响应字段映射（与 app/api/v1/config.py 完全一致口径）
_SWITCH_KEYS = {
    "switch.recommend": "recommend",
    "switch.vision": "vision",
    "switch.qa": "qa",
    "switch.payment": "payment",
    "switch.innovation": "innovation",
}


def _read_switches(session: Session) -> tuple[dict[str, bool], int | None, str | None]:
    """读取五开关状态与版本（函数）。

    参数：
        session：数据库会话。

    返回值：
        tuple[dict[str, bool], int | None, str | None]：
        (开关字典, 最新行 version（无行 None）, 最近 updated_at ISO 串)。

    异常：
        数据库异常向上抛出。
    """
    rows = session.execute(
        select(RemoteConfig).where(RemoteConfig.config_key.in_(_SWITCH_KEYS.keys()))
    ).scalars().all()
    switches = {field: True for field in _SWITCH_KEYS.values()}
    max_version: int | None = None
    latest_updated: str | None = None
    for row in rows:
        field = _SWITCH_KEYS.get(row.config_key)
        if field is None:
            continue
        switches[field] = bool(row.value) if isinstance(row.value, bool) else True
        if max_version is None or int(row.version) > max_version:
            max_version = int(row.version)
        if row.updated_at is not None:
            iso = row.updated_at.isoformat()
            if latest_updated is None or iso > latest_updated:
                latest_updated = iso
    return switches, max_version, latest_updated


@router.get("/switches", summary="五模块开关查询（含版本）")
def get_switches(
    _admin=Depends(require_super), session: Session = Depends(get_db)
) -> dict:
    """开关查询端点（函数）。

    参数：
        _admin：当前管理员（占位，仅鉴权 super_admin）。
        session：请求级数据库会话。

    返回值：
        dict：{switches, version, updated_at}。

    异常：
        HTTPException 403：非 super_admin。
    """
    switches, version, updated_at = _read_switches(session)
    return {"switches": switches, "version": version, "updated_at": updated_at}


@router.put("/switches", summary="全量更新五模块开关（version+1）")
def put_switches(
    payload: SwitchesPutRequest,
    request: Request,
    admin=Depends(require_super),
    session: Session = Depends(get_db),
) -> dict:
    """开关更新端点（函数）。

    说明：
        仅更新传入键（version 各自 +1，updated_by=当前管理员）；
        before 快照 = 更新前全量开关；after = 更新后全量开关（附版本）。

    参数：
        payload：{switches: {recommend/vision/qa/payment/innovation: bool}}。
        request：FastAPI 请求对象（取 ip）。
        admin：当前管理员（super_admin）。
        session：请求级数据库会话。

    返回值：
        dict：更新后的 {switches, version, updated_at}。

    异常：
        HTTPException 403：非 super_admin；422：未知键（Pydantic）。
    """
    before_switches, _, _ = _read_switches(session)
    for key, field in _SWITCH_KEYS.items():
        if field in payload.switches:
            row = session.execute(
                select(RemoteConfig).where(RemoteConfig.config_key == key)
            ).scalar_one_or_none()
            if row is None:
                row = RemoteConfig(config_key=key, value=bool(payload.switches[field]), version=1)
                session.add(row)
            else:
                row.value = bool(payload.switches[field])
                row.version = int(row.version) + 1
            row.updated_by = int(admin.id)
    session.flush()
    write_operation_log(
        session, admin, _MODULE, "update_switches",
        target_type="remote_config", target_id=None,
        before={"switches": before_switches},
        after={"switches": payload.switches}, request=request,
    )
    session.commit()
    switches, version, updated_at = _read_switches(session)
    return {"switches": switches, "version": version, "updated_at": updated_at}


@router.post("/switches/rollback", summary="按操作日志回滚开关")
def rollback_switches(
    payload: dict,
    request: Request,
    admin=Depends(require_super),
    session: Session = Depends(get_db),
) -> dict:
    """开关回滚端点（函数）。

    说明：
        取 operation_log（module='config'）before_snapshot.switches 整体恢复；
        写 action='rollback_switches' 新日志。

    参数：
        payload：{log_id: int}。
        request：FastAPI 请求对象。
        admin：当前管理员（super_admin）。
        session：请求级数据库会话。

    返回值：
        dict：{switches, version, updated_at, rolled_back_to}。

    异常：
        HTTPException 404：日志不存在/无开关快照；422：log_id 缺失；403：非超管。
    """
    log_id = payload.get("log_id") if isinstance(payload, dict) else None
    if not isinstance(log_id, int):
        raise api_error(422, ERR_VALIDATION, "log_id 必填（整数）", payload)
    log = session.get(OperationLog, log_id)
    snap = dict(log.before_snapshot or {}) if log is not None else {}
    if log is None or log.module != _MODULE or "switches" not in snap:
        raise api_error(404, ERR_NOT_FOUND, "开关操作日志不存在", f"log_id={log_id}")
    target: dict = snap["switches"]
    for key, field in _SWITCH_KEYS.items():
        if field in target:
            row = session.execute(
                select(RemoteConfig).where(RemoteConfig.config_key == key)
            ).scalar_one_or_none()
            if row is None:
                row = RemoteConfig(config_key=key, value=bool(target[field]), version=1)
                session.add(row)
            else:
                row.value = bool(target[field])
                row.version = int(row.version) + 1
            row.updated_by = int(admin.id)
    session.flush()
    write_operation_log(
        session, admin, _MODULE, "rollback_switches",
        target_type="remote_config", target_id=None,
        before={"switches": _read_switches(session)[0]},
        after={"switches": target}, request=request,
    )
    session.commit()
    switches, version, updated_at = _read_switches(session)
    return {
        "switches": switches, "version": version, "updated_at": updated_at,
        "rolled_back_to": log_id,
    }
