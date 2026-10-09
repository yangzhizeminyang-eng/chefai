"""编排节点公共工具模块。

职责：
    提供各节点共用的常量与工具：
    - DISCLAIMER_ID / TXT_G06：免责声明 ID 与保守模式固定话术（PRD TXT-G06 口径）；
    - BUSINESS_NODE_NAMES：业务节点清单（一票否决时标注 not_executed 的依据）；
    - make_span：构造 trace span 字典（字段与 agent_trace 表列一一对应）；
    - persist_trace：将 span 列表落库 agent_trace（失败仅告警，不阻断响应）。

说明：
    节点函数本身不持有数据库会话——按需自建短会话（SessionLocal 上下文管理器）。
"""

from __future__ import annotations

import time

from app.core.db import SessionLocal
from app.core.logging import get_logger
from app.models import AgentTrace

logger = get_logger(__name__)

# 免责声明固定 ID（compose / 终止节点统一附着，spec D9）
DISCLAIMER_ID = "DISCLAIMER_V1"

# 保守模式固定话术（PRD TXT-G06）
TXT_G06 = "安全校验暂不可用，已切换为安全模式，请谨慎操作。"

# 业务节点清单：一票否决短路时，这些节点不应有执行记录；
# emit_safety_response 会为缺失 span 的节点补「not_executed」记录（取证明确）
BUSINESS_NODE_NAMES: tuple[str, ...] = (
    "supervisor",
    "assemble_context",
    "recipe_retrieve",
    "hard_filter",
    "recipe_rank",
    "node_nutrition",
    "node_free_qa",
    "node_inventory_op",
    "node_nutrition_query",
    "node_cooking_help",
    "compose",
)


def make_span(node_name: str, status: str, duration_ms: float | None, **extra) -> dict:
    """构造 trace span 字典（函数）。

    说明：
        字段与 agent_trace 表列对齐（node_name/status/duration_ms/model_name/
        prompt_tokens/completion_tokens/cost_cents/rule_hit）。

    参数：
        node_name：节点名。
        status：七态状态（ok/degraded/failed/timeout/not_executed/skipped_by_veto）。
        duration_ms：耗时（毫秒，可为 None 表示未执行）。
        **extra：附加字段（model_name/prompt_tokens/completion_tokens/cost_cents/rule_hit）。

    返回值：
        dict：span 字典。

    异常：
        无。
    """
    span = {"node_name": node_name, "status": status}
    if duration_ms is not None:
        span["duration_ms"] = round(float(duration_ms))
    span.update(extra)
    return span


def now_ms() -> float:
    """获取当前单调时钟（毫秒）（函数）。

    返回值：
        float：perf_counter 计时起点（配合 end 相减得耗时）。

    异常：
        无。
    """
    return time.perf_counter() * 1000


def persist_trace(state: dict, extra_spans: list[dict]) -> bool:
    """将编排 trace 落库 agent_trace（函数）。

    说明：
        写入 state["trace"] 中已有的 span 与调用方补充的 extra_spans（含 not_executed
        与终止节点自身 span）；落库失败仅记录错误日志，绝不阻断响应组装。

    参数：
        state：当前编排状态（至少含 request_id）。
        extra_spans：补充 span 列表（not_executed / skipped_by_veto / 终止节点自身）。

    返回值：
        bool：落库成功返回 True。

    异常：
        不抛出（内部捕获全部异常）。
    """
    try:
        spans = list(state.get("trace") or []) + list(extra_spans or [])
        rows = []
        for s in spans:
            if not s.get("node_name"):
                continue
            rows.append(
                AgentTrace(
                    request_id=state.get("request_id") or "unknown",
                    thread_id=state.get("trace_id"),
                    user_id_hash=state.get("user_id_hash"),
                    node_name=s["node_name"],
                    status=s.get("status") or "ok",
                    duration_ms=s.get("duration_ms"),
                    model_name=s.get("model_name"),
                    prompt_tokens=s.get("prompt_tokens"),
                    completion_tokens=s.get("completion_tokens"),
                    cost_cents=s.get("cost_cents"),
                    rule_hit=s.get("rule_hit"),
                )
            )
        if not rows:
            return True
        with SessionLocal() as session:
            session.add_all(rows)
            session.commit()
        return True
    except Exception as exc:  # noqa: BLE001 —— trace 落库失败不影响响应
        logger.error("persist agent_trace failed (request_id=%s): %s", state.get("request_id"), exc)
        return False
