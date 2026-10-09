"""营养并行节点模块。

职责：
    node_nutrition：与 recipe_rank 并行（子图内 fan-out），对硬过滤后候选的前 3 道
    并行估算营养（estimate_nutrition_parallel，独立会话 + 线程池）；
    结果按 recipe_id 写入 state["nutrition"]，由 compose 合并进 results；
    单条失败 → partial_failures 标注「营养数据暂不可用」（不按 0 计、不阻断链路）。

说明：
    并行分支无法依赖 recipe_rank 的输出（同一 superstep），故按 hard_filter 输出序
    取 Top3 估算——与最终排序 Top 重合度高，阶段一可接受（注释留档）。
"""

from __future__ import annotations

from app.ability import estimate_nutrition_parallel
from app.core.logging import get_logger
from app.graph.nodes.common import make_span, now_ms

logger = get_logger(__name__)

# 并行估算的菜谱数量上限
NUTRITION_TOP_N = 3


def make_node_nutrition():
    """营养并行节点工厂（函数）。

    返回值：
        Callable：节点函数。

    异常：
        无。
    """

    def node_nutrition(state: dict) -> dict:
        """营养并行估算节点（函数）。

        参数：
            state：编排状态（hard_filter 已产出 filtered_candidates）。

        返回值：
            dict：{"nutrition": {recipe_id: 结果}, "partial_failures": [...],
            "trace": [span]}。

        异常：
            不抛出（估算异常转 partial_failures 标注）。
        """
        start = now_ms()
        filtered = state.get("filtered_candidates") or []
        # 取过滤后候选前 N 道（与排序 Top 重合度最高），servings 默认 2
        top_ids = [int(c["recipe_id"]) for c in filtered[:NUTRITION_TOP_N] if c.get("recipe_id")]
        nutrition: dict[int, dict] = {}
        failures: list[str] = []
        if top_ids:
            nutrition = estimate_nutrition_parallel(top_ids, servings=2)
            for rid in top_ids:
                if rid not in nutrition:
                    failures.append(f"菜谱 {rid} 营养数据暂不可用")

        # 状态：全部候选均失败 → degraded；部分失败 → degraded；成功或无候选 → ok
        if top_ids and not nutrition:
            status = "degraded"
        elif failures:
            status = "degraded"
        else:
            status = "ok"
        span = make_span("node_nutrition", status, now_ms() - start)
        return {"nutrition": nutrition, "partial_failures": failures, "trace": [span]}

    return node_nutrition
