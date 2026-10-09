"""闸门与终止节点模块（双侧风控闸门 + 一票否决出口 + 保守模式出口）。

职责：
    - intake_guard：入口闸门（RiskEngine.scan('input')，不调模型）；
    - output_guard：出口闸门（scan('output') 于 compose 汇总文本，再过 sensitive_words.sanitize
      二级替换）；
    - emit_safety_response：一票否决/澄清出口——组装 blocked 响应，为未执行的业务节点补
      not_executed / skipped_by_veto trace，落库 trace 与 risk_log；
    - safe_mode_handler：保守模式出口（TXT-G06 固定话术 + partial 说明）。

拓扑红线：
    一票否决短路先于 compose；不存在绕过闸门直达 END 的路径（由 main_graph 条件边保证，
    并有图结构测试断言）。
"""

from __future__ import annotations

from app.core.db import SessionLocal
from app.core.logging import get_logger
from app.graph.nodes.common import (
    BUSINESS_NODE_NAMES,
    DISCLAIMER_ID,
    TXT_G06,
    make_span,
    now_ms,
    persist_trace,
)
from app.graph.registry import register
from app.safety import (
    UNKNOWN_VERDICT,
    SafetyProfile,
    get_risk_engine,
    sanitize,
    write_risk_log,
)

logger = get_logger(__name__)


def make_intake_guard():
    """入口闸门节点工厂（函数）。

    说明：
        扫描文本 = 用户输入文本 + 食材名拼接（食材名本身也可能是高危词载体）；
        RiskEngine.scan 全捕获，任何异常返回 UNKNOWN → 条件边路由保守模式。

    参数：
        无（工厂模式）。

    返回值：
        Callable：节点函数（state → state 更新 dict）。

    异常：
        无（节点内部逻辑由 scan 全捕获兜底）。
    """

    def intake_guard(state: dict) -> dict:
        """入口闸门节点（函数）。

        参数：
            state：编排状态。

        返回值：
            dict：{"input_verdict": RiskVerdict dict, "trace": [span]}。

        异常：
            不抛出（scan 内部全捕获）。
        """
        start = now_ms()
        engine = get_risk_engine()
        ctx = SafetyProfile(**(state.get("safety_profile") or {}))
        # 待扫文本 = 输入文本 + 食材名（食材名同样可能构成高危语义，如「发芽土豆」）
        parts = [state.get("input_text") or ""]
        for item in state.get("ingredients") or []:
            if isinstance(item, str):
                parts.append(item)
            elif isinstance(item, dict):
                parts.append(str(item.get("name") or ""))
        text = " ".join(p for p in parts if p)
        verdict = engine.scan("input", text, ctx)
        span = make_span(
            "intake_guard", "ok", now_ms() - start, rule_hit=verdict.rule_code
        )
        return {"input_verdict": verdict.model_dump(), "trace": [span]}

    return intake_guard


def make_output_guard():
    """出口闸门节点工厂（函数）。

    说明：
        扫描对象 = compose 汇总文本（全部菜名 + rank_reasons + qa_answer）；
        DB 输出规则命中即整体阻断；敏感词二级替换对 qa_answer 生效（results 为 DB 受控内容，
        违规仅记录到 notice 提示）。

    参数：
        无。

    返回值：
        Callable：节点函数。

    异常：
        无（scan/sanitize 均不抛出）。
    """

    def output_guard(state: dict) -> dict:
        """出口闸门节点（函数）。

        参数：
            state：编排状态（compose 已产出 response）。

        返回值：
            dict：{"output_verdict": dict, "qa_answer": 替换后文本（如有违规）,
            "notice": 修正提示（如有违规）, "trace": [span]}。

        异常：
            不抛出。
        """
        start = now_ms()
        engine = get_risk_engine()
        ctx = SafetyProfile(**(state.get("safety_profile") or {}))
        # 汇总文本：菜名 + rank_reasons + qa_answer（覆盖自由生成内容的主要来源）
        parts: list[str] = []
        for item in state.get("results") or []:
            if isinstance(item, dict):
                parts.append(str(item.get("title") or ""))
                parts.extend(str(r) for r in (item.get("rank_reasons") or []))
        if state.get("qa_answer"):
            parts.append(str(state["qa_answer"]))
        text = " ".join(p for p in parts if p)
        verdict = engine.scan("output", text, ctx)
        update: dict = {
            "output_verdict": verdict.model_dump(),
            "trace": [make_span("output_guard", "ok", now_ms() - start, rule_hit=verdict.rule_code)],
        }
        # 二级保险：敏感词替换（DB OB 规则命中在先已阻断；此处兜底词表未覆盖变体）
        _, violations = sanitize(text)
        if violations:
            qa = state.get("qa_answer")
            if qa:
                clean_qa, _ = sanitize(qa)
                update["qa_answer"] = clean_qa
            update["notice"] = "部分输出表述已按合规口径自动修正。"
        return update

    return output_guard


def make_emit_safety_response():
    """一票否决/澄清出口节点工厂（函数）。

    说明：
        响应结构对齐架构文档 §9.2 否决示例：仅 request_id/blocked/overrides_all/risk/
        disclaimer_id/trace_id，🔴 绝不含 results/candidates/nutrition；
        伪科学类（block=false）同样经此出口返回科普澄清话术，但 blocked=false；
        为 trace 中缺失的业务节点补 not_executed（入口否决）/ skipped_by_veto（finalize）。

    参数：
        无。

    返回值：
        Callable：节点函数。

    异常：
        不抛出（话术缺失/落库失败均兜底为默认文案或告警）。
    """

    def emit_safety_response(state: dict) -> dict:
        """一票否决/澄清出口节点（函数）。

        参数：
            state：编排状态。

        返回值：
            dict：{"response": blocked 响应 dict, "trace": [补标 span + 自身 span]}。

        异常：
            不抛出。
        """
        start = now_ms()
        iv = state.get("input_verdict") or {}
        ov = state.get("output_verdict") or {}
        # 出口否决优先（output_guard 命中阻断后路由至此），否则为入口否决/澄清
        if ov.get("hit"):
            verdict = ov
            stage = "output"
        elif iv.get("hit"):
            verdict = iv
            stage = "input"
        else:
            # 不应发生（路由保证），兜底按 UNKNOWN 处理
            verdict = dict(UNKNOWN_VERDICT)
            stage = "input"

        blocked = bool(verdict.get("block"))
        overrides_all = bool(verdict.get("overrides_all"))
        engine = get_risk_engine()
        msg = engine.get_message(verdict.get("message_id"))
        risk = {
            "category": verdict.get("category"),
            "rule_code": verdict.get("rule_code"),
            "risk_level": verdict.get("risk_level"),
            "message_id": verdict.get("message_id"),
            "title": (msg or {}).get("title"),
            "body": (msg or {}).get("body") or "该请求未生成任何内容。",
            "correct_action": (msg or {}).get("correct_action"),
            "after_consumption_advice": (msg or {}).get("after_consumption_advice"),
            "evidence_ref": verdict.get("evidence_ref") or [],
        }
        response = {
            "request_id": state.get("request_id"),
            "blocked": blocked,
            "overrides_all": overrides_all,
            "risk": risk,
            "disclaimer_id": DISCLAIMER_ID,
            "trace_id": state.get("trace_id"),
        }

        # 业务节点清单标注：入口否决 → 业务节点均未执行；出口否决 → 业务节点已执行（保留原 span）
        seen = {s.get("node_name") for s in (state.get("trace") or [])}
        extra: list[dict] = []
        for name in BUSINESS_NODE_NAMES:
            if name not in seen:
                extra.append(make_span(name, "not_executed", None))
        if "output_guard" not in seen:
            extra.append(make_span("output_guard", "skipped_by_veto", None))
        extra.append(make_span("finalize", "skipped_by_veto", None))
        own = make_span("emit_safety_response", "ok", now_ms() - start, rule_hit=verdict.get("rule_code"))

        # trace 与 risk_log 落库（失败仅告警）
        persist_trace(state, extra + [own])
        try:
            with SessionLocal() as session:
                write_risk_log(
                    session,
                    state.get("request_id") or "unknown",
                    stage,
                    verdict,
                    state.get("input_text") or "",
                    "blocked",
                )
        except Exception as exc:  # noqa: BLE001
            logger.error("emit_safety_response risk_log failed: %s", exc)

        return {"response": response, "trace": extra + [own]}

    return emit_safety_response


def make_safe_mode_handler():
    """保守模式出口节点工厂（函数）。

    说明：
        风控 UNKNOWN（异常/超时）时的唯一出口：TXT-G06 固定话术 + partial 说明；
        绝不在风控不可用时直连模型或执行业务链（spec D9 红线）。

    参数：
        无。

    返回值：
        Callable：节点函数。

    异常：
        不抛出。
    """

    def safe_mode_handler(state: dict) -> dict:
        """保守模式出口节点（函数）。

        参数：
            state：编排状态。

        返回值：
            dict：{"response": 保守模式响应 dict, "trace": [补标 span + 自身 span]}。

        异常：
            不抛出。
        """
        start = now_ms()
        verdict = state.get("input_verdict") or state.get("output_verdict") or dict(UNKNOWN_VERDICT)
        response = {
            "request_id": state.get("request_id"),
            "safe_mode": True,
            "message": TXT_G06,
            "detail": "本次请求未生成任何业务内容，已按最保守策略处理，请稍后重试。",
            "disclaimer_id": DISCLAIMER_ID,
            "trace_id": state.get("trace_id"),
        }
        # 未执行的节点补标（业务节点与 finalize 均未执行）
        seen = {s.get("node_name") for s in (state.get("trace") or [])}
        extra: list[dict] = []
        for name in BUSINESS_NODE_NAMES:
            if name not in seen:
                extra.append(make_span(name, "not_executed", None))
        if "output_guard" not in seen:
            extra.append(make_span("output_guard", "not_executed", None))
        extra.append(make_span("finalize", "not_executed", None))
        own = make_span("safe_mode_handler", "ok", now_ms() - start)

        persist_trace(state, extra + [own])
        try:
            with SessionLocal() as session:
                write_risk_log(
                    session,
                    state.get("request_id") or "unknown",
                    "input",
                    verdict,
                    state.get("input_text") or "",
                    "safe_mode",
                )
        except Exception as exc:  # noqa: BLE001
            logger.error("safe_mode_handler risk_log failed: %s", exc)

        return {"response": response, "trace": extra + [own]}

    return safe_mode_handler


# ---- 注册（NFR-4.1：主图装配按注册表动态 add_node）----
register("intake_guard", make_intake_guard, forms="rule", timeout_ms=500, description="入口闸门：纯规则输入扫描")
register("output_guard", make_output_guard, forms="rule", timeout_ms=500, description="出口闸门：输出扫描 + 敏感词二级替换")
register("emit_safety_response", make_emit_safety_response, forms="rule", timeout_ms=500, description="一票否决/澄清出口")
register("safe_mode_handler", make_safe_mode_handler, forms="rule", timeout_ms=500, description="保守模式出口（TXT-G06）")
