"""受限问答节点模块。

职责：
    node_free_qa：烹饪相关的受限回答——
    - 系统提示约束：只答烹饪相关、≤5 句、禁止医疗/营养治疗声称/绝对化用语/安全承诺；
    - LLM 失败 → 固定兜底话术「暂时无法生成，请稍后重试。」；
    - 产出 qa_answer 入 state，待 output_guard 出口闸门复核与敏感词二级替换。
"""

from __future__ import annotations

from app.ability import get_llm_client
from app.core.logging import get_logger
from app.graph.nodes.common import make_span, now_ms
from app.graph.registry import register

logger = get_logger(__name__)

# LLM 失败固定兜底话术
QA_FALLBACK_ANSWER = "暂时无法生成，请稍后重试。"

# 受限问答系统提示（合规口径写死，禁止越界表述）
QA_SYSTEM_PROMPT = (
    "你是一个面向家庭用户的烹饪助手。严格遵守以下规则：\n"
    "1. 只回答与买菜、做菜、厨房操作相关的话题；与烹饪无关的问题直接说明无法回答；\n"
    "2. 回答不超过 5 句话，简明实用；\n"
    "3. 禁止任何医疗建议、疾病治疗或「吃什么治病」类内容；禁止营养治疗声称；\n"
    "4. 禁止绝对化用语（最好的/第一/唯一）与安全承诺（绝对安全/保证不过敏）；\n"
    "5. 不确定的内容明确说不确定，不得编造。"
)


def make_node_free_qa():
    """受限问答节点工厂（函数）。

    返回值：
        Callable：节点函数。

    异常：
        无。
    """

    def node_free_qa(state: dict) -> dict:
        """受限问答节点（函数）。

        说明：
            LLM 成功 → qa_answer = 模型回答（status=ok）；
            任何异常（LLMError/网络/超时/解析）→ 固定兜底话术（status=degraded）。

        参数：
            state：编排状态。

        返回值：
            dict：{"qa_answer": 回答文本, "qa_degraded": 是否降级兜底,
            "trace": [span]}（qa_degraded 供 compose 组装 citations 降级标注）。

        异常：
            不抛出（全部异常转兜底话术）。
        """
        start = now_ms()
        answer = QA_FALLBACK_ANSWER
        status = "degraded"
        model_name: str | None = None
        prompt_tokens = completion_tokens = 0
        cost_cents: float | None = None
        try:
            user_msg = state.get("input_text") or "（用户未输入文本）"
            names = list(state.get("resolved_ingredient_names") or [])
            if names:
                user_msg += "\n（用户已选食材：" + "、".join(names) + "）"
            # 阶段二：tool_loop 产出的工具结果摘要只作为回答素材注入（空列表时不追加）
            tool_results = [r for r in (state.get("tool_results") or []) if isinstance(r, dict)]
            if tool_results:
                facts = "; ".join(f"{r.get('tool')}={r.get('summary')}" for r in tool_results[:5])
                user_msg += "\n（工具参考数据：" + facts[:800] + "）"
            client = get_llm_client()
            result = client.chat(QA_SYSTEM_PROMPT, user_msg, temperature=0.2)
            if result.content:
                answer = result.content
            model_name = result.model
            prompt_tokens = result.prompt_tokens
            completion_tokens = result.completion_tokens
            cost_cents = result.cost_cents
            status = "ok"
        except Exception as exc:  # noqa: BLE001 —— LLMError 等一切失败走固定兜底话术
            logger.warning("node_free_qa fallback: %s", exc)

        span = make_span(
            "node_free_qa",
            status,
            now_ms() - start,
            model_name=model_name,
            prompt_tokens=prompt_tokens or None,
            completion_tokens=completion_tokens or None,
            cost_cents=cost_cents,
        )
        return {"qa_answer": answer, "qa_degraded": status == "degraded", "trace": [span]}

    return node_free_qa


# ---- 注册 ----
register("node_free_qa", make_node_free_qa, forms="llm", timeout_ms=5000, description="受限问答（≤5 句 + 合规约束 + 失败兜底）")
