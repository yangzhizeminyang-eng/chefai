"""compose 汇总节点模块。

职责：
    三档 results 组装（✅现在就能做 / 🛒差1–2样 / 💡需要多买几样，由 match_level 承载）、
    营养结果合并（calories_kcal 用每份估算值 + excluded_items 透传）、
    disclaimer_id="DISCLAIMER_V1" 固定附着、降级/部分失败标注（partial_failures）、
    结果不足 8 条时的 notice 提示。

输出：
    响应草稿写入 state["response"]（trace_id 由 finalize/终止节点补齐），
    随后进入 output_guard 出口闸门。
"""

from __future__ import annotations

from app.ability.ranking import TOP_N
from app.core.logging import get_logger
from app.graph.nodes.common import DISCLAIMER_ID, make_span, now_ms
from app.graph.registry import register

logger = get_logger(__name__)


def make_compose():
    """compose 节点工厂（函数）。

    返回值：
        Callable：节点函数。

    异常：
        无。
    """

    def compose(state: dict) -> dict:
        """汇总组装节点（函数）。

        说明：
            - 营养合并：nutrition 字典命中 → results 条目追加 nutrition 摘要并覆盖
              calories_kcal 为每份估算值；未命中 → 保留 DB 静态值并标注「营养数据暂不可用」；
            - 复合意图（M.3）：intent=composite_recommend_nutrition 时响应标注
              mode='composite'，附营养汇总说明 nutrition_summary；营养缺失项存在时
              追加 conflict_notes 口径差异标注（M.4，固定检查逻辑）；span 记
              dispatch_mode='composite'（调度面板可见）；
            - 推荐与问答互斥分支可同时缺省（空结果 + 无回答）时给 notice 兜底。

        参数：
            state：编排状态（intent / results / nutrition / qa_answer / partial_failures）。

        返回值：
            dict：{"response": 响应草稿, "results": 更新后的结果列表, "notice": 提示,
            "trace": [span]}。

        异常：
            不抛出（单条合并异常跳过）。
        """
        start = now_ms()
        results = list(state.get("results") or [])
        nutrition_map = state.get("nutrition") or {}
        partial_failures = list(state.get("partial_failures") or [])
        notice = state.get("notice") or ""
        is_composite = (state.get("intent") or "") == "composite_recommend_nutrition"

        # 合并营养结果到结果条目（并行节点产出按 recipe_id 归并）
        for item in results:
            try:
                nutrition = nutrition_map.get(item.get("recipe_id"))
                if nutrition:
                    item["calories_kcal"] = nutrition.get("per_serving", {}).get("kcal", item.get("calories_kcal"))
                    item["nutrition"] = {
                        "per_serving": nutrition.get("per_serving"),
                        "estimate_note": nutrition.get("estimate_note"),
                        "excluded_items": nutrition.get("excluded_items") or [],
                    }
                else:
                    item["nutrition"] = None
                    # 🔴 每份口径（M5 收口）：营养估算未命中时，DB calories_kcal 为全菜总量
                    # 语义，不能直接当每份展示 —— 按菜谱基准份数折算（retrieval 透传的
                    # 原始值缺份数信息，此处从结果条目 servings（缺省 2）折算）。
                    base = item.get("servings") or 2
                    raw_kcal = item.get("calories_kcal")
                    if isinstance(raw_kcal, (int, float)) and raw_kcal and base >= 1:
                        item["calories_kcal"] = round(float(raw_kcal) / base, 1)
            except Exception as exc:  # noqa: BLE001 —— 单条合并失败不影响整体
                logger.warning("compose merge nutrition failed: %s", exc)

        # 推荐结果条数不足（未填充占位，如实说明）
        if results and len(results) < TOP_N and not notice:
            notice = "现有食材能做的菜较少，建议补充后再试"
        if not results and not state.get("qa_answer"):
            notice = "暂未找到匹配的菜谱，建议补充食材后再试"

        response: dict = {
            "request_id": state.get("request_id"),
            "safe_mode": False,
            "disclaimer_id": DISCLAIMER_ID,
            "trace_id": state.get("trace_id"),
        }
        if results:
            response["results"] = results
            response["filtered_by"] = state.get("filtered_by") or {
                "allergen": 0,
                "dietary_restriction": 0,
                "difficulty": 0,
                "equipment": 0,
            }
        if state.get("qa_answer"):
            response["qa_answer"] = state["qa_answer"]
        if notice:
            response["notice"] = notice
        if partial_failures:
            response["partial_failures"] = partial_failures

        # 复合意图（M.3/M.4）：mode 标注 + 营养汇总说明 + 口径差异标注（固定检查逻辑）
        if is_composite:
            response["mode"] = "composite"
            if any(item.get("nutrition") for item in results):
                response["nutrition_summary"] = (
                    "已同步为你估算推荐菜品的营养：每份热量见各结果条目的 calories_kcal（估算值）。"
                )
            else:
                response["nutrition_summary"] = "本次推荐暂无可估算的营养数据。"
            missing_nutrition = sum(1 for item in results if not item.get("nutrition"))
            if missing_nutrition:
                response["conflict_notes"] = ["营养数据存在缺失项，仅供参考"]

        span = make_span("compose", "ok", now_ms() - start, dispatch_mode="composite" if is_composite else None)
        return {"response": response, "results": results, "notice": notice, "trace": [span]}

    return compose


# ---- 注册 ----
register("compose", make_compose, forms="rule", timeout_ms=1000, description="三档结果组装 + 免责附着 + 降级标注")
