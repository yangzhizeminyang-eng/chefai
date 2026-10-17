"""Agent Eval 评测框架 CLI 模块。

职责：
    对三条核心链路执行离线评测并产出报告（python -m eval.run_eval，约定 cwd=backend/）：
    - 意图识别：逐条调用 supervisor._keyword_fallback（确定性关键词兜底路径，离线可测），
      计算准确率；
    - 风控拦截：逐条调用 RiskEngine.scan("input", text)（规则引擎，规则来自本地 risk_rule
      表；引擎任何异常内部消化为 UNKNOWN=不拦截，按 D9 语义在报告中如实统计），
      计算高危拦截召回率与正常问题误拦截率；
    - 检索命中：逐条调用 ability.retrieval.retrieve_candidates（空食材 + 文本查询），
      计算 Hit@3 / Hit@5 / Recall@5 / MRR；--offline 时跳过并标注 unavailable。

诚实性约定：
    引用覆盖率与 Token/费用指标当前链路无可靠来源，报告一律输出 "unavailable" 并注明
    原因，绝不编造数字；单条用例失败记 error 不中断整体评测。

回归门禁：
    报告顶层输出 gate 段（阈值 / 实际值 / 各指标状态 / 失败用例 / 结果），默认阈值
    GATE_DEFAULTS：intent_accuracy ≥0.80、block_recall ≥1.00、false_block_rate ≤0.10、
    hit_at_3 ≥0.70、hit_at_5 ≥0.70、recall_at_5 ≥0.30；--gate-file 可用 JSON 覆盖阈值，
    --no-gate 关闭门禁（退出码恒 0）。任一可执行用例失败（passed=False 或 error 非空）
    直接判其所属维度 fail；--offline 时检索类指标标注 skipped 不触发 FAIL。
    退出码：0 成功（含门禁通过与 --no-gate）、1 门禁启用且 FAIL、2 数据集/阈值加载失败；
    报告（JSON+MD）在评测流程内任何情况下都落盘。

输出：
    eval/reports/report_YYYYmmdd_HHMMSS.json + 同名 .md 摘要表
    （--baseline 时文件名前缀改为 baseline_）。
"""

from __future__ import annotations

import argparse
import json
import math
import sys
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path

from sqlalchemy import select

# 保证以 `python -m eval.run_eval` 之外的方式（如直接执行脚本）也能导入 app 包
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.ability.retrieval import retrieve_candidates  # noqa: E402
from app.core.db import SessionLocal  # noqa: E402
from app.graph.nodes.supervisor import _keyword_fallback  # noqa: E402
from app.models import Recipe  # noqa: E402
from app.safety.engine import RiskEngine  # noqa: E402

# 各数据集最小行数（不含首行元数据），不足即视为数据集损坏
MIN_DATASET_SIZES: dict[str, int] = {"intent": 20, "retrieval": 15, "safety": 15}

# 意图合法取值（与 supervisor.INTENTS 一致，用于数据集字段校验）
VALID_INTENTS: frozenset[str] = frozenset(
    {
        "recommend_by_ingredients",
        "search_recipe",
        "photo_recognize",
        "free_qa",
        "cooking_help",
        "nutrition_query",
        "inventory_op",
        "smalltalk_or_out_of_scope",
        "composite_recommend_nutrition",
        "innovation",
    }
)

# 引用覆盖率与 Token/费用在当前链路无可靠来源的统一说明
UNAVAILABLE_NOTE_CITATIONS = "citations 覆盖率 unavailable：当前回答链路未产出可校验的引用来源字段"
UNAVAILABLE_NOTE_TOKEN = "token/cost unavailable：评测路径为确定性兜底（关键词/规则/SQL），无模型调用与计费数据"
UNAVAILABLE_NOTE_RETRIEVAL_OFFLINE = "retrieval 指标 unavailable：--offline 模式跳过检索评测"


# ---------------------------------------------------------------------------
# 数据结构
# ---------------------------------------------------------------------------
@dataclass
class EvalCase:
    """单条评测用例（类）。

    说明：
        三类数据集共用一个容器，按 dataset 字段解释 text 与期望值的含义。

    属性：
        id：用例唯一标识（如 it-001 / rt-003 / sf-012）。
        dataset：数据集名（intent / retrieval / safety）。
        text：待评测文本（intent 用输入文本、retrieval 用查询文本、safety 用待检文本）。
        expected_intent：意图数据集的期望意图名（其余数据集为 None）。
        expected_keywords：检索数据集的期望命中关键词列表（其余数据集为 None）。
        expected_blocked：风控数据集的期望拦截布尔值（其余数据集为 None）。
    """

    id: str
    dataset: str
    text: str
    expected_intent: str | None = None
    expected_keywords: list[str] | None = None
    expected_blocked: bool | None = None


@dataclass
class EvalCaseResult:
    """单条用例的评测结果（类）。

    说明：
        passed=None 表示该用例未执行（error / unavailable）；error 非空时其余
        细分字段无意义；期望值从用例冗余记录，保证报告 JSON 自包含可审计。

    属性：
        case_id：对应 EvalCase.id。
        dataset：数据集名。
        expected_intent：期望意图名（意图数据集用）。
        expected_keywords：期望命中关键词（检索数据集用）。
        expected_blocked：期望拦截布尔值（风控数据集用）。
        passed：是否通过（error / 未执行时为 None）。
        latency_ms：该用例执行耗时（毫秒）。
        error：失败原因（成功为 None）。
        predicted_intent：意图数据集的预测意图。
        blocked：风控数据集的实际拦截布尔值。
        status：风控判定状态（OK / HIT / UNKNOWN）。
        titles：检索数据集返回的候选标题列表。
        hit_at_3 / hit_at_5：检索前 3 / 前 5 名内是否命中期望关键词。
        recall_at_5：前 5 名对全库相关标题的召回比例。
        mrr：首个命中位置倒数（无命中为 0.0）。
    """

    case_id: str
    dataset: str
    expected_intent: str | None = None
    expected_keywords: list[str] | None = None
    expected_blocked: bool | None = None
    passed: bool | None = None
    latency_ms: float = 0.0
    error: str | None = None
    predicted_intent: str | None = None
    blocked: bool | None = None
    status: str | None = None
    titles: list[str] = field(default_factory=list)
    hit_at_3: bool | None = None
    hit_at_5: bool | None = None
    recall_at_5: float | None = None
    mrr: float | None = None


@dataclass
class EvalReport:
    """整体评测报告（类）。

    说明：
        汇总全部用例结果与各数据集指标；unavailable 的指标值为 None 并在
        notes 中注明原因，绝不编造数字。

    属性：
        generated_at：报告生成时间（ISO 格式）。
        file_stamp：文件名时间戳（YYYYmmdd_HHMMSS）。
        results：全部用例结果列表。
        metrics：{数据集名: 指标字典}（指标可能含 None 表示 unavailable）。
        notes：不可用指标与异常情况的说明列表。
        gate：回归门禁段（空 dict 表示尚未判定；--no-gate 时含 enabled=False）。
    """

    generated_at: str
    file_stamp: str = ""
    results: list[EvalCaseResult] = field(default_factory=list)
    metrics: dict[str, dict] = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)
    gate: dict[str, object] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# 指标纯函数（不依赖数据库与网络，便于单测构造已知输入验证）
# ---------------------------------------------------------------------------
def hit_at_k(titles: list[str], keywords: list[str], k: int) -> bool:
    """判断前 k 条候选标题中是否命中任一期望关键词（函数）。

    说明：
        命中定义：标题文本包含任一 expected_keyword 子串。

    参数：
        titles：候选标题列表（按检索排序）。
        keywords：期望命中的关键词列表。
        k：截断位置（前 k 条）。

    返回值：
        bool：前 k 条内命中任一关键词返回 True，否则 False。

    异常：
        无。
    """
    return any(any(kw in title for kw in keywords) for title in titles[:k])


def recall_at_k(titles: list[str], keywords: list[str], all_titles: list[str], k: int) -> float:
    """计算前 k 条候选对全库相关标题的召回比例（函数）。

    说明：
        相关集合 = 全库标题中包含任一期望关键词的标题集合；
        Recall@K = |前 k 条候选 ∩ 相关集合| / |相关集合|；
        全库无相关标题（关键词不存在的病态情形）按 0.0 处理。

    参数：
        titles：候选标题列表（按检索排序）。
        keywords：期望命中的关键词列表。
        all_titles：全库标题集合（用于划定相关集合）。
        k：截断位置。

    返回值：
        float：召回比例 ∈ [0.0, 1.0]。

    异常：
        无。
    """
    relevant = {t for t in all_titles if any(kw in t for kw in keywords)}
    if not relevant:
        return 0.0
    hits = sum(1 for t in titles[:k] if t in relevant)
    return hits / len(relevant)


def mrr(titles: list[str], keywords: list[str]) -> float:
    """计算单条查询的倒数排名 RR（函数）。

    说明：
        RR = 1 / 首个命中标题的名次；无命中为 0.0。
        多条查询的 MRR 由调用方对各条 RR 取均值。

    参数：
        titles：候选标题列表（按检索排序）。
        keywords：期望命中的关键词列表。

    返回值：
        float：单条查询的倒数排名 ∈ [0.0, 1.0]。

    异常：
        无。
    """
    for idx, title in enumerate(titles, start=1):
        if any(kw in title for kw in keywords):
            return 1.0 / idx
    return 0.0


def false_block_rate(blocked_flags: list[bool], expected_flags: list[bool]) -> float:
    """计算误拦截率（函数）。

    说明：
        在期望「不拦截」（expected=False）的用例中，被实际拦截的比例；
        无正常用例时按 0.0 处理。

    参数：
        blocked_flags：各用例实际是否拦截（与 expected_flags 一一对应）。
        expected_flags：各用例期望是否拦截。

    返回值：
        float：误拦截比例 ∈ [0.0, 1.0]。

    异常：
        无。
    """
    normals = [b for b, e in zip(blocked_flags, expected_flags, strict=True) if not e]
    if not normals:
        return 0.0
    return sum(1 for b in normals if b) / len(normals)


def block_recall(blocked_flags: list[bool], expected_flags: list[bool]) -> float:
    """计算高危拦截召回率（函数）。

    说明：
        在期望「拦截」（expected=True）的用例中，被实际拦截的比例；
        无高危用例时按 0.0 处理。

    参数：
        blocked_flags：各用例实际是否拦截（与 expected_flags 一一对应）。
        expected_flags：各用例期望是否拦截。

    返回值：
        float：拦截召回率 ∈ [0.0, 1.0]。

    异常：
        无。
    """
    risks = [b for b, e in zip(blocked_flags, expected_flags, strict=True) if e]
    if not risks:
        return 0.0
    return sum(1 for b in risks if b) / len(risks)


def percentile(values: list[float], p: float) -> float:
    """计算百分位数（纯函数，线性插值法）。

    说明：
        与 numpy.percentile 默认（linear）插值一致：
        rank = p/100 * (n-1)，取相邻两值线性插值；空列表按 0.0 处理。

    参数：
        values：样本值列表。
        p：百分位（0~100，如 50 表示 P50）。

    返回值：
        float：百分位数。

    异常：
        无。
    """
    if not values:
        return 0.0
    ordered = sorted(values)
    rank = (p / 100) * (len(ordered) - 1)
    lower = math.floor(rank)
    upper = math.ceil(rank)
    if lower == upper:
        return ordered[int(rank)]
    return ordered[lower] + (ordered[upper] - ordered[lower]) * (rank - lower)


# ---------------------------------------------------------------------------
# 数据集加载
# ---------------------------------------------------------------------------
def load_dataset(path: Path, dataset_name: str) -> list[EvalCase]:
    """加载单个 JSONL 评测数据集（函数）。

    说明：
        首行为元数据行（须含 dataset 键且与期望一致），跳过不参与评测；
        之后每行为一条用例，按数据集类型校验必需字段（intent 需合法意图值、
        retrieval 需非空关键词列表、safety 需布尔 expected_blocked）；
        行数低于 MIN_DATASET_SIZES 阈值视为数据集损坏，直接报错。

    参数：
        path：JSONL 文件路径。
        dataset_name：期望的数据集名（intent / retrieval / safety）。

    返回值：
        list[EvalCase]：评测用例列表。

    异常：
        ValueError：文件不存在、元数据不匹配、字段缺失/非法或行数不足。
    """
    if not path.exists():
        raise ValueError(f"数据集文件不存在: {path}")
    min_size = MIN_DATASET_SIZES.get(dataset_name)
    if min_size is None:
        raise ValueError(f"未知数据集类型: {dataset_name}")
    cases: list[EvalCase] = []
    with path.open("r", encoding="utf-8") as f:
        for line_no, raw in enumerate(f, start=1):
            line = raw.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"{path.name} 第 {line_no} 行 JSON 解析失败: {exc}") from exc
            if line_no == 1:
                if row.get("dataset") != dataset_name:
                    raise ValueError(f"{path.name} 首行元数据 dataset 应为 {dataset_name}")
                continue
            case_id = row.get("id")
            text = row.get("text", row.get("query"))
            if not case_id or text is None:
                raise ValueError(f"{path.name} 第 {line_no} 行缺少 id/text 字段")
            if dataset_name == "intent":
                intent = row.get("expected_intent")
                if intent not in VALID_INTENTS:
                    raise ValueError(f"{path.name} 第 {line_no} 行意图非法: {intent!r}")
                cases.append(EvalCase(id=case_id, dataset=dataset_name, text=text, expected_intent=intent))
            elif dataset_name == "retrieval":
                keywords = row.get("expected_keywords")
                if not keywords or not isinstance(keywords, list):
                    raise ValueError(f"{path.name} 第 {line_no} 行缺少 expected_keywords")
                cases.append(
                    EvalCase(id=case_id, dataset=dataset_name, text=text, expected_keywords=[str(k) for k in keywords])
                )
            else:  # safety
                blocked = row.get("expected_blocked")
                if not isinstance(blocked, bool):
                    raise ValueError(f"{path.name} 第 {line_no} 行 expected_blocked 必须为布尔值")
                cases.append(EvalCase(id=case_id, dataset=dataset_name, text=text, expected_blocked=blocked))
    if len(cases) < min_size:
        raise ValueError(f"{path.name} 用例数 {len(cases)} 低于最小要求 {min_size}")
    return cases


# ---------------------------------------------------------------------------
# 各链路评测器
# ---------------------------------------------------------------------------
def eval_intent(cases: list[EvalCase]) -> list[EvalCaseResult]:
    """执行意图识别评测（关键词兜底路径，离线确定性）（函数）。

    说明：
        对每条文本调用 supervisor._keyword_fallback(text, has_ingredients=False)
        得到预测意图，与期望意图比对；单条异常记 error 继续。

    参数：
        cases：意图评测用例列表。

    返回值：
        list[EvalCaseResult]：评测结果列表（与用例一一对应）。

    异常：
        不抛出（单条异常内部消化为 error 结果）。
    """
    results: list[EvalCaseResult] = []
    for case in cases:
        start = time.perf_counter()
        try:
            predicted = _keyword_fallback(case.text, has_ingredients=False)
            results.append(
                EvalCaseResult(
                    case_id=case.id,
                    dataset=case.dataset,
                    expected_intent=case.expected_intent,
                    passed=predicted == case.expected_intent,
                    latency_ms=round((time.perf_counter() - start) * 1000, 3),
                    predicted_intent=predicted,
                )
            )
        except Exception as exc:  # noqa: BLE001 —— 单条失败不中断评测
            results.append(
                EvalCaseResult(
                    case_id=case.id,
                    dataset=case.dataset,
                    expected_intent=case.expected_intent,
                    error=f"{type(exc).__name__}: {exc}",
                    latency_ms=round((time.perf_counter() - start) * 1000, 3),
                )
            )
    return results


def eval_safety(cases: list[EvalCase], engine: RiskEngine) -> list[EvalCaseResult]:
    """执行风控拦截评测（函数）。

    说明：
        对每条文本调用 engine.scan("input", text) 得到判定，blocked 取判定的
        block 字段（UNKNOWN 时为 False，语义与引擎 D9 约定一致）；判定状态
        原样记录，供报告如实披露 UNKNOWN（风控不可用）数量。

    参数：
        cases：风控评测用例列表。
        engine：风控引擎实例（规则来自本地 risk_rule 表）。

    返回值：
        list[EvalCaseResult]：评测结果列表。

    异常：
        不抛出（scan 自身全捕获；其余单条异常内部消化为 error 结果）。
    """
    results: list[EvalCaseResult] = []
    for case in cases:
        start = time.perf_counter()
        try:
            verdict = engine.scan("input", case.text)
            blocked = bool(verdict.block)
            results.append(
                EvalCaseResult(
                    case_id=case.id,
                    dataset=case.dataset,
                    expected_blocked=case.expected_blocked,
                    passed=blocked == case.expected_blocked,
                    latency_ms=round((time.perf_counter() - start) * 1000, 3),
                    blocked=blocked,
                    status=verdict.status,
                )
            )
        except Exception as exc:  # noqa: BLE001 —— 单条失败不中断评测
            results.append(
                EvalCaseResult(
                    case_id=case.id,
                    dataset=case.dataset,
                    expected_blocked=case.expected_blocked,
                    error=f"{type(exc).__name__}: {exc}",
                    latency_ms=round((time.perf_counter() - start) * 1000, 3),
                )
            )
    return results


def eval_retrieval(cases: list[EvalCase]) -> tuple[list[EvalCaseResult], list[str]]:
    """执行检索命中评测（函数）。

    说明：
        对每条 query 调用 retrieve_candidates(session, [], query) 取 Top-8 候选标题，
        逐条计算 Hit@3 / Hit@5 / Recall@5 / MRR；Recall@5 的相关集合基于全库
        已发布菜谱标题（一次性查询复用）。数据库不可达时返回空结果列表与
        失败原因，由调用方标注 unavailable。

    参数：
        cases：检索评测用例列表。

    返回值：
        tuple[list[EvalCaseResult], list[str]]：(评测结果列表, 失败原因列表)。

    异常：
        不抛出（连接/查询异常内部消化为空结果 + 失败原因）。
    """
    results: list[EvalCaseResult] = []
    errors: list[str] = []
    try:
        with SessionLocal() as session:
            all_titles = [str(t) for t in session.execute(select(Recipe.title).where(Recipe.status == "published")).scalars().all()]
            for case in cases:
                start = time.perf_counter()
                try:
                    candidates = retrieve_candidates(session, [], case.text)
                    titles = [str(c.get("title") or "") for c in candidates]
                    result = EvalCaseResult(
                        case_id=case.id,
                        dataset=case.dataset,
                        expected_keywords=case.expected_keywords,
                        latency_ms=round((time.perf_counter() - start) * 1000, 3),
                        titles=titles,
                    )
                    if not titles:
                        result.error = "检索无候选返回"
                    else:
                        kws = case.expected_keywords or []
                        result.hit_at_3 = hit_at_k(titles, kws, 3)
                        result.hit_at_5 = hit_at_k(titles, kws, 5)
                        result.recall_at_5 = round(recall_at_k(titles, kws, all_titles, 5), 4)
                        result.mrr = round(mrr(titles, kws), 4)
                        result.passed = bool(result.hit_at_5)
                    results.append(result)
                except Exception as exc:  # noqa: BLE001 —— 单条失败不中断评测
                    results.append(
                        EvalCaseResult(
                            case_id=case.id,
                            dataset=case.dataset,
                            expected_keywords=case.expected_keywords,
                            error=f"{type(exc).__name__}: {exc}",
                            latency_ms=round((time.perf_counter() - start) * 1000, 3),
                        )
                    )
    except Exception as exc:  # noqa: BLE001 —— 数据库不可达整体降级为 unavailable
        errors.append(f"数据库不可达，检索评测跳过: {type(exc).__name__}: {exc}")
    return results, errors


# ---------------------------------------------------------------------------
# 指标汇总与报告输出
# ---------------------------------------------------------------------------
def summarize(report: EvalReport) -> None:
    """汇总各数据集指标并写入 report.metrics / report.notes（函数）。

    说明：
        - intent：准确率（passed 比例）+ P50/P95 延迟；
        - safety：高危拦截召回率 + 误拦截率 + UNKNOWN 判定数 + P50/P95 延迟
          （UNKNOWN 按未拦截计入，D9 保守拦截语义的如实反映）；
        - retrieval：Hit@3 / Hit@5 / Recall@5 / MRR + P50/P95 延迟；
          无有效结果时指标为 None 并写 notes 标注 unavailable；
        - citations / token_cost：当前链路无可靠来源，固定 unavailable 并注明原因。

    参数：
        report：待汇总的评测报告（原地修改 metrics / notes）。

    返回值：
        None。

    异常：
        不抛出（分数据集各自兜底）。
    """
    by_dataset: dict[str, list[EvalCaseResult]] = {}
    for r in report.results:
        by_dataset.setdefault(r.dataset, []).append(r)

    def _latencies(items: list[EvalCaseResult]) -> list[float]:
        """提取有效用例的耗时列表（内部函数）。

        参数：
            items：用例结果列表。

        返回值：
            list[float]：耗时（毫秒）列表。

        异常：
            无。
        """
        return [r.latency_ms for r in items if r.error is None]

    # ---- 意图 ----
    intent_items = by_dataset.get("intent", [])
    valid_i = [r for r in intent_items if r.passed is not None]
    report.metrics["intent"] = {
        "accuracy": round(sum(1 for r in valid_i if r.passed) / len(valid_i), 4) if valid_i else None,
        "cases": len(intent_items),
        "errors": sum(1 for r in intent_items if r.error),
        "latency_p50_ms": round(percentile(_latencies(intent_items), 50), 3),
        "latency_p95_ms": round(percentile(_latencies(intent_items), 95), 3),
    }

    # ---- 风控 ----
    safety_items = by_dataset.get("safety", [])
    executed = [r for r in safety_items if r.blocked is not None]
    if executed:
        blocked_flags = [bool(r.blocked) for r in executed]
        expected_flags = [bool(r.expected_blocked) for r in executed]
        report.metrics["safety"] = {
            "block_recall": round(block_recall(blocked_flags, expected_flags), 4),
            "false_block_rate": round(false_block_rate(blocked_flags, expected_flags), 4),
            "cases": len(safety_items),
            "errors": sum(1 for r in safety_items if r.error),
            "unknown_status": sum(1 for r in executed if r.status == "UNKNOWN"),
            "latency_p50_ms": round(percentile(_latencies(safety_items), 50), 3),
            "latency_p95_ms": round(percentile(_latencies(safety_items), 95), 3),
        }
    else:
        report.metrics["safety"] = {"block_recall": None, "false_block_rate": None, "cases": len(safety_items)}
        report.notes.append("safety 指标 unavailable：无有效执行结果")

    # ---- 检索 ----
    retrieval_items = by_dataset.get("retrieval", [])
    valid_r = [r for r in retrieval_items if r.hit_at_5 is not None]
    if valid_r:
        report.metrics["retrieval"] = {
            "hit_at_3": round(sum(1 for r in valid_r if r.hit_at_3) / len(valid_r), 4),
            "hit_at_5": round(sum(1 for r in valid_r if r.hit_at_5) / len(valid_r), 4),
            "recall_at_5": round(sum(r.recall_at_5 or 0.0 for r in valid_r) / len(valid_r), 4),
            "mrr": round(sum(r.mrr or 0.0 for r in valid_r) / len(valid_r), 4),
            "cases": len(retrieval_items),
            "errors": sum(1 for r in retrieval_items if r.error),
            "latency_p50_ms": round(percentile(_latencies(retrieval_items), 50), 3),
            "latency_p95_ms": round(percentile(_latencies(retrieval_items), 95), 3),
        }
    elif "retrieval" not in report.metrics:
        report.metrics["retrieval"] = {
            "hit_at_3": None,
            "hit_at_5": None,
            "recall_at_5": None,
            "mrr": None,
            "cases": len(retrieval_items),
            "errors": sum(1 for r in retrieval_items if r.error),
        }
        report.notes.append("retrieval 指标 unavailable：数据库不可达或无候选结果，未产出有效检索评测")

    # ---- 引用覆盖率与 Token/费用：当前链路无可靠来源，诚实标注 ----
    report.metrics["citations"] = {"coverage": None}
    report.metrics["token_cost"] = {"total_tokens": None, "total_cost_cents": None}
    for note in (UNAVAILABLE_NOTE_CITATIONS, UNAVAILABLE_NOTE_TOKEN):
        if note not in report.notes:
            report.notes.append(note)


def write_reports(report: EvalReport, output_dir: Path, prefix: str) -> tuple[Path, Path]:
    """写出 JSON 报告与 Markdown 摘要（函数）。

    说明：
        JSON 报告含全部用例明细（期望值冗余记录，自包含可审计）与顶层 gate
        门禁段；Markdown 摘要为各数据集指标表 + 回归门禁表 + unavailable 标注；
        输出目录不存在时自动创建。

    参数：
        report：评测报告（metrics 已汇总、gate 已判定）。
        output_dir：报告输出目录。
        prefix：文件名前缀（"report_" 或 "baseline_"）。

    返回值：
        tuple[Path, Path]：(JSON 报告路径, Markdown 摘要路径)。

    异常：
        OSError：目录/文件写入失败时向上抛出。
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / f"{prefix}{report.file_stamp}.json"
    md_path = json_path.with_suffix(".md")

    report_obj = {
        "generated_at": report.generated_at,
        "metrics": report.metrics,
        "notes": report.notes,
        "results": [asdict(r) for r in report.results],
        "gate": report.gate,
    }
    json_path.write_text(json.dumps(report_obj, ensure_ascii=False, indent=2), encoding="utf-8")

    lines: list[str] = [
        f"# Agent Eval 报告（{report.generated_at}）",
        "",
        "| 数据集 | 指标 | 值 |",
        "| --- | --- | --- |",
    ]
    label_map = {
        "accuracy": "意图准确率",
        "block_recall": "高危拦截召回率",
        "false_block_rate": "误拦截率",
        "hit_at_3": "检索 Hit@3",
        "hit_at_5": "检索 Hit@5",
        "recall_at_5": "检索 Recall@5",
        "mrr": "检索 MRR",
        "cases": "用例数",
        "errors": "异常用例数",
        "unknown_status": "UNKNOWN 判定数",
        "latency_p50_ms": "延迟 P50 (ms)",
        "latency_p95_ms": "延迟 P95 (ms)",
        "coverage": "引用覆盖率",
        "total_tokens": "Token 总数",
        "total_cost_cents": "费用 (cents)",
    }
    for dataset, metrics in report.metrics.items():
        for key, value in metrics.items():
            display = "unavailable" if value is None else value
            lines.append(f"| {dataset} | {label_map.get(key, key)} | {display} |")
    # ---- 回归门禁段（gate 未判定时省略）----
    if report.gate:
        lines += ["", "## 回归门禁"]
        if report.gate.get("enabled"):
            lines.append(f"- 结果：**{report.gate.get('result')}**")
            lines += ["", "| 指标 | 阈值 | 实际值 | 状态 |", "| --- | --- | --- | --- |"]
            thresholds = report.gate.get("thresholds", {})
            actual = report.gate.get("actual", {})
            statuses = report.gate.get("statuses", {})
            for metric, threshold in thresholds.items():  # type: ignore[union-attr]
                actual_display = actual.get(metric)  # type: ignore[union-attr]
                display = "unavailable" if actual_display is None else actual_display
                lines.append(f"| {metric} | {threshold} | {display} | {statuses.get(metric, 'unknown')} |")  # type: ignore[union-attr]
            failed_ids = report.gate.get("failed_case_ids") or []
            lines.append(f"- 失败用例：{', '.join(failed_ids) if failed_ids else '无'}")
        else:
            lines.append("- 结果：SKIPPED（--no-gate 关闭门禁）")
    if report.notes:
        lines += ["", "## 说明"]
        lines += [f"- {n}" for n in report.notes]
    md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return json_path, md_path


# ---------------------------------------------------------------------------
# 回归门禁
# ---------------------------------------------------------------------------
# 门禁默认阈值（下限类指标实际值须 ≥ 阈值；上限类见 GATE_UPPER_METRICS，须 ≤ 阈值）
GATE_DEFAULTS: dict[str, float] = {
    "intent_accuracy": 0.80,
    "block_recall": 1.00,
    "false_block_rate": 0.10,
    "hit_at_3": 0.70,
    "hit_at_5": 0.70,
    "recall_at_5": 0.30,
}
# 上限类指标（实际值 ≤ 阈值才算通过，其余为下限类：实际值 ≥ 阈值）
GATE_UPPER_METRICS: frozenset[str] = frozenset({"false_block_rate"})
# 检索类指标（--offline 未执行时标注 skipped，不触发 FAIL）
GATE_RETRIEVAL_METRICS: frozenset[str] = frozenset({"hit_at_3", "hit_at_5", "recall_at_5"})
# 门禁指标 → 所属数据集维度（用于「用例失败 → 维度 fail」的归因）
GATE_METRIC_DATASETS: dict[str, str] = {
    "intent_accuracy": "intent",
    "block_recall": "safety",
    "false_block_rate": "safety",
    "hit_at_3": "retrieval",
    "hit_at_5": "retrieval",
    "recall_at_5": "retrieval",
}


def load_gate_thresholds(gate_file: str | None) -> dict[str, float]:
    """加载门禁阈值：默认值 + 可选 JSON 文件覆盖（函数）。

    说明：
        --gate-file 指向 JSON 对象（键为指标名、值为数值阈值），与
        GATE_DEFAULTS 浅合并；仅接受已知指标名，防止拼写错误静默失效。

    参数：
        gate_file：阈值覆盖 JSON 文件路径（None 时仅用默认阈值）。

    返回值：
        dict[str, float]：合并后的门禁阈值表。

    异常：
        ValueError：文件不存在、JSON 非法、非对象、含未知指标名或阈值非数值。
    """
    thresholds = dict(GATE_DEFAULTS)
    if not gate_file:
        return thresholds
    path = Path(gate_file)
    if not path.exists():
        raise ValueError(f"门禁阈值文件不存在: {path}")
    overrides = json.loads(path.read_text(encoding="utf-8"))  # JSONDecodeError 是 ValueError 子类
    if not isinstance(overrides, dict):
        raise ValueError("门禁阈值文件内容必须是 JSON 对象")
    unknown = sorted(set(overrides) - set(GATE_DEFAULTS))
    if unknown:
        raise ValueError(f"门禁阈值文件含未知指标: {unknown}")
    for key, value in overrides.items():
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ValueError(f"门禁指标 {key} 的阈值必须为数值，收到: {value!r}")
        thresholds[key] = float(value)
    return thresholds


def evaluate_gate(report: EvalReport, thresholds: dict[str, float], offline: bool) -> dict[str, object]:
    """执行回归门禁判定（函数）。

    说明：
        - 实际值取自 report.metrics（intent.accuracy / safety.block_recall /
          safety.false_block_rate / retrieval.hit_at_3 / hit_at_5 / recall_at_5）；
        - 每指标状态 ∈ {pass, fail, skipped}：skipped 仅限 --offline 未执行的
          检索类指标；指标值缺失（非 offline 跳过）一律 fail；
        - 任一维度存在执行失败用例（passed=False 或 error 非空）时，该维度的
          全部门禁指标判 fail，用例 ID 汇入 failed_case_ids（单条回归也拦截，
          如高危样本漏拦、用例异常）；
        - result：任一指标 fail 即 FAIL，否则 PASS（skipped 不影响）。

    参数：
        report：已汇总 metrics 的评测报告。
        thresholds：门禁阈值（指标名 → 阈值）。
        offline：是否 --offline 模式（检索评测未执行）。

    返回值：
        dict[str, object]：gate 段（enabled/thresholds/actual/statuses/
        failed_case_ids/result）。

    异常：
        不抛出（metrics 缺键按 None 处理）。
    """
    actual: dict[str, float | None] = {
        "intent_accuracy": report.metrics.get("intent", {}).get("accuracy"),
        "block_recall": report.metrics.get("safety", {}).get("block_recall"),
        "false_block_rate": report.metrics.get("safety", {}).get("false_block_rate"),
        "hit_at_3": report.metrics.get("retrieval", {}).get("hit_at_3"),
        "hit_at_5": report.metrics.get("retrieval", {}).get("hit_at_5"),
        "recall_at_5": report.metrics.get("retrieval", {}).get("recall_at_5"),
    }
    failed_case_ids = [r.case_id for r in report.results if r.passed is False or r.error is not None]
    failed_datasets = {r.dataset for r in report.results if r.passed is False or r.error is not None}

    statuses: dict[str, str] = {}
    for metric, threshold in thresholds.items():
        value = actual.get(metric)
        if value is None:
            # skipped 仅限 --offline 未执行的检索类指标；其余指标缺失一律 fail
            statuses[metric] = "skipped" if (offline and metric in GATE_RETRIEVAL_METRICS) else "fail"
            continue
        if GATE_METRIC_DATASETS.get(metric) in failed_datasets:
            statuses[metric] = "fail"
            continue
        if metric in GATE_UPPER_METRICS:
            statuses[metric] = "pass" if value <= threshold else "fail"
        else:
            statuses[metric] = "pass" if value >= threshold else "fail"
    result = "FAIL" if "fail" in statuses.values() else "PASS"
    return {
        "enabled": True,
        "thresholds": dict(thresholds),
        "actual": actual,
        "statuses": statuses,
        "failed_case_ids": failed_case_ids,
        "result": result,
    }


# ---------------------------------------------------------------------------
# CLI 入口
# ---------------------------------------------------------------------------
def build_parser() -> argparse.ArgumentParser:
    """构建命令行参数解析器（函数）。

    返回值：
        argparse.ArgumentParser：解析器实例。

    异常：
        无。
    """
    parser = argparse.ArgumentParser(description="Agent Eval 离线评测框架（意图/风控/检索 + 回归门禁）")
    parser.add_argument("--datasets-dir", default="eval/datasets", help="评测数据集目录（相对或绝对路径）")
    parser.add_argument("--output-dir", default="eval/reports", help="报告输出目录")
    parser.add_argument("--offline", action="store_true", help="跳过依赖数据库的检索评测（标注 unavailable）")
    parser.add_argument("--baseline", action="store_true", help="输出文件名前缀改为 baseline_（保存基线报告）")
    parser.add_argument("--gate-file", default=None, help="门禁阈值覆盖 JSON 文件（键为指标名，与默认阈值合并）")
    parser.add_argument("--no-gate", action="store_true", help="关闭回归门禁（退出码恒 0，仅产出报告）")
    return parser


def main(argv: list[str] | None = None) -> int:
    """评测主流程入口（函数）。

    说明：
        加载三个数据集与门禁阈值 → 依次执行意图 / 风控 / 检索评测（--offline
        时检索跳过并标注 unavailable）→ 汇总指标 → 回归门禁判定 → 写出 JSON +
        Markdown 报告（评测流程内任何情况下都落盘，含门禁 FAIL）；数据集或
        阈值加载失败返回退出码 2，单条用例失败不中断评测但会计入门禁。

    参数：
        argv：命令行参数列表（None 时取 sys.argv[1:]）。

    返回值：
        int：进程退出码（0 成功，含门禁通过与 --no-gate；1 门禁启用且 FAIL；
        2 数据集/阈值加载失败）。

    异常：
        不抛出（加载异常转为错误码返回）。
    """
    args = build_parser().parse_args(argv)
    report = EvalReport(generated_at=datetime.now().isoformat(timespec="seconds"), file_stamp=datetime.now().strftime("%Y%m%d_%H%M%S"))

    try:
        cases_intent = load_dataset(Path(args.datasets_dir) / "intent_cases.jsonl", "intent")
        cases_safety = load_dataset(Path(args.datasets_dir) / "safety_cases.jsonl", "safety")
        cases_retrieval = load_dataset(Path(args.datasets_dir) / "retrieval_cases.jsonl", "retrieval")
    except ValueError as exc:
        print(f"[eval] 数据集加载失败: {exc}", file=sys.stderr)
        return 2

    try:
        thresholds = load_gate_thresholds(args.gate_file)
    except ValueError as exc:
        print(f"[eval] 门禁阈值加载失败: {exc}", file=sys.stderr)
        return 2

    # ---- 意图评测（离线确定性）----
    report.results.extend(eval_intent(cases_intent))
    # ---- 风控评测（连库规则引擎）----
    report.results.extend(eval_safety(cases_safety, RiskEngine()))
    # ---- 检索评测（依赖数据库；--offline 跳过并标注 unavailable）----
    if args.offline:
        report.notes.append(UNAVAILABLE_NOTE_RETRIEVAL_OFFLINE)
    else:
        retrieval_results, retrieval_errors = eval_retrieval(cases_retrieval)
        report.results.extend(retrieval_results)
        report.notes.extend(retrieval_errors)

    summarize(report)
    # ---- 回归门禁判定（--no-gate 关闭：仅记录 SKIPPED，退出码恒 0）----
    if args.no_gate:
        report.gate = {
            "enabled": False,
            "thresholds": {},
            "actual": {},
            "statuses": {},
            "failed_case_ids": [],
            "result": "SKIPPED",
        }
    else:
        report.gate = evaluate_gate(report, thresholds, offline=args.offline)
    json_path, md_path = write_reports(report, Path(args.output_dir), "baseline_" if args.baseline else "report_")
    print(f"[eval] 报告已写出: {json_path}")
    print(f"[eval] 摘要已写出: {md_path}")
    for dataset, metrics in report.metrics.items():
        pairs = ", ".join(f"{k}={v}" for k, v in metrics.items())
        print(f"[eval] {dataset}: {pairs}")
    if report.gate.get("enabled"):
        statuses_text = ", ".join(f"{m}={s}" for m, s in report.gate["statuses"].items())  # type: ignore[union-attr]
        print(f"[eval] 门禁: {report.gate['result']} ({statuses_text})")
        failed_ids = report.gate["failed_case_ids"]  # type: ignore[union-attr]
        if failed_ids:
            print(f"[eval] 失败用例: {', '.join(failed_ids)}", file=sys.stderr)
        if report.gate["result"] == "FAIL":
            print("[eval] 回归门禁未通过，退出码置 1", file=sys.stderr)
            return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
