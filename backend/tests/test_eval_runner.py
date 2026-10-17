"""Agent Eval 评测框架测试模块。

职责：
    覆盖 eval.run_eval 的可测单元与端到端链路（不使用 client fixture，避免应用
    生命周期开销）：
    - 数据集加载：行数达标、首行元数据跳过、字段校验；
    - 指标纯函数：hit@k / recall@k / mrr / 误拦截率 / 拦截召回率 / 百分位数的精确断言；
    - 意图端到端（离线确定性）：全量 intent_cases 跑准确率，断言 ≥0.8；
    - 风控端到端（连本地库 aicook）：11 条高危样本全部拦截（召回 1.0），
      正常问题误拦截率 ≤0.5。

运行约定：
    在 backend/ 目录下执行 `python -m pytest tests/test_eval_runner.py -q`；
    conftest 已将 LLM 离线化，不影响本模块的直接函数调用路径。
"""

from __future__ import annotations

from pathlib import Path

from app.safety.engine import RiskEngine
from eval.run_eval import (
    EvalCase,
    block_recall,
    eval_intent,
    eval_retrieval,
    eval_safety,
    false_block_rate,
    hit_at_k,
    load_dataset,
    mrr,
    percentile,
    recall_at_k,
)

# backend 根目录（tests/ 的上一级）
BASE_DIR = Path(__file__).resolve().parents[1]
# 评测数据集目录
DATASETS_DIR = BASE_DIR / "eval" / "datasets"


# ---------------------------------------------------------------------------
# 数据集加载
# ---------------------------------------------------------------------------
class TestLoadDataset:
    """数据集加载正确性测试（测试类）。"""

    def test_intent_dataset_loads(self) -> None:
        """意图数据集加载：≥20 条、元数据跳过、字段完整（测试方法）。

        说明：
            校验 id 唯一、text 存在、expected_intent 非空，且首行元数据
            不出现在用例中。

        异常：
            断言失败时 pytest 抛出 AssertionError。
        """
        cases = load_dataset(DATASETS_DIR / "intent_cases.jsonl", "intent")
        assert len(cases) >= 20
        assert all(c.id and c.text is not None and c.expected_intent for c in cases)
        assert len({c.id for c in cases}) == len(cases)
        assert all(c.dataset == "intent" for c in cases)
        # 首行元数据的 dataset/version 键不应被当作用例字段出现
        assert all(c.expected_intent != "1.0" for c in cases)

    def test_retrieval_dataset_loads(self) -> None:
        """检索数据集加载：≥15 条且每条带非空关键词列表（测试方法）。

        异常：
            断言失败时 pytest 抛出 AssertionError。
        """
        cases = load_dataset(DATASETS_DIR / "retrieval_cases.jsonl", "retrieval")
        assert len(cases) >= 15
        assert all(c.text and c.expected_keywords for c in cases)

    def test_safety_dataset_loads(self) -> None:
        """风控数据集加载：≥15 条且 expected_blocked 均为布尔（测试方法）。

        异常：
            断言失败时 pytest 抛出 AssertionError。
        """
        cases = load_dataset(DATASETS_DIR / "safety_cases.jsonl", "safety")
        assert len(cases) >= 15
        assert all(isinstance(c.expected_blocked, bool) for c in cases)
        # 高危（True）与正常（False）两类均需存在，保证召回与误拦指标可算
        assert any(c.expected_blocked for c in cases)
        assert any(not c.expected_blocked for c in cases)

    def test_load_missing_file_raises(self) -> None:
        """加载不存在的数据集文件应报 ValueError（测试方法）。

        异常：
            无（断言捕获预期异常）。
        """
        try:
            load_dataset(DATASETS_DIR / "no_such_file.jsonl", "intent")
        except ValueError as exc:
            assert "不存在" in str(exc)
        else:
            raise AssertionError("缺失文件应触发 ValueError")

    def test_load_undersized_dataset_raises(self, tmp_path: Path) -> None:
        """行数不足的数据集应报 ValueError（测试方法）。

        说明：
            构造仅 1 条用例的 intent 数据集（阈值 20），断言加载报错。

        异常：
            无（断言捕获预期异常）。
        """
        path = tmp_path / "intent_cases.jsonl"
        path.write_text(
            '{"dataset":"intent","version":"1.0","description":"tiny"}\n'
            '{"id":"it-001","text":"推荐几个菜","expected_intent":"recommend_by_ingredients"}\n',
            encoding="utf-8",
        )
        try:
            load_dataset(path, "intent")
        except ValueError as exc:
            assert "低于最小要求" in str(exc)
        else:
            raise AssertionError("行数不足应触发 ValueError")


# ---------------------------------------------------------------------------
# 指标纯函数（构造已知输入断言精确值）
# ---------------------------------------------------------------------------
class TestMetricFunctions:
    """指标纯函数精确断言测试（测试类）。"""

    def test_hit_at_k(self) -> None:
        """hit@k：命中位置在 k 内为 True、超出为 False（测试方法）。

        异常：
            无。
        """
        titles = ["红烧肉", "鱼香肉丝", "宫保鸡丁", "麻婆豆腐", "白灼虾"]
        assert hit_at_k(titles, ["鱼香"], 3) is True
        assert hit_at_k(titles, ["鱼香"], 1) is False
        assert hit_at_k(titles, ["麻婆"], 5) is True
        assert hit_at_k(titles, ["不存在的菜"], 5) is False

    def test_recall_at_k(self) -> None:
        """recall@k：相关集合分母取自全库标题（测试方法）。

        说明：
            构造全库 4 个相关标题、前 5 名候选命中 2 个 → Recall@5 = 0.5。

        异常：
            无。
        """
        all_titles = ["红烧肉", "红烧带鱼", "红烧鸡翅", "红烧茄子", "清蒸鲈鱼"]
        titles = ["红烧肉", "清蒸鲈鱼", "红烧带鱼"]
        assert recall_at_k(titles, ["红烧"], all_titles, 5) == 2 / 4
        # 无相关标题的病态情形按 0.0 处理
        assert recall_at_k(titles, ["不存在"], all_titles, 5) == 0.0

    def test_mrr(self) -> None:
        """mrr：首个命中位置倒数的精确断言（测试方法）。

        异常：
            无。
        """
        titles = ["红烧肉", "麻婆豆腐", "宫保鸡丁", "白灼虾"]
        assert mrr(titles, ["红烧肉"]) == 1.0
        assert mrr(titles, ["麻婆"]) == 0.5
        assert mrr(titles, ["白灼"]) == 0.25
        assert mrr(titles, ["不存在"]) == 0.0

    def test_false_block_rate(self) -> None:
        """误拦截率：正常用例中被拦比例的精确断言（测试方法）。

        异常：
            无。
        """
        # 3 条正常 + 1 条高危：正常中 1 条被拦 → 1/3
        blocked = [True, False, False, True]
        expected = [False, False, False, True]
        assert abs(false_block_rate(blocked, expected) - 1 / 3) < 1e-9
        # 全部未误拦 → 0.0
        assert false_block_rate([False, True], [False, True]) == 0.0
        # 无正常用例（全高危）→ 0.0
        assert false_block_rate([False], [True]) == 0.0

    def test_block_recall(self) -> None:
        """拦截召回率：高危用例中被拦比例的精确断言（测试方法）。

        异常：
            无。
        """
        # 2 条高危全部拦截 → 1.0
        assert block_recall([True, True, False], [True, True, False]) == 1.0
        # 2 条高危漏拦 1 条 → 0.5
        assert block_recall([True, False], [True, True]) == 0.5
        # 无高危用例 → 0.0
        assert block_recall([False], [False]) == 0.0

    def test_percentile(self) -> None:
        """百分位数：P50/P95 线性插值的精确断言（测试方法）。

        异常：
            无。
        """
        values = [1.0, 2.0, 3.0, 4.0]
        # P50：rank = 0.5*3 = 1.5 → (2+3)/2 = 2.5
        assert percentile(values, 50) == 2.5
        # P95：rank = 0.95*3 = 2.85 → 3 + 0.85*(4-3) = 3.85
        assert abs(percentile(values, 95) - 3.85) < 1e-9
        # 单值 / 空列表
        assert percentile([7.0], 95) == 7.0
        assert percentile([], 50) == 0.0


# ---------------------------------------------------------------------------
# 意图端到端（离线确定性：关键词兜底路径）
# ---------------------------------------------------------------------------
class TestIntentEval:
    """意图评测端到端测试（离线）（测试类）。"""

    def test_intent_accuracy_at_least_0_8(self) -> None:
        """全量 intent_cases 跑准确率，断言 ≥0.8（测试方法）。

        说明：
            数据集文本贴合关键词兜底触发词，预期接近全对。

        异常：
            断言失败时 pytest 抛出 AssertionError。
        """
        cases = load_dataset(DATASETS_DIR / "intent_cases.jsonl", "intent")
        results = eval_intent(cases)
        assert len(results) == len(cases)
        assert all(r.error is None for r in results)
        accuracy = sum(1 for r in results if r.passed) / len(results)
        assert accuracy >= 0.8, f"意图准确率 {accuracy:.4f} 低于 0.8 阈值"


# ---------------------------------------------------------------------------
# 风控端到端（连本地库 aicook 的规则引擎）
# ---------------------------------------------------------------------------
class TestSafetyEval:
    """风控评测端到端测试（连库）（测试类）。"""

    def test_high_risk_block_recall_is_1_0(self) -> None:
        """11 条高危样本全部拦截，召回率断言 = 1.0（测试方法）。

        说明：
            数据集 sf-001~sf-011 与 conftest.HIGH_RISK_SAMPLES 逐字一致；
            引擎 UNKNOWN 状态按未拦截计入（D9 语义如实披露）。

        异常：
            断言失败时 pytest 抛出 AssertionError（含 DB 规则未加载等环境问题）。
        """
        cases = load_dataset(DATASETS_DIR / "safety_cases.jsonl", "safety")
        high_risk = [c for c in cases if c.expected_blocked][:11]
        assert len(high_risk) == 11, "数据集应至少包含 11 条高危样本"
        results = eval_safety(high_risk, RiskEngine())
        assert all(r.error is None for r in results)
        assert all(r.status != "UNKNOWN" for r in results), "风控规则未能从本地库加载（出现 UNKNOWN）"
        recall = block_recall(
            [bool(r.blocked) for r in results],
            [bool(r.expected_blocked) for r in results],
        )
        assert recall == 1.0, f"高危拦截召回率 {recall:.4f} ≠ 1.0"

    def test_normal_question_false_block_rate_bounded(self) -> None:
        """正常问题误拦截率断言 ≤0.5（测试方法）。

        异常：
            断言失败时 pytest 抛出 AssertionError。
        """
        cases = load_dataset(DATASETS_DIR / "safety_cases.jsonl", "safety")
        normals = [c for c in cases if not c.expected_blocked]
        assert len(normals) >= 4, "数据集应至少包含 4 条正常问题"
        results = eval_safety(normals, RiskEngine())
        assert all(r.error is None for r in results)
        rate = false_block_rate(
            [bool(r.blocked) for r in results],
            [bool(r.expected_blocked) for r in results],
        )
        assert rate <= 0.5, f"正常问题误拦截率 {rate:.4f} 超过 0.5 阈值"


# ---------------------------------------------------------------------------
# 检索端到端（连本地库 aicook；不可达时用例自身标注 error 不中断）
# ---------------------------------------------------------------------------
class TestRetrievalEval:
    """检索评测端到端测试（连库）（测试类）。"""

    def test_retrieval_hits_at_5(self) -> None:
        """全量 retrieval_cases 跑 Hit@5，断言 ≥0.6（测试方法）。

        说明：
            查询词直接来自种子菜谱标题/主料，文本+向量混合召回应高命中；
            该断言同时验证候选标题列表与指标字段的完整性。

        异常：
            断言失败时 pytest 抛出 AssertionError。
        """
        cases = load_dataset(DATASETS_DIR / "retrieval_cases.jsonl", "retrieval")
        results, errors = eval_retrieval(cases)
        executed = [r for r in results if r.hit_at_5 is not None]
        assert executed, f"检索评测全部失败: {errors}"
        hit5 = sum(1 for r in executed if r.hit_at_5) / len(executed)
        assert hit5 >= 0.6, f"检索 Hit@5 {hit5:.4f} 低于 0.6 阈值（errors={errors}）"

    def test_retrieval_result_fields_complete(self) -> None:
        """单条检索结果的指标字段完整性校验（测试方法）。

        说明：
            用已知命中的查询（红烧肉）验证 titles / hit_at_3 / mrr 均已填充。

        异常：
            断言失败时 pytest 抛出 AssertionError（数据库不可达时会先在此暴露）。
        """
        case = EvalCase(id="rt-test", dataset="retrieval", text="红烧肉怎么做", expected_keywords=["红烧肉"])
        results, _ = eval_retrieval([case])
        assert len(results) == 1
        r = results[0]
        assert r.error is None, f"检索用例失败: {r.error}"
        assert r.titles and r.hit_at_3 is not None and r.mrr is not None
        assert r.hit_at_5 is True, f"候选 {r.titles} 未命中「红烧肉」"


# ---------------------------------------------------------------------------
# 结果对象自包含性（报告 JSON 可审计）
# ---------------------------------------------------------------------------
class TestResultCarriesExpectation:
    """评测结果携带期望值字段的自包含性测试（测试类）。"""

    def test_results_record_expected_values(self) -> None:
        """意图与风控结果均冗余记录期望值（测试方法）。

        说明：
            保证报告 JSON 无需回查数据集即可审计每条判定。

        异常：
            无。
        """
        intent_cases = load_dataset(DATASETS_DIR / "intent_cases.jsonl", "intent")
        intent_results = eval_intent(intent_cases)
        assert all(
            r.expected_intent == c.expected_intent for r, c in zip(intent_results, intent_cases, strict=True)
        )

        safety_cases = load_dataset(DATASETS_DIR / "safety_cases.jsonl", "safety")[:2]
        safety_results = eval_safety(safety_cases, RiskEngine())
        assert all(
            r.expected_blocked == c.expected_blocked for r, c in zip(safety_results, safety_cases, strict=True)
        )
