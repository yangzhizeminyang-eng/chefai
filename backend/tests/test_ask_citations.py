"""OBS-04 ask 响应 citations 结构化来源测试。

覆盖（/v1/ask 响应新增可选字段 citations，既有字段不动）：
    - 检索/推荐型回答（intent=recipe_search）：citations 为
      [{type:"recipe", id, title}, ...]，与 recipe_ids 一一对应、title 为真实菜名；
    - 降级回答（LLM 不可达 → 固定兜底话术）：citations 标注
      [{type:"degraded", reason:"llm_unavailable"}]；
    - 风控拦截回答（intent=blocked）：citations 为空数组（无内容来源）；
    - 兼容性：recipe_ids 等既有字段不因新增 citations 而变化。

运行约定：
    在 backend/ 目录下执行 `python -m pytest tests/test_ask_citations.py -q`；
    conftest 已将 LLM 指向不可达地址（free_qa 必走降级兜底路径，确定性可测）。
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from tests.conftest import unique_request_id

# LLM 不可用时的固定兜底话术（与 app.graph.nodes.qa.QA_FALLBACK_ANSWER 一致）
QA_FALLBACK_ANSWER = "暂时无法生成，请稍后重试。"


def test_ask_recipe_search_citations_match_recipe_ids(client: TestClient) -> None:
    """检索型回答带 citations 且与 recipe_ids 一致（函数）。

    说明：
        「可乐鸡翅怎么做」走 recipe_search 分支；citations 应为 recipe 型结构化
        来源列表，id 集合与 recipe_ids 完全一致、title 非空且为真实菜名。

    参数：
        client：TestClient fixture。

    返回值：
        None。

    异常：
        断言失败即测试失败（需先执行种子数据初始化）。
    """
    resp = client.post(
        "/v1/ask",
        json={"text": "可乐鸡翅怎么做", "request_id": unique_request_id()},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data.get("intent") == "recipe_search"
    recipe_ids = data.get("recipe_ids") or []
    assert recipe_ids, "检索型回答应含 recipe_ids（既有字段不回退）"

    citations = data.get("citations")
    assert isinstance(citations, list) and citations, "检索型回答应含非空 citations"
    for cit in citations:
        assert cit.get("type") == "recipe"
        assert isinstance(cit.get("id"), int)
        assert str(cit.get("title") or "").strip(), "citation 应携带真实菜名标题"
    # id 集合与 recipe_ids 完全一致（同一批检索结果的结构化来源）
    assert {c["id"] for c in citations} == set(recipe_ids)


def test_ask_free_qa_degraded_citations(client: TestClient) -> None:
    """降级回答 citations 标注 degraded（函数）。

    说明：
        测试环境 LLM 不可达 → node_free_qa 固定兜底话术 → 响应 citations 应
        标注 degraded 且 reason=llm_unavailable（诚实标注无来源可引）。

    参数：
        client：TestClient fixture。

    返回值：
        None。

    异常：
        断言失败即测试失败。
    """
    resp = client.post(
        "/v1/ask",
        json={"text": "请问怎么煎牛排", "request_id": unique_request_id()},
    )
    assert resp.status_code == 200
    data = resp.json()
    # LLM 不可达 → 关键词兜底判 free_qa → qa 节点降级兜底话术
    assert data.get("intent") == "free_qa"
    assert data.get("answer") == QA_FALLBACK_ANSWER
    assert data.get("citations") == [{"type": "degraded", "reason": "llm_unavailable"}]


def test_ask_blocked_citations_empty(client: TestClient) -> None:
    """风控拦截回答 citations 为空数组（函数）。

    说明：
        高危输入被一票否决（intent=blocked）时未生成任何业务内容，
        citations 为空数组（不是 None/缺失，便于前端统一消费）。

    参数：
        client：TestClient fixture。

    返回值：
        None。

    异常：
        断言失败即测试失败。
    """
    resp = client.post(
        "/v1/ask",
        json={"text": "发芽土豆削掉芽能吃吗", "request_id": unique_request_id()},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data.get("intent") == "blocked"
    assert data.get("blocked") is not None
    assert data.get("citations") == []


def test_ask_citations_do_not_break_existing_fields(client: TestClient) -> None:
    """新增 citations 不破坏既有字段契约（函数）。

    说明：
        检索型响应的既有字段（request_id/intent/recipe_ids/trace_id/
        disclaimer_id）应全部保留，citations 仅是附加可选字段。

    参数：
        client：TestClient fixture。

    返回值：
        None。

    异常：
        断言失败即测试失败。
    """
    resp = client.post(
        "/v1/ask",
        json={"text": "西红柿炒鸡蛋怎么做", "request_id": unique_request_id()},
    )
    assert resp.status_code == 200
    data = resp.json()
    for key in ("request_id", "intent", "recipe_ids", "trace_id", "disclaimer_id"):
        assert key in data, f"既有字段 {key} 不应因新增 citations 缺失"
