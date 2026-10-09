"""Agent 注册表模块（NFR-4.1 可插拔）。

职责：
    提供 AgentSpec 与 AGENT_REGISTRY 注册表：新增 Agent 只需 register() 注册
    （名称 / 节点工厂 / 形态 / 超时），主图装配时按注册表动态 add_node，不改中枢核心。

说明：
    node_factory 为「返回节点函数」的零参工厂（如 make_intake_guard），
    与架构文档 §4.7 的 registry 机制一致。
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field


@dataclass
class AgentSpec:
    """Agent 注册规格（模型类）。

    属性：
        name：节点名（主图 add_node 依据）。
        node_factory：零参节点工厂，调用后返回节点函数（state → state 更新 dict / Command）。
        forms：节点形态（rule=规则节点 / llm=LLM 节点 / compute=计算节点 / subgraph=子图）。
        timeout_ms：节点超时预算（毫秒，超时矩阵见架构文档 §4.6）。
        description：节点用途说明（面板展示用）。
    """

    name: str
    node_factory: Callable[[], Callable]
    forms: str
    timeout_ms: int
    description: str = field(default="")


# 全局注册表：{name: AgentSpec}
AGENT_REGISTRY: dict[str, AgentSpec] = {}


def register(name: str, node_factory: Callable[[], Callable], forms: str, timeout_ms: int, description: str = "") -> None:
    """注册一个 Agent 节点（函数）。

    说明：
        同名重复注册直接覆盖（便于热插拔/测试替换）；
        注册顺序无关，主图装配按注册表遍历 add_node。

    参数：
        name：节点名。
        node_factory：零参节点工厂。
        forms：节点形态（rule / llm / compute / subgraph）。
        timeout_ms：超时预算（毫秒）。
        description：用途说明。

    返回值：
        None。

    异常：
        无。
    """
    AGENT_REGISTRY[name] = AgentSpec(
        name=name, node_factory=node_factory, forms=forms, timeout_ms=timeout_ms, description=description
    )


def load_registry() -> dict[str, AgentSpec]:
    """确保全部内置节点已注册并返回注册表（函数）。

    说明：
        通过导入 nodes/subgraphs 包触发各模块的 register() 副作用；
        幂等（重复导入无副作用）。

    返回值：
        dict[str, AgentSpec]：注册表。

    异常：
        节点模块导入失败时向上抛出（装配期即暴露问题）。
    """
    from app.graph import nodes as _nodes  # noqa: F401 —— 导入触发注册
    from app.graph import subgraphs as _subgraphs  # noqa: F401 —— 导入触发注册

    return AGENT_REGISTRY
