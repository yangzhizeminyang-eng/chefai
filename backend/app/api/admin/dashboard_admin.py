"""后台看板路由模块（模块 K）。

职责：
    - GET /admin/v1/dashboard/cost?days=7：agent_trace 按日聚合
      {tokens, cost_cents, requests}（cost_cents 列模型已存在，直接 SUM；
      空值按 0 计）；
    - GET /admin/v1/dashboard/risk?days=7：risk_log 按日聚合
      {total, blocked, by_rule:[{rule_id, count}]}。
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.models import AgentTrace, RiskLog

router = APIRouter(prefix="/dashboard", tags=["后台-看板"])


def _window(days: int) -> tuple[datetime, datetime]:
    """计算统计时间窗（函数）。

    参数：
        days：向前追溯天数（1~90）。

    返回值：
        tuple[datetime, datetime]：(start, end)（UTC，end 含今天全天）。

    异常：
        无。
    """
    end = datetime.now(UTC) + timedelta(minutes=1)
    return end - timedelta(days=days), end


@router.get("/cost", summary="成本看板（agent_trace 按日聚合）")
def cost_dashboard(
    days: int = Query(default=7, ge=1, le=90),
    session: Session = Depends(get_db),
) -> dict:
    """成本看板端点（函数）。

    说明：
        tokens = SUM(prompt+completion coalesce 0)；cost_cents 列模型已存在
        （Numeric(10,4)）直接 SUM，空值按 0；requests = COUNT(span 行)。

    参数：
        days：统计天数（缺省 7）。
        session：请求级数据库会话。

    返回值：
        dict：{days: [{date, tokens, cost_cents, requests}]}（date 升序）。

    异常：
        数据库异常向上抛出（全局处理器兜底）。
    """
    start, end = _window(days)
    tokens_sum = func.sum(
        func.coalesce(AgentTrace.prompt_tokens, 0)
        + func.coalesce(AgentTrace.completion_tokens, 0)
    )
    rows = session.execute(
        select(
            func.date(AgentTrace.created_at).label("day"),
            tokens_sum,
            func.coalesce(func.sum(AgentTrace.cost_cents), 0),
            func.count(AgentTrace.id),
        )
        .where(AgentTrace.created_at >= start, AgentTrace.created_at <= end)
        .group_by(func.date(AgentTrace.created_at))
        .order_by(func.date(AgentTrace.created_at))
    ).all()
    return {
        "days": [
            {
                "date": str(day),
                "tokens": int(tokens or 0),
                "cost_cents": float(cost or 0),
                "requests": int(cnt or 0),
            }
            for day, tokens, cost, cnt in rows
        ]
    }


@router.get("/risk", summary="风控看板（risk_log 按日聚合）")
def risk_dashboard(
    days: int = Query(default=7, ge=1, le=90),
    session: Session = Depends(get_db),
) -> dict:
    """风控看板端点（函数）。

    说明：
        total = 全部留痕行；blocked = action='blocked'；by_rule 按 rule_code
        分组计数（rule_id 语义为规则编码，None 归入 'unknown'）。

    参数：
        days：统计天数（缺省 7）。
        session：请求级数据库会话。

    返回值：
        dict：{days: [{date, total, blocked, by_rule: [{rule_id, count}]}]}。

    异常：
        数据库异常向上抛出。
    """
    start, end = _window(days)
    cond = RiskLog.created_at >= start, RiskLog.created_at <= end
    rows = session.execute(
        select(
            func.date(RiskLog.created_at).label("day"),
            func.count(RiskLog.id),
            func.count(RiskLog.id).filter(RiskLog.action == "blocked"),
        )
        .where(*cond)
        .group_by(func.date(RiskLog.created_at))
        .order_by(func.date(RiskLog.created_at))
    ).all()
    rule_rows = session.execute(
        select(
            func.date(RiskLog.created_at).label("day"),
            func.coalesce(RiskLog.rule_code, "unknown").label("rule_id"),
            func.count(RiskLog.id),
        )
        .where(*cond)
        .group_by(func.date(RiskLog.created_at), func.coalesce(RiskLog.rule_code, "unknown"))
    ).all()
    by_rule_map: dict[str, list[dict]] = {}
    for day, rule_id, cnt in rule_rows:
        by_rule_map.setdefault(str(day), []).append({"rule_id": rule_id, "count": int(cnt)})
    return {
        "days": [
            {
                "date": str(day),
                "total": int(total or 0),
                "blocked": int(blocked or 0),
                "by_rule": by_rule_map.get(str(day), []),
            }
            for day, total, blocked in rows
        ]
    }
