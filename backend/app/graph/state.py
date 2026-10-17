"""LangGraph 编排状态定义模块。

职责：
    定义主图与推荐子图共享的 CookingState（TypedDict, total=False）。
    🔴 trace 字段使用 Annotated[list[dict], operator.add] reducer：
    并行节点（recipe_rank ∥ node_nutrition）的 trace span 依赖它正确合并，
    是「Agent 调度可视化面板」消费的数据基础（架构文档 §4.2）。

说明：
    判定/档案等复杂对象统一以 dict 形态入 state（便于跨节点读写与序列化）；
    数据库会话不入 state——各节点自管短会话。
"""

from __future__ import annotations

import operator
from typing import Annotated, TypedDict


class CookingState(TypedDict, total=False):
    """主图/子图共享编排状态（模型类）。

    字段：
        request_id：请求唯一标识（幂等键）。
        trace_id：调度面板 trace 标识。
        user_id_hash：用户标识哈希（脱敏，sha256 前 12 位）。
        intent：supervisor 识别的意图（8 类枚举）。
        input_text：用户原始输入文本。
        ingredients：用户输入的食材（名称字符串列表或 {ingredient_id} 字典列表）。
        safety_profile：用户安全档案（SafetyProfile.model_dump() 字典）。
        input_verdict：入口闸门判定（RiskVerdict dict）。
        output_verdict：出口闸门判定（RiskVerdict dict）。
        safe_mode：保守模式标记。
        resolved_ingredient_ids：assemble_context 解析出的食材 ID 列表。
        resolved_ingredient_names：解析出的食材名列表（供排序理由）。
        candidates：召回候选列表（retrieve_candidates 输出）。
        filtered_candidates：硬过滤后的候选列表。
        filtered_by：硬过滤计数 {"allergen": n, "dietary_restriction": n, "difficulty": n}。
        results：排序后三档结果列表（含 rank_reasons/match_level）。
        nutrition：{recipe_id: 营养估算结果 dict}。
        qa_answer：受限问答文本（node_free_qa 产出，待出口闸门复核）。
        partial_failures：部分失败说明列表（降级标注）。
        notice：面向用户的附加提示（如结果不足）。
        response：最终响应 dict（finalize/终止节点产出）。
        trace：trace span 列表（operator.add 累加合并，落库 agent_trace）。
        tool_results：工具循环节点（tool_loop）产出摘要列表
            （operator.add 累加，与 trace 同风格；条目含 tool/status/summary）。
        tool_loop_limit_hit：工具循环触限标记（达轮数上限/超预算时为 True）。
    """

    # 请求元信息
    request_id: str
    trace_id: str
    user_id_hash: str
    user_id: int
    intent: str
    input_text: str
    ingredients: list

    # 安全域
    safety_profile: dict
    input_verdict: dict
    output_verdict: dict
    safe_mode: bool

    # 业务数据
    resolved_ingredient_ids: list
    resolved_ingredient_names: list
    candidates: list
    filtered_candidates: list
    filtered_by: dict
    results: list
    nutrition: dict
    qa_answer: str
    partial_failures: list
    notice: str
    tool_results: Annotated[list[dict], operator.add]
    tool_loop_limit_hit: bool

    # 响应与可观测
    response: dict
    trace: Annotated[list[dict], operator.add]
