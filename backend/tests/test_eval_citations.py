"""OBS-04 Eval citation 覆盖维度与 token/cost 归因测试。

覆盖：
    - EvalCaseResult 新增 citations / citation_hit / citation_grounding 字段
      （默认空列表 / None / None）；
    - eval_retrieval 为检索用例构造与 compose 同口径的结构化来源并判定
      citation_hit（citations 中含期望关键词来源）；
    - summarize 的 citations 段：coverage = citation_hit 命中比例；无有效
      citation 数据时 coverage=None 且 notes 明确归因（绝不编造）；
    - citation_grounding 非循环口径：summarize 按 published_recipe_ids 批量
      校验引用 id 可追溯性（id 不在已发布集合 → False；全部在 → True；
      无 citations → None），citations 中 id 不在集合 → grounding_ratio 下降；
      未提供 id 集合时 grounding unavailable 并 notes 归因；intent 等非检索
      路径 citations 恒空、不参与 grounding；
    - summarize 的 token_cost 段：评测路径（关键词/规则/SQL）无 LLM 调用，
      total_tokens / total_cost_cents 恒 None（unavailable）且归因写入 reason，
      estimated=False 表示非估算口径；
    - 回归门禁不含 citation 指标（信息维度不进门禁）。

运行约定：
    在 backend/ 目录下执行 `python -m pytest tests/test_eval_citations.py -q`。
"""

from __future__ import annotations

from pathlib import Path

import pytest

from eval.run_eval import (
    GATE_DEFAULTS,
    EvalCase,
    EvalCaseResult,
    EvalReport,
    eval_intent,
    eval_retrieval,
    evaluate_gate,
    summarize,
)

# backend 根目录（tests/ 的上一级）
BASE_DIR = Path(__file__).resolve().parents[1]


def _make_retrieval_result(case_id: str, citation_hit: bool | None) -> EvalCaseResult:
    """构造检索类用例结果（辅助函数）。

    参数：
        case_id：用例 ID。
        citation_hit：citation 命中布尔值（None 表示无有效 citation 数据）。

    返回值：
        EvalCaseResult：可直接进入 summarize 的检索类结果。

    异常：
        无。
    """
    return EvalCaseResult(
        case_id=case_id,
        dataset="retrieval",
        expected_keywords=["红烧肉"],
        passed=citation_hit,
        titles=["红烧肉"] if citation_hit else [" unrelated"],
        citations=[{"type": "recipe", "id": 3, "title": "红烧肉"}] if citation_hit is not None else [],
        citation_hit=citation_hit,
    )


class TestCitationFields:
    """EvalCaseResult citations 字段与 eval_retrieval 产出测试（测试类）。"""

    def test_result_defaults(self) -> None:
        """新字段默认值：citations 为空列表、citation_hit 为 None（测试方法）。

        异常：
            断言失败时 pytest 抛出 AssertionError。
        """
        r = EvalCaseResult(case_id="rt-x", dataset="retrieval")
        assert r.citations == []
        assert r.citation_hit is None

    def test_eval_retrieval_builds_citations(self) -> None:
        """检索用例构造 recipe 型 citations 且 citation_hit 判定正确（测试方法）。

        说明：
            用已知命中的查询（红烧肉怎么做）验证 citations 结构与命中布尔值。

        异常：
            断言失败时 pytest 抛出 AssertionError（数据库不可达时会先在此暴露）。
        """
        case = EvalCase(id="rt-cit", dataset="retrieval", text="红烧肉怎么做", expected_keywords=["红烧肉"])
        results, errors = eval_retrieval([case])
        assert len(results) == 1
        r = results[0]
        assert r.error is None, f"检索用例失败: {r.error}（errors={errors}）"
        assert r.citations, "命中用例应产出非空 citations"
        for cit in r.citations:
            assert cit.get("type") == "recipe"
            assert isinstance(cit.get("id"), int)
            assert str(cit.get("title") or "").strip()
        assert r.citation_hit is True, f"citations={r.citations} 未覆盖期望关键词"


class TestSummarizeCitations:
    """summarize 的 citations 段汇总测试（测试类）。"""

    def test_coverage_is_hit_ratio(self) -> None:
        """coverage = citation_hit 命中比例（2/3 精确断言）（测试方法）。

        异常：
            断言失败时 pytest 抛出 AssertionError。
        """
        report = EvalReport(generated_at="t")
        report.results = [
            _make_retrieval_result("rt-a", True),
            _make_retrieval_result("rt-b", True),
            _make_retrieval_result("rt-c", False),
        ]
        summarize(report)
        cit = report.metrics.get("citations") or {}
        assert cit.get("coverage") == round(2 / 3, 4)
        assert cit.get("cases") == 3
        assert cit.get("cases_with_citations") == 3

    def test_unavailable_when_no_citation_data(self) -> None:
        """无有效 citation 数据时 coverage=None 且 notes 明确归因（测试方法）。

        异常：
            断言失败时 pytest 抛出 AssertionError。
        """
        report = EvalReport(generated_at="t")
        report.results = []  # 无任何检索结果
        summarize(report)
        assert report.metrics["citations"]["coverage"] is None
        assert any("citations" in n and "unavailable" in n for n in report.notes), (
            f"notes 应含 citations unavailable 归因: {report.notes}"
        )

    def test_intent_results_do_not_enter_coverage(self) -> None:
        """非检索数据集（intent/safety）不参与 citation 覆盖分母（测试方法）。

        说明：
            citation 维度仅对检索类用例有意义，不适用维度不编造数值。

        异常：
            断言失败时 pytest 抛出 AssertionError。
        """
        report = EvalReport(generated_at="t")
        report.results = [
            EvalCaseResult(case_id="it-a", dataset="intent", predicted_intent="free_qa", passed=True),
        ]
        summarize(report)
        assert report.metrics["citations"]["coverage"] is None


class TestCitationGrounding:
    """citation_grounding 非循环口径测试（grounding = 引用 id 可追溯至已发布菜谱库）（测试类）。

    说明：
        citation_hit 与 Hit@k 同源（判据同为候选标题含期望关键词，仅窗口口径
        不同），coverage 是 hit 的冗余；grounding 为独立口径——校验 citations
        的 id 是否指向已发布菜谱库，由 summarize 按 published_recipe_ids 批量判定。
    """

    @staticmethod
    def _patch_candidates(monkeypatch: pytest.MonkeyPatch, marker: str = "未发布来源") -> None:
        """替换 eval.run_eval.retrieve_candidates 为受控检索桩（辅助函数）。

        说明：
            查询文本含 marker 时返回虚假 id（999999，不存在于已发布库）候选；
            否则返回真实 id=1 候选；查询含「空候选」标记时返回空列表。

        参数：
            monkeypatch：pytest monkeypatch fixture。
            marker：触发虚假 id 候选的查询标记词。

        返回值：
            None。

        异常：
            无。
        """

        def _fake_retrieve(session: object, ingredient_ids: list[int], query_text: str | None) -> list[dict]:
            """检索桩主体（内部函数）。

            参数：
                session：数据库会话（桩不触库，忽略）。
                ingredient_ids：食材 id 列表（桩忽略）。
                query_text：查询文本（按标记词分流返回受控候选）。

            返回值：
                list[dict]：受控候选列表（recipe_id + title 结构与真实候选一致）。

            异常：
                无。
            """
            text = query_text or ""
            if "空候选" in text:
                return []
            if marker in text:
                return [{"recipe_id": 999999, "title": "红烧肉（未发布来源）"}]
            return [{"recipe_id": 1, "title": "红烧肉"}]

        monkeypatch.setattr("eval.run_eval.retrieve_candidates", _fake_retrieve)

    def test_grounding_false_for_unpublished_id(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """citation 指向已发布库不存在的 id → grounding=False 且 grounding_ratio 下降（测试方法）。

        说明：
            monkeypatch 注入虚假 id=999999 候选与真实 id=1 候选各一条，验证
            summarize 批量校验能识别不可追溯引用（citation_hit 不受影响——
            虚假来源标题仍含关键词，正是循环定义下 coverage 无法暴露的问题）。

        异常：
            断言失败时 pytest 抛出 AssertionError。
        """
        self._patch_candidates(monkeypatch)
        cases = [
            EvalCase(id="rt-fake", dataset="retrieval", text="红烧肉怎么做（未发布来源）", expected_keywords=["红烧肉"]),
            EvalCase(id="rt-real", dataset="retrieval", text="红烧肉怎么做", expected_keywords=["红烧肉"]),
        ]
        results, errors = eval_retrieval(cases)
        assert not errors, f"检索评测不应整体失败: {errors}"
        fake = next(r for r in results if r.case_id == "rt-fake")
        real = next(r for r in results if r.case_id == "rt-real")
        assert [c["id"] for c in fake.citations] == [999999], f"桩候选未注入虚假 id: {fake.citations}"
        assert fake.citation_hit is True, "虚假来源标题含关键词时 citation_hit 仍为 True（同源口径的冗余性）"

        report = EvalReport(generated_at="t")
        report.results = results
        summarize(report, published_recipe_ids={1, 2, 3})
        assert fake.citation_grounding is False, "虚假 id 不在已发布集合，grounding 应为 False"
        assert real.citation_grounding is True
        cit = report.metrics["citations"]
        assert cit["grounding_ratio"] == 0.5, f"1/2 用例引用可追溯，grounding_ratio 应为 0.5: {cit}"
        assert cit["grounding_cases"] == 2

    def test_grounding_true_when_all_ids_published(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """citations 全部 id 在已发布集合内 → grounding=True、ratio=1.0 且 notes 含同源口径标注（测试方法）。

        异常：
            断言失败时 pytest 抛出 AssertionError。
        """
        self._patch_candidates(monkeypatch)
        case = EvalCase(id="rt-ok", dataset="retrieval", text="红烧肉怎么做", expected_keywords=["红烧肉"])
        results, errors = eval_retrieval([case])
        assert not errors
        report = EvalReport(generated_at="t")
        report.results = results
        summarize(report, published_recipe_ids={1})
        assert results[0].citation_grounding is True
        cit = report.metrics["citations"]
        assert cit["grounding_ratio"] == 1.0
        assert cit["grounding_cases"] == 1
        assert any("同源" in n and "grounding" in n for n in report.notes), (
            f"notes 应含 citation_hit 与 Hit@k 同源的口径标注: {report.notes}"
        )

    def test_grounding_none_when_no_candidates(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """空候选（error）用例 citations=[]、citation_hit=None 且不进 grounding 分母（测试方法）。

        异常：
            断言失败时 pytest 抛出 AssertionError。
        """
        self._patch_candidates(monkeypatch)
        cases = [
            EvalCase(id="rt-empty", dataset="retrieval", text="红烧肉（空候选）", expected_keywords=["红烧肉"]),
            EvalCase(id="rt-real", dataset="retrieval", text="红烧肉怎么做", expected_keywords=["红烧肉"]),
        ]
        results, errors = eval_retrieval(cases)
        assert not errors
        empty = next(r for r in results if r.case_id == "rt-empty")
        assert empty.error is not None, "空候选用例应记 error"
        assert empty.citations == []
        assert empty.citation_hit is None

        report = EvalReport(generated_at="t")
        report.results = results
        summarize(report, published_recipe_ids={1})
        assert empty.citation_grounding is None, "无 citations 的用例 grounding 应为 None（不参与校验）"
        cit = report.metrics["citations"]
        assert cit["grounding_cases"] == 1, f"空候选用例不应计入 grounding 分母: {cit}"

    def test_grounding_unavailable_without_published_ids(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """未提供已发布 id 集合（如数据库不可达）→ grounding unavailable 且 notes 归因（测试方法）。

        异常：
            断言失败时 pytest 抛出 AssertionError。
        """
        self._patch_candidates(monkeypatch)
        case = EvalCase(id="rt-noids", dataset="retrieval", text="红烧肉怎么做", expected_keywords=["红烧肉"])
        results, _ = eval_retrieval([case])
        report = EvalReport(generated_at="t")
        report.results = results
        summarize(report)
        assert results[0].citation_grounding is None, "未校验时 grounding 不得编造为 True/False"
        cit = report.metrics["citations"]
        assert cit["grounding_ratio"] is None
        assert cit["grounding_cases"] is None
        assert any("grounding" in n and "unavailable" in n for n in report.notes), (
            f"notes 应含 grounding unavailable 归因: {report.notes}"
        )

    def test_intent_results_have_no_citations(self) -> None:
        """intent 数据集用例 citations 恒空且 citation_hit / citation_grounding 均为 None（测试方法）。

        说明：
            intent/safety 等非检索路径不生成 citation（eval_retrieval 仅对检索
            用例构造 citations），不适用维度不编造数值。

        异常：
            断言失败时 pytest 抛出 AssertionError。
        """
        cases = [EvalCase(id="it-cit", dataset="intent", text="今天吃点什么好呢", expected_intent="free_qa")]
        results = eval_intent(cases)
        assert len(results) == 1
        r = results[0]
        assert r.citations == []
        assert r.citation_hit is None
        assert r.citation_grounding is None


class TestSummarizeTokenCost:
    """summarize 的 token_cost 段归因测试（测试类）。"""

    def test_token_cost_unavailable_with_reason(self) -> None:
        """token/cost 恒 unavailable 且归因明确、非估算口径（测试方法）。

        说明：
            评测路径为确定性兜底（关键词/规则/SQL）无 LLM 调用，无 usage 来源；
            estimated=False 表示未使用占位单价估算，绝不与实际计费混同。

        异常：
            断言失败时 pytest 抛出 AssertionError。
        """
        report = EvalReport(generated_at="t")
        summarize(report)
        tc = report.metrics["token_cost"]
        assert tc["total_tokens"] is None
        assert tc["total_cost_cents"] is None
        assert tc["estimated"] is False
        assert tc["reason"], "token/cost 段应携带 unavailable 归因说明"
        assert any("token" in n for n in report.notes)


class TestGateExcludesCitations:
    """回归门禁不纳入 citation 指标测试（测试类）。"""

    def test_gate_thresholds_exclude_citation_metric(self) -> None:
        """GATE_DEFAULTS 与 gate 判定结果均不含 citation 指标（测试方法）。

        说明：
            citation 覆盖为信息展示维度，不进门禁（避免新指标误伤既有门禁）。

        异常：
            断言失败时 pytest 抛出 AssertionError。
        """
        assert "citation_coverage" not in GATE_DEFAULTS
        report = EvalReport(generated_at="t")
        report.results = [_make_retrieval_result("rt-a", True)]
        summarize(report)
        gate = evaluate_gate(report, dict(GATE_DEFAULTS), offline=False)
        assert "citation_coverage" not in gate["thresholds"]
        assert "citation_coverage" not in gate["statuses"]
