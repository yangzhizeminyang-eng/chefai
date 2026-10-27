"""Agent Eval 回归门禁测试模块。

职责：
    覆盖 eval.run_eval 的回归门禁链路（评测函数全部 monkeypatch 桩替换，
    不依赖真实检索 / API / 数据库；数据集使用真实 eval/datasets 目录）：
    - 全部指标达标 → 退出 0，报告 gate.result=PASS；
    - 指标低于阈值 → 退出 1，gate 段含阈值 / 实际值 / 失败用例 ID；
    - 单条用例 error → 退出 1 且 failed_case_ids 含该用例 ID；
    - --offline 下检索指标标注 skipped，不触发 FAIL（退出 0）；
    - --no-gate 关闭门禁（指标再差也退出 0）；
    - --gate-file 放宽阈值后恢复退出 0。

运行约定：
    在 backend/ 目录下执行 `python -m pytest tests/test_eval_gate.py -q`；
    报告统一写入 pytest tmp_path，不污染 eval/reports/。
"""

from __future__ import annotations

import json
import math
from collections.abc import Callable
from pathlib import Path

import pytest

import eval.run_eval as run_eval
from eval.run_eval import EvalCase, EvalCaseResult

# backend 根目录（tests/ 的上一级）
BASE_DIR = Path(__file__).resolve().parents[1]
# 评测数据集目录（真实数据集：main 内部加载 + 测试取用例 ID 集合）
DATASETS_DIR = BASE_DIR / "eval" / "datasets"


# ---------------------------------------------------------------------------
# 评测函数桩工厂（返回受控结果，不触库 / 不触网）
# ---------------------------------------------------------------------------
def _make_intent_stub(
    fail_ids: set[str] | None = None, error_ids: set[str] | None = None
) -> Callable[[list[EvalCase]], list[EvalCaseResult]]:
    """构造意图评测桩（工厂函数）。

    说明：
        返回可直接替换 run_eval.eval_intent 的桩函数；fail_ids 内用例判
        passed=False，error_ids 内用例构造为 error（passed=None）。

    参数：
        fail_ids：期望判负的用例 ID 集合（None 视为空集）。
        error_ids：期望执行异常的用例 ID 集合（None 视为空集）。

    返回值：
        Callable[[list[EvalCase]], list[EvalCaseResult]]：意图评测桩函数。

    异常：
        无。
    """
    fail_ids = fail_ids or set()
    error_ids = error_ids or set()

    def _stub(cases: list[EvalCase]) -> list[EvalCaseResult]:
        """意图评测桩主体（内部函数）。

        参数：
            cases：main() 从真实数据集加载的意图用例列表。

        返回值：
            list[EvalCaseResult]：受控结果（与用例一一对应）。

        异常：
            无。
        """
        results: list[EvalCaseResult] = []
        for case in cases:
            if case.id in error_ids:
                results.append(
                    EvalCaseResult(
                        case_id=case.id,
                        dataset="intent",
                        expected_intent=case.expected_intent,
                        error="RuntimeError: 桩注入异常",
                    )
                )
            else:
                passed = case.id not in fail_ids
                results.append(
                    EvalCaseResult(
                        case_id=case.id,
                        dataset="intent",
                        expected_intent=case.expected_intent,
                        passed=passed,
                        predicted_intent=case.expected_intent if passed else "free_qa",
                    )
                )
        return results

    return _stub


def _make_safety_stub() -> Callable[[list[EvalCase], object], list[EvalCaseResult]]:
    """构造风控评测桩（工厂函数）。

    说明：
        返回全部通过的风控桩：blocked 与期望一致，高危记 HIT、正常记 OK。

    返回值：
        Callable：风控评测桩函数（签名兼容 eval_safety(cases, engine)）。

    异常：
        无。
    """

    def _stub(cases: list[EvalCase], engine: object) -> list[EvalCaseResult]:
        """风控评测桩主体（内部函数）。

        参数：
            cases：main() 加载的风控用例列表。
            engine：main() 传入的引擎实例（已被测试替换为哑对象，忽略）。

        返回值：
            list[EvalCaseResult]：全部通过的风控结果。

        异常：
            无。
        """
        return [
            EvalCaseResult(
                case_id=case.id,
                dataset="safety",
                expected_blocked=case.expected_blocked,
                passed=True,
                blocked=case.expected_blocked,
                status="HIT" if case.expected_blocked else "OK",
            )
            for case in cases
        ]

    return _stub


def _make_retrieval_stub(
    miss_hit3_ids: set[str] | None = None,
) -> Callable[[list[EvalCase]], tuple[list[EvalCaseResult], list[str]]]:
    """构造检索评测桩（工厂函数）。

    说明：
        所有用例 Hit@5 命中（passed=True，不产生失败用例）；miss_hit3_ids 内
        用例 Hit@3 未命中，用于构造「仅指标越界、无失败用例」的门禁失败场景。

    参数：
        miss_hit3_ids：期望 Hit@3 未命中的用例 ID 集合（None 视为空集）。

    返回值：
        Callable：检索评测桩函数（返回 (结果列表, 错误列表) 二元组）。

    异常：
        无。
    """
    miss_hit3_ids = miss_hit3_ids or set()

    def _stub(cases: list[EvalCase]) -> tuple[list[EvalCaseResult], list[str]]:
        """检索评测桩主体（内部函数）。

        参数：
            cases：main() 加载的检索用例列表。

        返回值：
            tuple[list[EvalCaseResult], list[str]]：(受控结果, 空错误列表)。

        异常：
            无。
        """
        results: list[EvalCaseResult] = []
        for case in cases:
            hit3 = case.id not in miss_hit3_ids
            results.append(
                EvalCaseResult(
                    case_id=case.id,
                    dataset="retrieval",
                    expected_keywords=case.expected_keywords,
                    passed=True,
                    titles=["红烧肉"],
                    hit_at_3=hit3,
                    hit_at_5=True,
                    recall_at_5=1.0,
                    mrr=1.0,
                )
            )
        return results, []

    return _stub


def _retrieval_forbidden(cases: list[EvalCase]) -> tuple[list[EvalCaseResult], list[str]]:
    """离线模式的检索评测哨兵桩（函数）。

    说明：
        --offline 下 main 不应调用检索评测；一旦被调用立即失败暴露。

    参数：
        cases：检索用例列表（不应到达）。

    返回值：
        无（永不返回）。

    异常：
        AssertionError：--offline 模式仍然执行了检索评测。
    """
    raise AssertionError("--offline 模式不应执行检索评测")


# 全部通过的桩（无内部状态，可跨测试共享）
INTENT_ALL_PASS = _make_intent_stub()
SAFETY_ALL_PASS = _make_safety_stub()
RETRIEVAL_ALL_PASS = _make_retrieval_stub()


def _run_main(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    run_label: str,
    argv_extra: list[str],
    intent_stub: Callable[[list[EvalCase]], list[EvalCaseResult]],
    safety_stub: Callable[[list[EvalCase], object], list[EvalCaseResult]],
    retrieval_stub: Callable[[list[EvalCase]], tuple[list[EvalCaseResult], list[str]]],
) -> tuple[int, dict]:
    """以受控桩运行 run_eval.main 并读取落盘报告（辅助函数）。

    参数：
        monkeypatch：pytest monkeypatch fixture。
        tmp_path：pytest 临时目录（报告输出根位置）。
        run_label：本次运行的子目录名（同一测试多次运行时隔离报告文件）。
        argv_extra：追加给 main 的额外 CLI 参数（--offline / --no-gate / --gate-file）。
        intent_stub：替换 run_eval.eval_intent 的桩。
        safety_stub：替换 run_eval.eval_safety 的桩。
        retrieval_stub：替换 run_eval.eval_retrieval 的桩。

    返回值：
        tuple[int, dict]：(main 退出码, 报告 JSON 解析后的字典)。

    异常：
        AssertionError：输出目录未产出唯一报告 JSON。
    """
    monkeypatch.setattr(run_eval, "eval_intent", intent_stub)
    monkeypatch.setattr(run_eval, "eval_safety", safety_stub)
    monkeypatch.setattr(run_eval, "eval_retrieval", retrieval_stub)
    # 风控引擎替换为哑工厂：避免 main 内构造真实 RiskEngine 连接数据库
    monkeypatch.setattr(run_eval, "RiskEngine", lambda: None)
    output_dir = tmp_path / run_label
    argv = ["--datasets-dir", str(DATASETS_DIR), "--output-dir", str(output_dir), *argv_extra]
    code = run_eval.main(argv)
    json_files = sorted(output_dir.glob("report_*.json"))
    assert len(json_files) == 1, f"输出目录应恰有 1 份报告 JSON: {json_files}"
    report = json.loads(json_files[0].read_text(encoding="utf-8"))
    return code, report


# ---------------------------------------------------------------------------
# 门禁端到端测试（main 级）
# ---------------------------------------------------------------------------
class TestEvalGate:
    """回归门禁端到端测试（main 级，评测函数全部桩替换）（测试类）。"""

    def test_gate_all_pass_exit_0(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        """全部指标达标：退出 0，gate.result=PASS 且全部状态为 pass（测试方法）。

        异常：
            断言失败时 pytest 抛出 AssertionError。
        """
        code, report = _run_main(
            monkeypatch, tmp_path, "all_pass", [], INTENT_ALL_PASS, SAFETY_ALL_PASS, RETRIEVAL_ALL_PASS
        )
        assert code == 0
        gate = report["gate"]
        assert gate["enabled"] is True
        assert gate["result"] == "PASS"
        assert set(gate["statuses"].values()) == {"pass"}
        assert gate["failed_case_ids"] == []
        # 阈值段完整覆盖六项默认指标
        assert set(gate["thresholds"]) == set(run_eval.GATE_DEFAULTS)

    def test_gate_below_threshold_exit_1(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        """意图准确率 0.5 低于阈值：退出 1，gate 段含阈值/实际值/失败用例（测试方法）。

        异常：
            断言失败时 pytest 抛出 AssertionError。
        """
        intent_cases = run_eval.load_dataset(DATASETS_DIR / "intent_cases.jsonl", "intent")
        fail_ids = {c.id for c in intent_cases[len(intent_cases) // 2 :]}
        code, report = _run_main(
            monkeypatch,
            tmp_path,
            "below_threshold",
            [],
            _make_intent_stub(fail_ids=fail_ids),
            SAFETY_ALL_PASS,
            RETRIEVAL_ALL_PASS,
        )
        assert code == 1
        gate = report["gate"]
        assert gate["result"] == "FAIL"
        assert gate["actual"]["intent_accuracy"] == 0.5
        assert gate["thresholds"]["intent_accuracy"] == 0.8
        assert gate["statuses"]["intent_accuracy"] == "fail"
        # 失败用例 ID 动态取自后半段切分（不硬编码具体 ID，避免数据集扩充时断言失效）
        assert sorted(fail_ids)[0] in gate["failed_case_ids"]
        assert set(gate["failed_case_ids"]) == fail_ids

    def test_gate_case_error_exit_1(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        """单条用例 error：退出 1 且 failed_case_ids 含该 ID（测试方法）。

        说明：
            意图准确率仍为 1.0（23 条有效用例全对），验证「用例 error 独立于
            指标阈值触发维度 fail」的门禁语义。

        异常：
            断言失败时 pytest 抛出 AssertionError。
        """
        code, report = _run_main(
            monkeypatch,
            tmp_path,
            "case_error",
            [],
            _make_intent_stub(error_ids={"it-007"}),
            SAFETY_ALL_PASS,
            RETRIEVAL_ALL_PASS,
        )
        assert code == 1
        gate = report["gate"]
        assert gate["result"] == "FAIL"
        assert gate["actual"]["intent_accuracy"] == 1.0  # 指标本身达标
        assert gate["statuses"]["intent_accuracy"] == "fail"  # 但用例 error 触发维度 fail
        assert "it-007" in gate["failed_case_ids"]

    def test_gate_offline_skipped_not_fail(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        """--offline：检索指标 skipped，不触发 FAIL（退出 0）（测试方法）。

        说明：
            检索哨兵桩保证 --offline 下检索评测确实未执行；检索指标既非
            pass 也非 fail，而是 skipped，且整体门禁仍 PASS。

        异常：
            断言失败时 pytest 抛出 AssertionError。
        """
        code, report = _run_main(
            monkeypatch, tmp_path, "offline", ["--offline"], INTENT_ALL_PASS, SAFETY_ALL_PASS, _retrieval_forbidden
        )
        assert code == 0
        gate = report["gate"]
        assert gate["result"] == "PASS"
        assert gate["actual"]["hit_at_3"] is None
        assert gate["statuses"]["hit_at_3"] == "skipped"
        assert gate["statuses"]["hit_at_5"] == "skipped"
        assert gate["statuses"]["recall_at_5"] == "skipped"
        assert gate["statuses"]["intent_accuracy"] == "pass"

    def test_no_gate_exit_0(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        """--no-gate：指标再差也退出 0，gate.enabled=False（测试方法）。

        异常：
            断言失败时 pytest 抛出 AssertionError。
        """
        intent_cases = run_eval.load_dataset(DATASETS_DIR / "intent_cases.jsonl", "intent")
        all_fail = {c.id for c in intent_cases}
        code, report = _run_main(
            monkeypatch,
            tmp_path,
            "no_gate",
            ["--no-gate"],
            _make_intent_stub(fail_ids=all_fail),
            SAFETY_ALL_PASS,
            RETRIEVAL_ALL_PASS,
        )
        assert code == 0
        assert report["gate"]["enabled"] is False

    def test_gate_file_override(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        """--gate-file 放宽阈值：默认门禁退出 1，放宽后退出 0（测试方法）。

        说明：
            构造「Hit@3 部分未命中但 Hit@5 全命中」场景：无失败用例、仅
            hit_at_3 越默认阈值（0.70）；gate 文件将其放宽至 0.50 后恢复通过，
            验证阈值覆盖生效。

        异常：
            断言失败时 pytest 抛出 AssertionError。
        """
        retrieval_cases = run_eval.load_dataset(DATASETS_DIR / "retrieval_cases.jsonl", "retrieval")
        # 让约 40% 用例 Hit@3 未命中（Hit@5 仍全命中 → 不产生失败用例）
        miss_hit3 = {c.id for c in retrieval_cases[: math.ceil(len(retrieval_cases) * 0.4)]}
        retrieval_stub = _make_retrieval_stub(miss_hit3_ids=miss_hit3)
        # 默认阈值：hit_at_3 < 0.70 → FAIL / 退出 1
        code_default, _ = _run_main(
            monkeypatch, tmp_path, "override_default", [], INTENT_ALL_PASS, SAFETY_ALL_PASS, retrieval_stub
        )
        assert code_default == 1
        # 放宽 hit_at_3 至 0.50 → PASS / 退出 0
        gate_file = tmp_path / "gate_relaxed.json"
        gate_file.write_text(json.dumps({"hit_at_3": 0.5}), encoding="utf-8")
        code_relaxed, report = _run_main(
            monkeypatch,
            tmp_path,
            "override_relaxed",
            ["--gate-file", str(gate_file)],
            INTENT_ALL_PASS,
            SAFETY_ALL_PASS,
            retrieval_stub,
        )
        assert code_relaxed == 0
        gate = report["gate"]
        assert gate["thresholds"]["hit_at_3"] == 0.5
        assert gate["result"] == "PASS"
