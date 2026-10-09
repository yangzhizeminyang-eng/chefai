"""LangGraph 主图结构单测。

验证主图装配满足架构红线（PRD §11.5 三条不可违背拓扑规则的可测子集）：
1. 全部关键节点存在（双侧闸门 / 中枢 / 子图 / 汇总 / 终止出口）；
2. 所有进入 END 的边都来自三个终止出口节点（finalize / emit_safety_response / safe_mode_handler），
   即不存在绕过出口闸门直达 END 的路径；
3. 入口闸门不与 END 直连（一票否决必须经由 emit_safety_response 短路出口）。
"""


def _compiled_main_graph():
    """构建并返回编译后的主图（延迟导入，避免收集期副作用）。"""
    from app.graph.main_graph import build_main_graph

    return build_main_graph()


class TestMainGraphStructure:
    """主图结构红线断言（NFR：可枚举 = 可测试 = 可验收）。"""

    def test_required_nodes_exist(self) -> None:
        """关键节点必须全部注册：闸门/中枢/业务子图/汇总/终止出口。"""
        graph = _compiled_main_graph()
        nodes = set(graph.get_graph().nodes)
        required = {
            "intake_guard",
            "supervisor",
            "subgraph_recommend",
            "node_free_qa",
            "compose",
            "output_guard",
            "finalize",
            "emit_safety_response",
            "safe_mode_handler",
        }
        missing = required - nodes
        assert not missing, f"主图缺少关键节点: {missing}"

    def test_all_end_edges_come_from_terminal_exits(self) -> None:
        """进入 END 的边必须全部来自终止出口节点，不允许业务节点直连 END。"""
        graph = _compiled_main_graph()
        terminal_exits = {"finalize", "emit_safety_response", "safe_mode_handler"}
        end_edges = [
            edge for edge in graph.get_graph().edges if edge.target == "__end__"
        ]
        assert end_edges, "图中不存在任何到 END 的边（装配异常）"
        illegal = [e.source for e in end_edges if e.source not in terminal_exits]
        assert not illegal, f"存在绕过出口闸门直达 END 的路径: {illegal}"

    def test_intake_guard_has_no_direct_end_edge(self) -> None:
        """入口闸门不得直连 END：阻断路径必须先经 emit_safety_response。"""
        graph = _compiled_main_graph()
        direct = [
            edge
            for edge in graph.get_graph().edges
            if edge.source == "intake_guard" and edge.target == "__end__"
        ]
        assert not direct, "intake_guard 直连 END，绕过了一票否决短路出口"

    def test_veto_response_is_pure(self) -> None:
        """一票否决返回体纯净性：blocked 响应不含任何业务结果字段。"""
        from app.graph.runner import run_ask

        resp = run_ask({"request_id": "ut_veto_pure_001", "text": "木耳泡一晚上明天炒行吗"})
        assert resp.get("blocked") is True
        for forbidden_key in ("results", "candidates", "nutrition"):
            assert forbidden_key not in resp, f"否决响应泄漏了业务字段 {forbidden_key}"
