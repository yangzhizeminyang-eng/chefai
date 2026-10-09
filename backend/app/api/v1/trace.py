"""调度可视化（trace）路由模块。

职责：
    - GET /v1/trace/{request_id}：trace 详情（节点列表 + 风控判定 + 一票否决 + 汇总）；
    - GET /v1/trace?limit=20：最近 trace 列表（面板场景切换，响应体为数组）。

    一票否决判定（veto）：存在 overrides_all 语义的取证 = risk_log 中该 request_id 有
    action='blocked' 行，或 agent_trace 中存在 skipped_by_veto 状态节点；
    风控判定卡数据 = risk_log 最新行 + risk_message 话术全文。
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.v1.deps import ERR_NOT_FOUND, adapt_risk, api_error
from app.core.db import get_db
from app.models import AgentTrace, RiskLog
from app.safety import get_risk_engine

router = APIRouter(prefix="/trace", tags=["trace"])


def _load_risk_row(session: Session, request_id: str) -> RiskLog | None:
    """加载该请求最新的 risk_log 行（函数）。

    参数：
        session：数据库会话。
        request_id：幂等键。

    返回值：
        RiskLog | None：最新风控日志行（无则 None）。

    异常：
        不抛出（查询异常返回 None，判定卡降级为未命中）。
    """
    try:
        return session.execute(
            select(RiskLog)
            .where(RiskLog.request_id == request_id)
            .order_by(RiskLog.id.desc())
            .limit(1)
        ).scalar_one_or_none()
    except Exception:  # noqa: BLE001
        return None


def _load_nodes(session: Session, request_id: str) -> list[AgentTrace]:
    """加载该请求全部节点 span（函数）。

    参数：
        session：数据库会话。
        request_id：幂等键。

    返回值：
        list[AgentTrace]：按落库顺序的 span 行。

    异常：
        不抛出（查询异常返回空列表）。
    """
    try:
        return list(
            session.execute(
                select(AgentTrace)
                .where(AgentTrace.request_id == request_id)
                .order_by(AgentTrace.id)
            ).scalars().all()
        )
    except Exception:  # noqa: BLE001
        return []


@router.get("/{request_id}", summary="Agent 调度 trace 详情（W-06 面板数据源）")
def get_trace_detail(
    request_id: str,
    session: Session = Depends(get_db),
) -> dict:
    """trace 详情端点（函数）。

    说明：
        - veto 为对象 {veto, reason}（前端以 veto.veto 判断高亮横幅）；
        - risk 恒为对象（hit=false 表示未命中放行，前端类型要求 hit 恒存在）；
        - totals 双口径：前端消费 prompt_tokens/completion_tokens/cost_cents，
          任务口径 total_* 字段同值附加。

    参数：
        request_id：幂等键。
        session：请求级数据库会话。

    返回值：
        dict：TraceDetailResponse 结构。

    异常：
        HTTPException 404：无任何 trace 记录。
    """
    nodes = _load_nodes(session, request_id)
    if not nodes:
        raise api_error(404, ERR_NOT_FOUND, "未找到该请求的调度记录", f"request_id={request_id}")

    risk_row = _load_risk_row(session, request_id)
    has_veto_span = any(n.status == "skipped_by_veto" for n in nodes)
    is_veto = has_veto_span or (risk_row is not None and risk_row.action == "blocked")

    # 风控判定卡：risk_log 行 + risk_message 话术全文
    risk_body = {
        "hit": risk_row is not None and bool(risk_row.rule_code),
        "category": risk_row.category if risk_row else None,
        "rule_code": risk_row.rule_code if risk_row else None,
        "rule_id": risk_row.rule_code if risk_row else None,
        "risk_level": risk_row.risk_level if risk_row else None,
        "message_id": risk_row.message_id if risk_row else None,
        "title": None,
        "body": None,
        "correct_action": None,
        "after_consumption_advice": None,
        "evidence_ref": [],
    }
    if risk_row is not None and risk_row.rule_code:
        message = get_risk_engine().get_message(risk_row.message_id)
        if message:
            risk_body.update(
                {
                    "title": message.get("title"),
                    "body": message.get("body"),
                    "correct_action": message.get("correct_action"),
                    "after_consumption_advice": message.get("after_consumption_advice"),
                }
            )
    reason = None
    if is_veto and risk_row is not None:
        reason = f"输入命中阻断规则 {risk_row.rule_code or ''}，业务节点短路未执行".strip()

    total_duration = sum(int(n.duration_ms or 0) for n in nodes)
    total_prompt = sum(int(n.prompt_tokens or 0) for n in nodes)
    total_completion = sum(int(n.completion_tokens or 0) for n in nodes)
    total_cost = sum(float(n.cost_cents or 0) for n in nodes)

    return {
        "request_id": request_id,
        "veto": {"veto": bool(is_veto), "reason": reason},
        "risk": adapt_risk(risk_body),
        "nodes": [
            {
                "node_name": n.node_name,
                "status": n.status,
                "duration_ms": int(n.duration_ms or 0),
                "model_name": n.model_name,
                "prompt_tokens": int(n.prompt_tokens or 0),
                "completion_tokens": int(n.completion_tokens or 0),
                "cost_cents": float(n.cost_cents or 0),
                "rule_hit": n.rule_hit,
            }
            for n in nodes
        ],
        "totals": {
            "prompt_tokens": total_prompt,
            "completion_tokens": total_completion,
            "cost_cents": total_cost,
            "total_duration_ms": total_duration,
            "total_prompt_tokens": total_prompt,
            "total_completion_tokens": total_completion,
            "total_cost_cents": total_cost,
        },
        "created_at": nodes[0].created_at.isoformat() if nodes[0].created_at else None,
    }


@router.get("", summary="最近 trace 列表（面板场景切换，响应体为数组）")
def list_traces(
    limit: int = Query(default=20, ge=1, le=100),
    session: Session = Depends(get_db),
) -> list[dict]:
    """最近 trace 列表端点（函数）。

    说明：
        按 request_id 分组取最近 limit 条（以最大 span id 代表组内最新）；
        响应体为数组（前端 listTraces 消费 Promise<TraceListItem[]>）；
        列表项 veto 为布尔（与详情对象口径不同，均为前端契约）。

    参数：
        limit：返回条数上限（1~100，默认 20）。
        session：请求级数据库会话。

    返回值：
        list[dict]：TraceListItem 数组（按时间倒序）。

    异常：
        查询异常返回空数组（列表为辅助功能，不阻塞面板）。
    """
    try:
        # 最近 request_id 分组：组内最大 id 即最新落库行
        grouped = session.execute(
            select(
                AgentTrace.request_id,
                func.max(AgentTrace.id).label("last_row_id"),
                func.count(AgentTrace.id).label("node_count"),
                func.coalesce(func.sum(AgentTrace.duration_ms), 0).label("total_duration"),
            )
            .group_by(AgentTrace.request_id)
            .order_by(func.max(AgentTrace.id).desc())
            .limit(limit)
        ).all()
    except Exception:  # noqa: BLE001 —— 列表失败返回空，面板仍可手动查询
        return []

    items: list[dict] = []
    for request_id, _last_row_id, node_count, total_duration in grouped:
        nodes = _load_nodes(session, str(request_id))
        if not nodes:
            continue
        risk_row = _load_risk_row(session, str(request_id))
        is_veto = any(n.status == "skipped_by_veto" for n in nodes) or (
            risk_row is not None and risk_row.action == "blocked"
        )
        items.append(
            {
                "request_id": str(request_id),
                "created_at": nodes[-1].created_at.isoformat() if nodes[-1].created_at else None,
                "veto": bool(is_veto),
                "risk": adapt_risk(
                    {
                        "hit": risk_row is not None and bool(risk_row.rule_code),
                        "category": risk_row.category if risk_row else None,
                        "rule_code": risk_row.rule_code if risk_row else None,
                        "risk_level": risk_row.risk_level if risk_row else None,
                        "message_id": risk_row.message_id if risk_row else None,
                    }
                ),
                "node_count": int(node_count or len(nodes)),
                "total_duration_ms": int(total_duration or 0),
            }
        )
    return items
