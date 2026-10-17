"""LangGraph 主图装配模块。

职责：
    build_main_graph()：按注册表动态 add_node（NFR-4.1），装配主图拓扑——

    START → intake_guard
      ├─ UNKNOWN → safe_mode_handler（保守模式，绝不直连模型）
      ├─ hit → emit_safety_response（一票否决/澄清短路，业务节点不执行）
      └─ pass → supervisor（意图识别）
            └─ 确定性字典路由 INTENT_ROUTES：
                 recommend_by_ingredients / search_recipe /
                 composite_recommend_nutrition → subgraph_recommend
                 innovation → node_innovation_entry（模块 O 创新入口，透传创新子图）
                 inventory_op → node_inventory_op（M.4/M.5 库存专用节点）
                 cooking_help → node_cooking_help（M.4/M.5 烹饪求助专用节点）
                 nutrition_query → node_nutrition_query（M.4/M.5 饮食记录汇总节点）
                 其余意图 → tool_loop（qa 前置工具节点）→ node_free_qa（受限问答）
                  → compose → output_guard
                       ├─ UNKNOWN → safe_mode_handler
                       ├─ hit&block → emit_safety_response
                       └─ pass → finalize → END
    emit_safety_response / safe_mode_handler → END

拓扑红线：
    三个终止节点（finalize/emit_safety_response/safe_mode_handler）之外不存在任何
    直达 END 的路径；一票否决短路先于 compose；双侧闸门不可省略；
    专用意图节点均位于 supervisor 之后、compose/output_guard 之前（无绕闸路径）。

复合意图路由说明（M.3）：
    composite_recommend_nutrition 复用推荐子图（最小化改动）：子图内
    recipe_rank ∥ node_nutrition 天然并行，营养部分由并行节点覆盖，trace 中
    可见 ≥3 个业务节点 span（recipe_retrieve/hard_filter/recipe_rank/node_nutrition）；
    compose 节点识别 composite 意图在响应中标注 mode='composite' 并附营养汇总说明。

nutrition_query 路由变更说明（M.4/M.5）：
    由「推荐子图（对推荐结果估算营养）」改为专用节点 node_nutrition_query
    （查 meal_record 今日汇总模板应答）——纯「今天营养怎么样」类询问的主口径
    是饮食记录汇总而非推荐结果估算；推荐场景的营养估算仍由子图并行节点承担。

tool_loop 接入说明（阶段二）：
    其余意图（photo_recognize/free_qa/smalltalk_or_out_of_scope）统一路由到
    tool_loop（qa 前置工具节点）→ node_free_qa（无条件边）——工具结果摘要只
    作为回答素材进入 node_free_qa 提示词，最终回答仍经 compose → output_guard
    出口闸门（不绕过风控）；MCP_ENABLED='off'（缺省）时 tool_loop 仅挂内置
    4 个只读工具，LLM 失败/解析失败/无工具需求时立即收敛，行为退化等价于直连。
"""

from __future__ import annotations

from langgraph.graph import END, START, StateGraph

from app.graph.registry import load_registry
from app.graph.state import CookingState

# 意图 → 主图节点 确定性映射（LLM 只识别意图，路由由代码字典固定，可枚举可测试）
INTENT_ROUTES: dict[str, str] = {
    "recommend_by_ingredients": "subgraph_recommend",
    "search_recipe": "subgraph_recommend",
    # M.3 复合意图：复用推荐子图（recipe_rank ∥ node_nutrition 并行，trace 可见 ≥3 业务节点）
    "composite_recommend_nutrition": "subgraph_recommend",
    # M.4/M.5 专用意图节点（替换原 node_free_qa 落点；模板应答，不调 LLM）
    "nutrition_query": "node_nutrition_query",
    "cooking_help": "node_cooking_help",
    "inventory_op": "node_inventory_op",
    # 模块 O 创新意图：主图入口节点透传创新子图（precheck→generate）
    "innovation": "node_innovation_entry",
    # 阶段一无视觉/独立问答子图，其余意图统一并入受限问答（qa 节点覆盖短答场景）；
    # 阶段二：qa 意图先经 tool_loop（前置工具节点）再进 node_free_qa（无条件边）
    "photo_recognize": "tool_loop",
    "free_qa": "tool_loop",
    "smalltalk_or_out_of_scope": "tool_loop",
}


def route_after_intake_guard(state: CookingState) -> str:
    """入口闸门后的条件路由（函数）。

    说明：
        UNKNOWN → 保守模式；hit → emit_safety_response（一票否决短路；伪科学类
        block=false 同样经此出口返回科普澄清，blocked=false）；否则放行 supervisor。

    参数：
        state：编排状态（input_verdict 已写入）。

    返回值：
        str：下一节点名（safe_mode_handler / emit_safety_response / supervisor）。

    异常：
        无（verdict 缺失时按 UNKNOWN 处理）。
    """
    verdict = state.get("input_verdict") or {}
    if verdict.get("status") == "UNKNOWN":
        return "safe_mode_handler"
    if verdict.get("hit"):
        # ★ 一票否决/澄清：短路，supervisor 与全部业务节点不执行
        return "emit_safety_response"
    return "supervisor"


def route_after_supervisor(state: CookingState) -> str:
    """supervisor 后的确定性字典路由（函数）。

    说明：
        仅查表，无任何 LLM 参与；双保险守卫写入的 __veto__ 亦映射到否决出口；
        未知意图兜底 node_free_qa。

    参数：
        state：编排状态（intent 已写入）。

    返回值：
        str：下一节点名。

    异常：
        无。
    """
    intent = state.get("intent") or ""
    if intent == "__veto__":
        return "emit_safety_response"
    return INTENT_ROUTES.get(intent, "node_free_qa")


def route_after_output_guard(state: CookingState) -> str:
    """出口闸门后的条件路由（函数）。

    说明：
        UNKNOWN → 保守模式；hit 且 block → emit_safety_response；
        hit 但非 block → 视为已由敏感词二级替换修正，放行 finalize。

    参数：
        state：编排状态（output_verdict 已写入）。

    返回值：
        str：下一节点名（finalize / emit_safety_response / safe_mode_handler）。

    异常：
        无。
    """
    verdict = state.get("output_verdict") or {}
    if verdict.get("status") == "UNKNOWN":
        return "safe_mode_handler"
    if verdict.get("hit") and verdict.get("block"):
        return "emit_safety_response"
    return "finalize"


def build_main_graph():
    """装配并编译主图（函数）。

    说明：
        节点按 AGENT_REGISTRY 动态 add_node（新增 Agent 只需注册，不改本装配逻辑）；
        条件边均显式给出目标白名单，保证拓扑可审计。

    参数：
        无。

    返回值：
        CompiledStateGraph：编译后的主图（invoke / get_graph 可用）。

    异常：
        注册表节点与路由白名单不一致时由 LangGraph 装配期抛错（启动期即暴露）。
    """
    registry = load_registry()
    builder = StateGraph(CookingState)

    # 按注册表动态装配节点（NFR-4.1 可插拔的核心机制）
    for spec in registry.values():
        builder.add_node(spec.name, spec.node_factory())

    builder.add_edge(START, "intake_guard")
    builder.add_conditional_edges(
        "intake_guard",
        route_after_intake_guard,
        ["supervisor", "emit_safety_response", "safe_mode_handler"],
    )
    builder.add_conditional_edges(
        "supervisor",
        route_after_supervisor,
        sorted(set(INTENT_ROUTES.values())) + ["emit_safety_response"],
    )
    # 业务节点统一汇入 compose（推荐子图、受限问答、M.4/M.5 专用节点与创新入口路径）
    builder.add_edge("tool_loop", "node_free_qa")  # 阶段二：qa 前置工具节点 → 受限问答
    builder.add_edge("subgraph_recommend", "compose")
    builder.add_edge("node_free_qa", "compose")
    builder.add_edge("node_inventory_op", "compose")
    builder.add_edge("node_nutrition_query", "compose")
    builder.add_edge("node_cooking_help", "compose")
    builder.add_edge("node_innovation_entry", "compose")
    builder.add_edge("compose", "output_guard")
    builder.add_conditional_edges(
        "output_guard",
        route_after_output_guard,
        ["finalize", "emit_safety_response", "safe_mode_handler"],
    )
    # 三个终止节点 → END（不存在绕过闸门直达 END 的路径）
    builder.add_edge("finalize", END)
    builder.add_edge("emit_safety_response", END)
    builder.add_edge("safe_mode_handler", END)
    return builder.compile()
