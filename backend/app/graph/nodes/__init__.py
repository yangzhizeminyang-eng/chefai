"""graph.nodes 包：主图节点集合。

说明：
    导入本包即触发各模块的 register() 副作用（NFR-4.1 注册表装配依赖）；
    intent_ops 为 M.4/M.5 专用意图节点（inventory_op/nutrition_query/cooking_help）。
"""

from app.graph.nodes import (  # noqa: F401
    compose,
    finalize,
    guards,
    innovation_entry,
    intent_ops,
    nutrition_node,
    qa,
    supervisor,
)

__all__ = ["guards", "supervisor", "qa", "nutrition_node", "compose", "finalize", "intent_ops", "innovation_entry"]
