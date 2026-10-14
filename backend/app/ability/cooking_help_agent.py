"""烹饪求助子智能体模块（混合架构：风控闸门内的回答生成器）。

职责：
    generate_cooking_help(question, context)：结合当前菜谱步骤与用户档案
    （过敏原/口味/厨艺/饮食目标），经主 LLM（DeepSeek）生成 2~3 条可操作
    的针对性帮助。回答仍需通过既有 output 风控闸门（cooking.py）；
    LLM 失败抛 LLMError，由端点回退关键词库/步骤要点模板（绝不阻断求助）。

安全红线：
    🔴 不提供医疗诊断与食安绝对结论（「还能吃吗/变质了吗」类问题引导
    保守处理并查证官方渠道）；回答不出现致敏食材的「试着少吃点」类
    建议——用户档案含过敏原时明确提示规避。
"""

from __future__ import annotations

import json

from app.ability.llm import LLMError, get_llm_client
from app.core.logging import get_logger

logger = get_logger(__name__)

# 求助子智能体 system prompt（结合上下文给可操作建议；安全红线内嵌）
COOKING_HELP_SYSTEM_PROMPT = (
    "你是烹饪导师，正在用户做菜过程中实时答疑。结合给定的当前步骤、菜谱与用户档案，"
    "针对用户的问题给出 2~3 条可操作的建议，只输出一个 JSON 字符串数组（如"
    '["建议一","建议二"]），不要输出解释文字或代码围栏。'
    "要求：建议必须贴合当前步骤的具体动作与火候/时间/调料；结合用户档案（过敏原务必规避、"
    "新手给更细的判断标准、口味偏好影响调味建议）；每条不超过 50 字，口语化。"
    "🔴 禁止提供医疗诊断或食品安全绝对结论：变质/中毒/能否食用类问题一律建议"
    "「不确定时弃用更稳妥，并以官方食品安全渠道为准」，不得替用户判断能吃。"
)


def generate_cooking_help(question: str, context: dict) -> list[str]:
    """生成烹饪求助回答（子智能体，函数）。

    说明：
        上下文由端点层组装（菜谱/当前步骤/用户档案），本函数负责拼装
        prompt、调主 LLM、容错解析 JSON 数组并校验条目（2~3 条、均为
        非空字符串、超长截断）。解析失败抛 LLMError 由端点回退模板。

    参数：
        question：用户求助问题（已过 input 风控闸门）。
        context：上下文字典（recipe_title/current_step_text/family/skill 等）。

    返回值：
        list[str]：2~3 条建议。

    异常：
        LLMError：LLM 调用失败或输出无法解析出合法数组时抛出。
    """
    question = (question or "").strip()
    if not question:
        raise LLMError("求助问题为空")
    user_msg = (
        f"用户的问题：{question}\n"
        f"当前上下文：{json.dumps(context, ensure_ascii=False)}"
    )
    result = get_llm_client().chat(
        system=COOKING_HELP_SYSTEM_PROMPT,
        user=user_msg,
        temperature=0.3,
    )
    answers = _extract_answer_array(result.content)
    if answers is None:
        logger.warning("cooking help agent unparseable: %r", result.content[:200])
        raise LLMError("求助回答解析失败")
    return answers


def _extract_answer_array(raw: str) -> list[str] | None:
    """从 LLM 原始输出容错提取建议数组（独立纯函数，便于单测）。

    说明：
        定位首个 '[' 到末个 ']' 截取，json.loads 失败返回 None；
        逐条转字符串、剔除空白项、每条截断 80 字；有效条目不足 2 条时
        若恰有 1 条也接受（LLM 偶尔只给一条强建议），0 条返回 None。

    参数：
        raw：LLM 输出文本。

    返回值：
        list[str] | None：建议列表（1~3 条）；无法解析返回 None。

    异常：
        不抛出（解析失败返回 None）。
    """
    start = raw.find("[")
    end = raw.rfind("]")
    if start < 0 or end <= start:
        return None
    try:
        data = json.loads(raw[start : end + 1])
    except (json.JSONDecodeError, ValueError):
        return None
    if not isinstance(data, list):
        return None
    answers: list[str] = []
    for item in data[:3]:
        if not isinstance(item, str):
            continue
        cleaned = item.strip()
        if cleaned:
            answers.append(cleaned[:80])
    if not answers:
        return None
    return answers
