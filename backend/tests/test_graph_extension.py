"""图中枢扩展测试（Task 6：M.3 复合意图 + M.4/M.5 专用意图节点 + L.12 创新风控 + E.9 反馈接线）。

覆盖：
    1. M.3 复合意图：「做菜 + 营养」复合输入复用推荐子图，agent_trace 可见
       ≥3 个业务节点 span（recipe_retrieve/hard_filter/recipe_rank/node_nutrition），
       编排响应标注 mode='composite' 与营养汇总说明；
    2. M.4/M.5 专用意图节点：inventory_op / nutrition_query / cooking_help 三意图
       各自路由到专用节点（trace span 取证），响应含模板/降级引导语义
       （测试环境 LLM 离线 + 无数字 user_id，走确定性关键词兜底 + 降级话术）；
    3. L.12 创新风控规则：INNO-001（输入侧医疗红线）/ INNO-002（输出侧安全承诺）/
       INNO-003（输出侧伪科学表述）在 RiskEngine 中生效；
    4. 图结构红线：新节点均位于 supervisor 之后、不直连 END（无绕闸路径）；
    5. E.9 反馈接线：recipe_rank 节点按 state.user_id 加载 feedback_penalty
       （无该用户时为空惩罚，不炸不改变排序行为）。
"""

from __future__ import annotations

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.ability.ranking import load_feedback_penalty, weighted_rank
from app.core.db import SessionLocal
from app.graph.main_graph import build_main_graph
from app.graph.nodes.intent_ops import (
    HELP_DEGRADED_TEXT,
    INV_DEGRADED_TEXT,
    NUT_DEGRADED_TEXT,
    make_node_cooking_help,
    make_node_inventory_op,
    make_node_nutrition_query,
)
from app.graph.runner import run_ask
from app.graph.subgraphs.recommend import make_recipe_rank
from app.models import AgentTrace
from app.safety import get_risk_engine
from app.safety.types import SafetyProfile
from tests.conftest import unique_request_id


def _trace_nodes(request_id: str) -> set[str]:
    """查询指定请求落库的全部节点名集合（函数）。

    参数：
        request_id：请求唯一标识（agent_trace.request_id）。

    返回值：
        set[str]：该请求全部 trace span 的节点名集合。

    异常：
        数据库不可达时向上抛出（测试环境前置条件失败）。
    """
    with SessionLocal() as session:
        rows = session.execute(
            select(AgentTrace.node_name).where(AgentTrace.request_id == request_id)
        ).all()
    return {str(r[0]) for r in rows}


def _make_candidate(recipe_id: int, main_names: list[str], covered: list[str], difficulty: int = 2) -> dict:
    """构造排序候选字典（函数）。

    参数：
        recipe_id：菜谱 ID（唯一）。
        main_names：主料名列表。
        covered：用户已覆盖食材名列表。
        difficulty：难度值（1~5，默认 2）。

    返回值：
        dict：retrieve_candidates 兼容结构的候选字典。

    异常：
        无。
    """
    return {
        "recipe_id": recipe_id,
        "title": f"测试菜谱{recipe_id}",
        "difficulty": difficulty,
        "time_minutes": 15,
        "calories_kcal": 200,
        "allergen_codes": [],
        "ingredient_allergen_codes": [],
        "dietary_flags": [],
        "equipment": [],
        "covered_count": len([n for n in main_names if n in covered]),
        "covered_names": [n for n in main_names if n in covered],
        "main_ingredient_names": main_names,
        "seasoning_names": [],
        "matched_by_title": False,
    }


class TestCompositeIntent:
    """M.3 复合意图调度（≥3 业务节点并行且 trace 可见）（测试类）。"""

    def test_composite_trace_has_multi_business_nodes(self, client: TestClient) -> None:
        """复合输入经 /v1/ask 后 trace 落库节点集合覆盖 ≥3 个子图业务节点（函数）。

        参数：
            client：FastAPI TestClient fixture。

        返回值：
            None。

        异常：
            断言失败即测试失败。
        """
        rid = unique_request_id()
        resp = client.post(
            "/v1/ask",
            json={"request_id": rid, "text": "用鸡蛋和西红柿做个菜，顺便看看今天营养"},
        )
        assert resp.status_code == 200
        body = resp.json()
        # 复合意图路由到推荐子图：有结果映射 recipe_search，空结果兜底 recommend
        assert body.get("intent") in ("recipe_search", "recommend")
        nodes = _trace_nodes(rid)
        biz = {"recipe_retrieve", "hard_filter", "recipe_rank", "node_nutrition"}
        assert len(biz & nodes) >= 3, f"复合意图 trace 业务节点不足 3 个：nodes={sorted(nodes)}"

    def test_composite_mode_in_orchestration_response(self) -> None:
        """编排响应标注 mode='composite' 并附营养汇总说明（函数）。

        参数：
            无。

        返回值：
            None。

        异常：
            断言失败即测试失败。
        """
        rid = unique_request_id()
        resp = run_ask({"request_id": rid, "text": "用鸡蛋和西红柿做个菜，顺便看看今天营养"})
        assert resp.get("mode") == "composite"
        assert "nutrition_summary" in resp, "复合响应缺少营养汇总说明"
        assert not resp.get("blocked")


class TestDedicatedIntentNodes:
    """M.4/M.5 专用意图节点路由与降级话术（测试类）。

    说明：
        测试环境 LLM 离线（supervisor 走关键词兜底）且请求未注入数字 user_id，
        专用节点按设计降级为固定引导话术（span 标 degraded），模板查库路径由
        user_id 注入后自动生效。
    """

    def test_inventory_op_intent(self, client: TestClient) -> None:
        """库存意图路由 node_inventory_op，响应含库存引导语义（函数）。

        参数：
            client：FastAPI TestClient fixture。

        返回值：
            None。

        异常：
            断言失败即测试失败。
        """
        rid = unique_request_id()
        resp = client.post("/v1/ask", json={"request_id": rid, "text": "看看我冰箱里有什么"})
        assert resp.status_code == 200
        body = resp.json()
        assert body.get("intent") == "free_qa"
        answer = str(body.get("answer") or "")
        assert ("库存" in answer) or ("食材" in answer), f"库存引导语义缺失：{answer}"
        assert "node_inventory_op" in _trace_nodes(rid)

    def test_nutrition_query_intent(self, client: TestClient) -> None:
        """营养查询意图路由 node_nutrition_query（函数）。

        参数：
            client：FastAPI TestClient fixture。

        返回值：
            None。

        异常：
            断言失败即测试失败。
        """
        rid = unique_request_id()
        resp = client.post("/v1/ask", json={"request_id": rid, "text": "我今天营养怎么样"})
        assert resp.status_code == 200
        body = resp.json()
        answer = str(body.get("answer") or "")
        # 模板（今日已记录 N 餐）或空记录/降级话术均含「今日」口径
        assert ("今日" in answer) or (answer == NUT_DEGRADED_TEXT), f"营养汇总语义缺失：{answer}"
        assert "node_nutrition_query" in _trace_nodes(rid)

    def test_cooking_help_intent(self, client: TestClient) -> None:
        """烹饪求助意图路由 node_cooking_help（函数）。

        参数：
            client：FastAPI TestClient fixture。

        返回值：
            None。

        异常：
            断言失败即测试失败。
        """
        rid = unique_request_id()
        resp = client.post("/v1/ask", json={"request_id": rid, "text": "做菜步骤忘了"})
        assert resp.status_code == 200
        body = resp.json()
        answer = str(body.get("answer") or "")
        # 模板（检测到进行中的烹饪）或空会话/降级话术均含烹饪引导语义
        assert ("烹饪" in answer) or (answer == HELP_DEGRADED_TEXT), f"烹饪引导语义缺失：{answer}"
        assert "node_cooking_help" in _trace_nodes(rid)

    def test_dedicated_nodes_degrade_without_user_id(self) -> None:
        """无数字 user_id 时三节点直接降级固定话术且 span 标 degraded（函数）。

        参数：
            无。

        返回值：
            None。

        异常：
            断言失败即测试失败。
        """
        for node_factory, degraded_text in (
            (make_node_inventory_op, INV_DEGRADED_TEXT),
            (make_node_nutrition_query, NUT_DEGRADED_TEXT),
            (make_node_cooking_help, HELP_DEGRADED_TEXT),
        ):
            out = node_factory()({})
            assert out["qa_answer"] == degraded_text
            span = out["trace"][0]
            assert span["status"] == "degraded"


class TestInnovationRiskRules:
    """L.12 创新风控规则种子在 RiskEngine 中生效（测试类）。"""

    def test_inno001_blocks_medical_innovation_input(self) -> None:
        """INNO-001 输入侧拦截「创新菜当医疗手段」请求（函数）。

        说明：
            「降血糖」字面量同时被既有 MR-001 关键词覆盖（同为 critical 医疗红线，
            按 id 序 MR-001 先命中）；「降糖」变体仅由 INNO-001 覆盖，严格断言规则码。

        参数：
            无。

        返回值：
            None。

        异常：
            断言失败即测试失败。
        """
        engine = get_risk_engine()
        verdict = engine.scan("input", "创新一个能降血糖的菜")
        assert verdict.hit and verdict.block
        assert verdict.category == "medical_refusal"
        assert verdict.rule_code in ("INNO-001", "MR-001")
        variant = engine.scan("input", "创新一个能降糖的菜")
        assert variant.hit and variant.block and variant.rule_code == "INNO-001"

    def test_inno002_blocks_safety_promise_output(self) -> None:
        """INNO-002 输出侧拦截「安全放心尽管吃」类安全承诺（函数）。

        参数：
            无。

        返回值：
            None。

        异常：
            断言失败即测试失败。
        """
        engine = get_risk_engine()
        verdict = engine.scan("output", "这道创新菜安全放心尽管吃")
        assert verdict.hit and verdict.block
        assert verdict.rule_code == "INNO-002"

    def test_inno003_blocks_pseudoscience_output(self) -> None:
        """INNO-003 输出侧拦截「相克/解毒/排毒」类伪科学表述（函数）。

        参数：
            无。

        返回值：
            None。

        异常：
            断言失败即测试失败。
        """
        engine = get_risk_engine()
        verdict = engine.scan("output", "这道创新菜与豆腐相克，还能解毒")
        assert verdict.hit and verdict.block
        assert verdict.rule_code == "INNO-003"


class TestGraphExtensionStructure:
    """图结构扩展红线：新节点存在且无绕闸路径（测试类）。"""

    def test_new_nodes_exist_and_no_direct_end(self) -> None:
        """三个专用节点已注册进主图，且全图无业务节点直连 END（函数）。

        参数：
            无。

        返回值：
            None。

        异常：
            断言失败即测试失败。
        """
        graph = build_main_graph()
        nodes = set(graph.get_graph().nodes)
        new_nodes = {"node_inventory_op", "node_nutrition_query", "node_cooking_help"}
        assert new_nodes <= nodes, f"专用节点未注册进主图：{new_nodes - nodes}"
        end_edges = [e for e in graph.get_graph().edges if e.target == "__end__"]
        terminal_exits = {"finalize", "emit_safety_response", "safe_mode_handler"}
        illegal = [e.source for e in end_edges if e.source not in terminal_exits]
        assert not illegal, f"存在绕过出口闸门直达 END 的路径：{illegal}"

    def test_composite_intent_route_registered(self) -> None:
        """复合意图已注册进确定性路由字典并指向推荐子图（函数）。

        参数：
            无。

        返回值：
            None。

        异常：
            断言失败即测试失败。
        """
        from app.graph.main_graph import INTENT_ROUTES

        assert INTENT_ROUTES.get("composite_recommend_nutrition") == "subgraph_recommend"
        assert INTENT_ROUTES.get("inventory_op") == "node_inventory_op"
        assert INTENT_ROUTES.get("nutrition_query") == "node_nutrition_query"
        assert INTENT_ROUTES.get("cooking_help") == "node_cooking_help"


class TestFeedbackPenaltyWiring:
    """E.9 反馈接线冒烟：recipe_rank 节点按 user_id 加载惩罚（测试类）。"""

    def test_recipe_rank_node_runs_with_user_id(self) -> None:
        """带数字 user_id 调用 rank 节点：惩罚查询执行且不炸、结果正常（函数）。

        说明：
            user_id 取不存在的用户（惩罚为空映射），验证 state.user_id →
            load_feedback_penalty → weighted_rank(feedback_penalty=...) 接线通路。

        参数：
            无。

        返回值：
            None。

        异常：
            断言失败即测试失败。
        """
        node = make_recipe_rank()
        state = {
            "filtered_candidates": [
                _make_candidate(1, ["土豆", "青椒"], ["土豆", "青椒"]),
                _make_candidate(2, ["茄子", "蒜"], ["茄子"]),
            ],
            "safety_profile": {},
            "user_id": 987654321,
        }
        out = node(state)
        assert out["results"], "rank 节点带 user_id 执行后结果为空"
        assert out["sub_trace"][0]["node_name"] == "recipe_rank"

    def test_load_feedback_penalty_empty_for_unknown_user(self) -> None:
        """load_feedback_penalty 对不存在用户返回空映射（函数）。

        参数：
            无。

        返回值：
            None。

        异常：
            断言失败即测试失败。
        """
        with SessionLocal() as session:
            penalty = load_feedback_penalty(session, 987654321)
        assert penalty == {}

    def test_weighted_rank_accepts_penalty_smoke(self) -> None:
        """weighted_rank 带 feedback_penalty 冒烟（既有排序测试保持绿的补充断言）（函数）。

        参数：
            无。

        返回值：
            None。

        异常：
            断言失败即测试失败。
        """
        ranked = weighted_rank(
            [
                _make_candidate(1, ["土豆"], ["土豆"]),
                _make_candidate(2, ["茄子"], ["茄子"]),
            ],
            SafetyProfile(),
            None,
            feedback_penalty={1: 0.5},
        )
        assert {item["recipe_id"] for item in ranked} == {1, 2}
        penalized = next(item for item in ranked if item["recipe_id"] == 1)
        assert "你曾表示不喜欢" in penalized["rank_reasons"]
