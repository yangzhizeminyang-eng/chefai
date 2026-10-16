"""免责同意路由模块。

职责：
    POST /v1/consent/disclaimer：免责声明同意落库（disclaimer_consent 表）。
    幂等：同 user + agreement_version 已有记录则跳过（不重复插行），恒返回 {ok: true}。
    POST /v1/consent/sensitive：PIPL 敏感个人信息单独同意落库（consent_record 表）。
    幂等：同 user + scope + version 未撤销记录直接复用，返回同一 consent_id。
"""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, Depends, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.v1.deps import (
    ERR_VALIDATION,
    api_error,
    resolve_user,
)
from app.core.db import get_db
from app.models import ConsentRecord, DisclaimerConsent
from app.schemas.auth import ConsentRequest, ConsentResponse
from app.schemas.profile import (
    CONSENT_SENSITIVE_VERSION,
    SCENE_TO_SCOPE,
    ConsentSensitiveRequest,
    ConsentSensitiveResponse,
)

router = APIRouter(prefix="/consent", tags=["consent"])


@router.post("/disclaimer", response_model=ConsentResponse, summary="免责声明同意落库")
def record_disclaimer_consent(
    payload: ConsentRequest | None = None,
    request: Request = None,
    session: Session = Depends(get_db),
) -> ConsentResponse:
    """记录免责声明同意（函数）。

    说明：
        anonymous_id 解析顺序：请求体 → X-Anonymous-Id 头 → 新建匿名用户；
        同一用户同一版本幂等（已有记录跳过写入）；版本缺省 DISCLAIMER_V1。

    参数：
        payload：请求体（可 None，前端仅发送 disclaimer_version）。
        request：FastAPI 请求对象。
        session：请求级数据库会话。

    返回值：
        ConsentResponse：{ok: true}。

    异常：
        数据库异常向上抛出（全局异常处理器兜底 500）。
    """
    body = payload or ConsentRequest()
    version = body.effective_version()
    user = resolve_user(session, body.anonymous_id, request)

    # 幂等检查：同 user + version 已有记录则跳过
    exists = session.execute(
        select(DisclaimerConsent.id)
        .where(DisclaimerConsent.user_id == user.id)
        .where(DisclaimerConsent.agreement_version == version)
        .limit(1)
    ).scalar_one_or_none()

    if exists is None:
        session.add(
            DisclaimerConsent(
                user_id=int(user.id),
                agreement_version=version,
                agreed_at=datetime.now(UTC),
            )
        )
    session.commit()
    return ConsentResponse(ok=True)


@router.post(
    "/sensitive",
    response_model=ConsentSensitiveResponse,
    status_code=201,
    summary="PIPL 敏感个人信息单独同意落库",
)
def record_sensitive_consent(
    payload: ConsentSensitiveRequest,
    request: Request = None,
    session: Session = Depends(get_db),
) -> ConsentSensitiveResponse:
    """敏感个人信息单独同意端点（函数）。

    说明：
        scene 映射为 consent_record.scope（表级 CHECK 枚举：allergen / health_goal /
        special_population；前端场景 family_allergen → allergen，diet_goal → health_goal），
        未知场景 422。幂等：同 user + scope + version 存在未撤销记录则直接复用，
        重复提交返回同一 consent_id 不重复插行；版本固定 SENSITIVE_V1。

    参数：
        payload：{scene, anonymous_id?}。
        request：FastAPI 请求对象（读 X-Anonymous-Id 头）。
        session：请求级数据库会话。

    返回值：
        ConsentSensitiveResponse：{consent_id}（字符串化的记录 ID）。

    异常：
        HTTPException 422：scene 不在支持场景内；
        数据库异常向上抛出（全局异常处理器兜底 500）。
    """
    scene = (payload.scene or "").strip()
    scope = SCENE_TO_SCOPE.get(scene)
    if scope is None:
        raise api_error(
            422,
            ERR_VALIDATION,
            "未知的同意场景",
            f"scene={scene}（允许：{sorted(SCENE_TO_SCOPE)}）",
        )

    user = resolve_user(session, payload.anonymous_id, request)

    # 幂等：同 user + scope + version 未撤销记录直接复用（不重复插行）
    existing_id = session.execute(
        select(ConsentRecord.id)
        .where(ConsentRecord.user_id == int(user.id))
        .where(ConsentRecord.scope == scope)
        .where(ConsentRecord.version == CONSENT_SENSITIVE_VERSION)
        .where(ConsentRecord.revoked_at.is_(None))
        .order_by(ConsentRecord.id)
        .limit(1)
    ).scalar_one_or_none()

    if existing_id is None:
        record = ConsentRecord(
            user_id=int(user.id),
            scope=scope,
            version=CONSENT_SENSITIVE_VERSION,
            agreed=True,
            agreed_at=datetime.now(UTC),
        )
        session.add(record)
        session.flush()
        consent_id = int(record.id)
    else:
        consent_id = int(existing_id)
    session.commit()
    return ConsentSensitiveResponse(consent_id=str(consent_id))
