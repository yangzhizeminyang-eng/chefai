"""graph 包：LangGraph 多智能体编排。

公共导出：
    build_main_graph / get_compiled_main_graph：主图装配与编译单例；
    run_recommend / run_ask：编排入口（API 层唯一消费面）；
    CookingState：主图/子图共享状态；
    AGENT_REGISTRY / register：Agent 注册表（NFR-4.1 可插拔）；
    INTENT_ROUTES：确定性意图路由字典。
"""

from app.graph.main_graph import INTENT_ROUTES, build_main_graph
from app.graph.registry import AGENT_REGISTRY, register
from app.graph.runner import get_compiled_main_graph, run_ask, run_recommend
from app.graph.state import CookingState

__all__ = [
    "build_main_graph",
    "get_compiled_main_graph",
    "run_recommend",
    "run_ask",
    "CookingState",
    "AGENT_REGISTRY",
    "register",
    "INTENT_ROUTES",
]
