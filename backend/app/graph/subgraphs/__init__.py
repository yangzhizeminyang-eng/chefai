"""graph.subgraphs 包：子图集合。

说明：
    导入本包即触发各子图模块的 register() 副作用（NFR-4.1 注册表装配依赖）。
"""

from app.graph.subgraphs import recommend  # noqa: F401

__all__ = ["recommend"]
