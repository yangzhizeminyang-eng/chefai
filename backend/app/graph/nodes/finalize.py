"""finalize 终止节点模块。

职责：
    正常路径唯一出口：
    - 把编排全程的 trace spans 逐行落库 agent_trace（request_id/node_name/status/
      duration_ms/model_name/prompt_tokens/completion_tokens/cost_cents/rule_hit；
      user_id_hash 为 sha256 前 12 位脱敏）；
    - 返回最终 response（补齐 trace_id 与 disclaimer_id）。

拓扑红线：
    到达 finalize 的前提是已通过 intake_guard 与 output_guard 两道闸门（条件边保证）。
"""

from __future__ import annotations

from app.core.logging import get_logger
from app.graph.nodes.common import DISCLAIMER_ID, TXT_G06, make_span, now_ms, persist_trace
from app.graph.registry import register

logger = get_logger(__name__)


def make_finalize():
    """finalize 节点工厂（函数）。

    返回值：
        Callable：节点函数。

    异常：
        无。
    """

    def finalize(state: dict) -> dict:
        """终止节点：trace 落库并返回最终响应（函数）。

        参数：
            state：编排状态（response 已由 compose 产出）。

        返回值：
            dict：{"response": 最终响应 dict, "trace": [自身 span]}。

        异常：
            不抛出（落库失败仅告警；响应兜底为保守模式文案）。
        """
        start = now_ms()
        own = make_span("finalize", "ok", now_ms() - start)

        # 全量 trace 落库（含本节点 span；失败仅告警不影响响应）
        persist_trace(state, [own])

        response = dict(state.get("response") or {})
        if not response:
            # compose 缺失的兜底（正常路由下不应发生）
            response = {
                "request_id": state.get("request_id"),
                "safe_mode": True,
                "message": TXT_G06,
            }
        response.setdefault("disclaimer_id", DISCLAIMER_ID)
        response["trace_id"] = state.get("trace_id")
        return {"response": response, "trace": [own]}

    return finalize


# ---- 注册 ----
register("finalize", make_finalize, forms="rule", timeout_ms=1000, description="trace 落库 + 最终响应组装")
