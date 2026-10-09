"""后台风控管理路由模块（模块 K，super_admin 专属）。

职责：
    - GET/POST/PUT /admin/v1/risk-rules、POST /{id}/toggle：规则 CRUD 与启停，
      每次改动写 before/after 审计日志并触发规则热更新；
    - POST /admin/v1/risk-rules/rollback {log_id}：按 before_snapshot 恢复规则；
    - GET/POST/PUT/DELETE /admin/v1/sensitive-words：输出侧敏感词自定义表 CRUD
      （remote_config 键 'output_sensitive_words'）。

热更新语义（重要注释）：
    RiskEngine 每次 scan 都会校验规则指纹（COUNT+MAX(updated_at)，等价于客户端
    30s 指纹轮询的拉模式语义——规则集任一变化即触发重载，无需推送/Redis）。
    本模块在写操作提交后主动调用 engine._load_rules(stage) 强制重载一次，
    使管理端变更「立即生效」而非等待下一次 scan 才发现指纹变化。
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.admin import ERR_CONFLICT, ERR_NOT_FOUND, ERR_VALIDATION, api_error
from app.core.db import get_db
from app.core.security import require_super, write_operation_log
from app.models import OperationLog, RemoteConfig, RiskRule
from app.safety.engine import RiskStage, get_risk_engine
from app.safety.sensitive_words import (
    _BAN_RULES,
    _CUSTOM_CONFIG_KEY,
    invalidate_custom_rules_cache,
)
from app.schemas.admin import (
    RiskRuleCreate,
    RiskRuleToggleRequest,
    RiskRuleUpdate,
    SensitiveWordAppend,
    SensitiveWordsPut,
)

router = APIRouter(tags=["后台-风控管理"])

_MODULE_RULE = "risk_rule"
_MODULE_WORDS = "sensitive_words"


def _rule_snapshot(rule: RiskRule) -> dict:
    """风控规则审计快照（函数）。

    参数：
        rule：规则 ORM 实例。

    返回值：
        dict：可 JSONB 序列化的关键字段字典。

    异常：
        无。
    """
    return {
        "rule_code": rule.rule_code,
        "category": rule.category,
        "stage_scope": rule.stage_scope,
        "trigger_condition": dict(rule.trigger_condition or {}),
        "response_message_id": rule.response_message_id,
        "block": bool(rule.block),
        "risk_level": rule.risk_level,
        "evidence_ref": rule.evidence_ref,
        "version": rule.version,
        "enabled": bool(rule.enabled),
    }


def _refresh_engine_cache(stage_scope: str) -> None:
    """触发风控引擎规则缓存热更新（函数）。

    说明：
        RiskEngine 为「scan 时指纹校验」的拉模式热更新（等价 30s 指纹轮询语义）；
        本函数在管理端写操作后主动按 stage 强制重载一次，变更立即生效。
        调用引擎内部 _load_rules 属于模块 K 与 safety 域的约定接口。

    参数：
        stage_scope：'input' / 'output' / 'both'（both 重载两侧）。

    返回值：
        None。

    异常：
        不抛出（引擎加载失败会被 scan 的 UNKNOWN 兜底覆盖，不阻断管理端响应）。
    """
    engine = get_risk_engine()
    stages: list[RiskStage] = (
        ["input", "output"] if stage_scope == "both" else [stage_scope]  # type: ignore[list-item]
    )
    for stage in stages:
        try:
            engine._load_rules(stage)
        except Exception:  # noqa: BLE001 —— 热更新失败不影响管理端操作本身
            pass


def _load_rule_or_404(session: Session, rule_id: int) -> RiskRule:
    """加载规则或抛 404（函数）。

    参数：
        session：数据库会话。
        rule_id：规则 ID。

    返回值：
        RiskRule：规则 ORM 实例。

    异常：
        HTTPException 404：规则不存在。
    """
    rule = session.get(RiskRule, rule_id)
    if rule is None:
        raise api_error(404, ERR_NOT_FOUND, "风控规则不存在", f"rule_id={rule_id}")
    return rule


@router.get("/risk-rules", summary="风控规则列表（含停用）")
def list_risk_rules(
    _admin=Depends(require_super), session: Session = Depends(get_db)
) -> dict:
    """规则列表端点（函数）。

    参数：
        _admin：当前管理员（占位，仅鉴权 super_admin）。
        session：请求级数据库会话。

    返回值：
        dict：{items: [规则快照 + id]}。

    异常：
        HTTPException 403：非 super_admin。
    """
    rows = session.execute(select(RiskRule).order_by(RiskRule.id)).scalars().all()
    return {"items": [_rule_snapshot(r) | {"id": int(r.id)} for r in rows]}


@router.post("/risk-rules", status_code=201, summary="创建风控规则")
def create_risk_rule(
    payload: RiskRuleCreate,
    request: Request,
    admin=Depends(require_super),
    session: Session = Depends(get_db),
) -> dict:
    """创建规则端点（函数）。

    说明：
        (rule_code, version) 唯一冲突 → 409；创建后热更新对应 stage 缓存。

    参数：
        payload：规则请求体。
        request：FastAPI 请求对象（取 ip）。
        admin：当前管理员（super_admin）。
        session：请求级数据库会话。

    返回值：
        dict：{id} + 规则快照。

    异常：
        HTTPException 409：rule_code+version 已存在；403：非 super_admin。
    """
    exists = session.execute(
        select(RiskRule.id).where(
            RiskRule.rule_code == payload.rule_code, RiskRule.version == payload.version
        )
    ).scalar_one_or_none()
    if exists is not None:
        raise api_error(
            409, ERR_CONFLICT, "rule_code+version 已存在",
            f"{payload.rule_code}@{payload.version}",
        )
    rule = RiskRule(
        rule_code=payload.rule_code,
        category=payload.category,
        stage_scope=payload.stage_scope,
        trigger_condition=payload.trigger_condition,
        response_message_id=payload.response_message_id,
        block=payload.block,
        risk_level=payload.risk_level,
        evidence_ref=payload.evidence_ref,
        version=payload.version,
        enabled=payload.enabled,
    )
    session.add(rule)
    session.flush()
    write_operation_log(
        session, admin, _MODULE_RULE, "create",
        target_type="risk_rule", target_id=int(rule.id),
        before=None, after=_rule_snapshot(rule), request=request,
    )
    session.commit()
    _refresh_engine_cache(rule.stage_scope)
    return _rule_snapshot(rule) | {"id": int(rule.id)}


@router.put("/risk-rules/{rule_id}", summary="更新风控规则")
def update_risk_rule(
    rule_id: int,
    payload: RiskRuleUpdate,
    request: Request,
    admin=Depends(require_super),
    session: Session = Depends(get_db),
) -> dict:
    """更新规则端点（函数）。

    说明：
        全字段可选；enabled 变更与 toggle 同语义（before/after 日志 + 热更新）。

    参数：
        rule_id：规则 ID。
        payload：更新请求体。
        request：FastAPI 请求对象。
        admin：当前管理员（super_admin）。
        session：请求级数据库会话。

    返回值：
        dict：{id} + 更新后快照。

    异常：
        HTTPException 404：规则不存在；403：非 super_admin。
    """
    rule = _load_rule_or_404(session, rule_id)
    before = _rule_snapshot(rule)
    if payload.trigger_condition is not None:
        rule.trigger_condition = payload.trigger_condition
    if payload.block is not None:
        rule.block = payload.block
    if payload.risk_level is not None:
        rule.risk_level = payload.risk_level
    if payload.response_message_id is not None:
        rule.response_message_id = payload.response_message_id
    if payload.evidence_ref is not None:
        rule.evidence_ref = payload.evidence_ref
    if payload.enabled is not None:
        rule.enabled = payload.enabled
    write_operation_log(
        session, admin, _MODULE_RULE, "update",
        target_type="risk_rule", target_id=rule_id,
        before=before, after=_rule_snapshot(rule), request=request,
    )
    session.commit()
    _refresh_engine_cache(rule.stage_scope)
    return _rule_snapshot(rule) | {"id": int(rule.id)}


@router.post("/risk-rules/{rule_id}/toggle", summary="启停风控规则（热更新）")
def toggle_risk_rule(
    rule_id: int,
    payload: RiskRuleToggleRequest,
    request: Request,
    admin=Depends(require_super),
    session: Session = Depends(get_db),
) -> dict:
    """规则启停端点（函数）。

    说明：
        before/after 快照记录 enabled 变化；提交后主动重载引擎缓存
        （正常路径下引擎 scan 时也会因指纹变化自动重载——30s 指纹轮询语义）。

    参数：
        rule_id：规则 ID。
        payload：{enabled: bool}。
        request：FastAPI 请求对象。
        admin：当前管理员（super_admin）。
        session：请求级数据库会话。

    返回值：
        dict：{id, enabled}。

    异常：
        HTTPException 404：规则不存在；403：非 super_admin。
    """
    rule = _load_rule_or_404(session, rule_id)
    before = _rule_snapshot(rule)
    rule.enabled = payload.enabled
    write_operation_log(
        session, admin, _MODULE_RULE, "toggle",
        target_type="risk_rule", target_id=rule_id,
        before=before, after=_rule_snapshot(rule), request=request,
    )
    session.commit()
    _refresh_engine_cache(rule.stage_scope)
    return {"id": rule_id, "enabled": bool(rule.enabled)}


@router.post("/risk-rules/rollback", summary="按操作日志回滚风控规则")
def rollback_risk_rule(
    payload: dict,
    request: Request,
    admin=Depends(require_super),
    session: Session = Depends(get_db),
) -> dict:
    """规则回滚端点（函数）。

    说明：
        取 operation_log（module='risk_rule'）before_snapshot 恢复规则字段；
        规则已被删除时按快照重建（新 id，rule_code/version 取快照原值）。
        简化实现：整行恢复，不做跨版本合并。

    参数：
        payload：{log_id: int}。
        request：FastAPI 请求对象。
        admin：当前管理员（super_admin）。
        session：请求级数据库会话。

    返回值：
        dict：{id, rolled_back_to}。

    异常：
        HTTPException 404：日志不存在/不指向规则行；422：log_id 缺失；
        403：非 super_admin。
    """
    log_id = payload.get("log_id") if isinstance(payload, dict) else None
    if not isinstance(log_id, int):
        raise api_error(422, ERR_VALIDATION, "log_id 必填（整数）", payload)
    log = session.get(OperationLog, log_id)
    if log is None or log.module != _MODULE_RULE or not log.before_snapshot:
        raise api_error(404, ERR_NOT_FOUND, "风控操作日志不存在", f"log_id={log_id}")
    snap = dict(log.before_snapshot)
    rule = session.execute(
        select(RiskRule).where(
            RiskRule.rule_code == snap.get("rule_code"),
            RiskRule.version == snap.get("version"),
        )
    ).scalar_one_or_none()
    if rule is None:
        # 目标规则已被删除：按快照重建（新 id）
        rule = RiskRule(
            rule_code=snap["rule_code"],
            category=snap["category"],
            stage_scope=snap["stage_scope"],
            trigger_condition=snap.get("trigger_condition") or {},
            response_message_id=snap.get("response_message_id"),
            block=bool(snap.get("block", True)),
            risk_level=snap["risk_level"],
            evidence_ref=snap.get("evidence_ref"),
            version=snap["version"],
            enabled=bool(snap.get("enabled", True)),
        )
        session.add(rule)
        session.flush()
    else:
        rule.trigger_condition = snap.get("trigger_condition") or {}
        rule.block = bool(snap.get("block", True))
        rule.risk_level = snap["risk_level"]
        rule.response_message_id = snap.get("response_message_id")
        rule.evidence_ref = snap.get("evidence_ref")
        rule.enabled = bool(snap.get("enabled", True))
        session.flush()
    write_operation_log(
        session, admin, _MODULE_RULE, "rollback",
        target_type="risk_rule", target_id=int(rule.id),
        before=None, after=_rule_snapshot(rule), request=request,
    )
    session.commit()
    _refresh_engine_cache(rule.stage_scope)
    return {"id": int(rule.id), "rolled_back_to": log_id}


# ---------------------------------------------------------------------------
# 输出侧敏感词自定义表（remote_config 'output_sensitive_words'）
# ---------------------------------------------------------------------------
def _words_row(session: Session) -> RemoteConfig | None:
    """读取敏感词配置行（函数）。

    参数：
        session：数据库会话。

    返回值：
        RemoteConfig | None：配置行（不存在为 None）。

    异常：
        数据库异常向上抛出。
    """
    return session.execute(
        select(RemoteConfig).where(RemoteConfig.config_key == _CUSTOM_CONFIG_KEY)
    ).scalar_one_or_none()


def _upsert_words(
    session: Session, words: list[dict], admin, request: Request, action: str,
    before: dict | None,
) -> RemoteConfig:
    """upsert 敏感词配置行（函数）。

    参数：
        session：数据库会话。
        words：词条数组（JSONB value）。
        admin：操作管理员。
        request：请求对象（取 ip）。
        action：审计动作（replace/append/remove）。
        before：变更前快照（含 version）。

    返回值：
        RemoteConfig：配置行 ORM（已 flush）。

    异常：
        数据库异常向上抛出。
    """
    row = _words_row(session)
    after_version = (int(row.version) if row is not None else 0) + 1
    if row is None:
        row = RemoteConfig(
            config_key=_CUSTOM_CONFIG_KEY, value=words, version=after_version,
            updated_by=int(admin.id) if admin is not None else None,
        )
        session.add(row)
    else:
        row.value = words
        row.version = after_version
        row.updated_by = int(admin.id) if admin is not None else None
    session.flush()
    write_operation_log(
        session, admin, _MODULE_WORDS, action,
        target_type="remote_config", target_id=int(row.id),
        before=before, after={"words": words, "version": after_version},
        request=request,
    )
    return row


@router.get("/sensitive-words", summary="输出敏感词表查询（含内置回退说明）")
def get_sensitive_words(
    _admin=Depends(require_super), session: Session = Depends(get_db)
) -> dict:
    """敏感词查询端点（函数）。

    说明：
        返回 remote_config 自定义词表；未配置时返回空列表并标注
        active_source='builtin'（sanitize 实际回退内置表）。

    参数：
        _admin：当前管理员（占位，仅鉴权 super_admin）。
        session：请求级数据库会话。

    返回值：
        dict：{words: [...], version, active_source: 'remote_config'|'builtin'}。

    异常：
        HTTPException 403：非 super_admin。
    """
    row = _words_row(session)
    if row is None or not isinstance(row.value, list) or len(row.value) == 0:
        return {"words": [], "version": int(row.version) if row is not None else 0,
                "active_source": "builtin", "builtin_rules": len(_BAN_RULES)}
    return {"words": list(row.value), "version": int(row.version),
            "active_source": "remote_config", "builtin_rules": len(_BAN_RULES)}


@router.put("/sensitive-words", summary="全量替换敏感词表")
def put_sensitive_words(
    payload: SensitiveWordsPut,
    request: Request,
    admin=Depends(require_super),
    session: Session = Depends(get_db),
) -> dict:
    """敏感词全量替换端点（函数）。

    说明：
        全量覆盖 'output_sensitive_words'（version+1）+ 审计日志 + 清理进程
        TTL 缓存（sanitize 立即生效）。空数组=回退内置表语义。

    参数：
        payload：{words: [词条]}。
        request：请求对象。
        admin：当前管理员（super_admin）。
        session：数据库会话。

    返回值：
        dict：{words, version, active_source}。

    异常：
        HTTPException 403：非 super_admin。
    """
    row = _words_row(session)
    before = (
        {"words": list(row.value), "version": int(row.version)}
        if row is not None and isinstance(row.value, list) else None
    )
    words = [w.model_dump() for w in payload.words]
    updated = _upsert_words(session, words, admin, request, "replace", before)
    invalidate_custom_rules_cache()
    session.commit()
    return {
        "words": words, "version": int(updated.version),
        "active_source": "remote_config" if words else "builtin",
    }


@router.post("/sensitive-words", status_code=201, summary="追加敏感词")
def append_sensitive_word(
    payload: SensitiveWordAppend,
    request: Request,
    admin=Depends(require_super),
    session: Session = Depends(get_db),
) -> dict:
    """追加敏感词端点（函数）。

    参数：
        payload：{word, replacement, category?}。
        request：请求对象。
        admin：当前管理员（super_admin）。
        session：数据库会话。

    返回值：
        dict：{words, version}（追加后全量）。

    异常：
        HTTPException 409：word 已存在；403：非 super_admin。
    """
    row = _words_row(session)
    current: list[dict] = list(row.value) if row is not None and isinstance(row.value, list) else []
    before = {"words": current, "version": int(row.version)} if row is not None else None
    if any(w.get("word") == payload.word for w in current):
        raise api_error(409, ERR_CONFLICT, "敏感词已存在", payload.word)
    current.append(payload.model_dump())
    updated = _upsert_words(session, current, admin, request, "append", before)
    invalidate_custom_rules_cache()
    session.commit()
    return {"words": current, "version": int(updated.version)}


@router.delete("/sensitive-words", summary="删除敏感词（?word= 单删；缺省清空回退内置）")
def delete_sensitive_word(
    word: str | None = None,
    request: Request = None,  # type: ignore[assignment] —— FastAPI 自动注入 Request
    admin=Depends(require_super),
    session: Session = Depends(get_db),
) -> dict:
    """删除敏感词端点（函数）。

    说明：
        word 参数缺省时清空整个自定义表（等价回退内置表）。

    参数：
        word：目标敏感词（可 None=清空）。
        request：请求对象。
        admin：当前管理员（super_admin）。
        session：数据库会话。

    返回值：
        dict：{words: 剩余词表, version, active_source}。

    异常：
        HTTPException 404：word 不存在；403：非 super_admin。
    """
    row = _words_row(session)
    current: list[dict] = list(row.value) if row is not None and isinstance(row.value, list) else []
    before = {"words": current, "version": int(row.version)} if row is not None else None
    if word is None:
        remaining: list[dict] = []
        action = "clear"
    else:
        if not any(w.get("word") == word for w in current):
            raise api_error(404, ERR_NOT_FOUND, "敏感词不存在", word)
        remaining = [w for w in current if w.get("word") != word]
        action = "remove"
    updated = _upsert_words(session, remaining, admin, request, action, before)
    invalidate_custom_rules_cache()
    session.commit()
    return {
        "words": remaining, "version": int(updated.version),
        "active_source": "remote_config" if remaining else "builtin",
    }
