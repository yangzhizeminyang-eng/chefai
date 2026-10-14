"""语音意图理解模块（混合架构：白名单未命中时的 LLM 兜底解析）。

职责：
    parse_voice_intent(text, context)：把白名单未命中的转写文本交给主 LLM
    （DeepSeek，OpenAI 兼容 chat）做意图解析，输出结构化指令 JSON：
    {action, minutes, step_no, question, reply}。
    action 枚举与前端语音白名单指令一一对应（外加 none）；
    解析失败 / 开关关闭 / 超时统一抛 LLMError 或返回 none（由路由层降级），
    绝不阻断语音主链路（白名单高频指令完全不经过本模块）。

安全：
    用户转写文本仅作为 user 消息内容；输出强制 JSON 且 action 枚举校验，
    无工具执行、无 SQL/命令拼接面；烹饪求助类 question 仍走既有求助风控。
"""

from __future__ import annotations

import json

from app.ability.llm import LLMError, get_llm_client
from app.core.logging import get_logger

logger = get_logger(__name__)

# action 枚举（烹饪页指令与前端白名单一一对应；nav_*/none 供全局语音智能体）
VALID_ACTIONS: frozenset[str] = frozenset({
    "next", "prev", "timer_open", "timer_pause", "timer_resume",
    "timer_stop", "step_jump", "timer_preset", "help", "repeat",
    "finish", "close", "none",
    "nav_home", "nav_select", "nav_recommend", "nav_today", "nav_seasonal",
    "nav_recognize", "nav_profile", "nav_inventory", "nav_innovate",
    "nav_me", "nav_trace",
    "pick_recipe", "start_cooking",
})

# 意图解析 system prompt（强制 JSON、枚举校验、上下文合理性约束）
VOICE_INTENT_SYSTEM_PROMPT = (
    "你是烹饪助手的语音指令解析器。把用户说的一句话解析成 JSON 指令，只输出一个 JSON 对象，"
    "不要输出任何解释文字或代码围栏。"
    "action 枚举（只能取其一）。烹饪页指令（仅当上下文显示在烹饪引导页时使用）："
    "next=翻到下一步；prev=回上一步；timer_open=起一个计时器（minutes=分钟数，必须输出阿拉伯数字整数，把「八」「十五」等中文数字转成 8/15，没说分钟填 null）；"
    "timer_pause=暂停计时；timer_resume=继续计时；timer_stop=停止/取消计时；"
    "step_jump=跳到第几步（step_no=步骤号）；repeat=重读当前步骤；close=关闭当前弹层；"
    "finish=完成做菜；help=烹饪求助（question=问题正文，没说问题填 null）。"
    "全局导航指令（任意页面）："
    "nav_today=打开「今天吃什么」推荐；nav_seasonal=打开「时令吃什么」；"
    "nav_home=打开首页；nav_select=打开选择食材；nav_recommend=打开推荐结果；"
    "nav_recognize=打开拍照识别；nav_profile=打开家庭档案；nav_inventory=打开我的冰箱；"
    "nav_innovate=打开 AI 创新；nav_me=打开我的；nav_trace=打开调度面板；"
    "pick_recipe=在当前推荐列表里选第几个菜（step_no=序号从 1 起，仅当上下文显示在推荐列表页）；"
    "start_cooking=开始做当前菜谱（仅当上下文显示在菜谱详情页）；"
    "none=无法理解或不是可执行指令。"
    "结合上下文判断：用户想找菜/看推荐用 nav_today 或 nav_select；和烹饪有关的提问"
    "（能不能吃、怎么办）用 help；导航诉求与当前所在页面重复时仍正常输出导航动作。"
    "输出格式："
    '{"action":"...","minutes":null,"step_no":null,"question":null,"reply":null}'
    "reply 仅在 action=none 时可填一句 12 字以内的简短回应（如「没听懂，请再说一遍」），否则填 null。"
)

# 用户消息模板（上下文 JSON 注入）
_VOICE_INTENT_USER_TEMPLATE = '用户说：「{text}」\n当前上下文：{context}'


def parse_voice_intent(text: str, context: dict | None = None) -> dict:
    """解析白名单未命中的转写文本为结构化指令（函数）。

    说明：
        调主 LLM（settings.LLM_*，DeepSeek）做零样本意图解析，temperature=0
        保确定性；输出经 JSON 容错提取（首个 { 到末个 }）+ action 枚举校验，
        minutes/step_no 归一为 int|null，question/reply 归一为 str|null。
        LLM 输出非法 / 网络失败抛 LLMError 由路由层降级。

    参数：
        text：ASR 转写文本（白名单未命中）。
        context：烹饪上下文（当前步骤/计时器等，可缺省）。

    返回值：
        dict：{action, minutes, step_no, question, reply}（action 必为枚举值）。

    异常：
        LLMError：LLM 调用失败或输出无法解析出合法 JSON 时抛出。
    """
    text = (text or "").strip()
    if not text:
        return {"action": "none", "minutes": None, "step_no": None, "question": None, "reply": None}
    user_msg = _VOICE_INTENT_USER_TEMPLATE.format(
        text=text,
        context=json.dumps(context or {}, ensure_ascii=False),
    )
    result = get_llm_client().chat(
        system=VOICE_INTENT_SYSTEM_PROMPT,
        user=user_msg,
        temperature=0.0,
    )
    parsed = _extract_intent_json(result.content)
    if parsed is None:
        logger.warning("voice intent unparseable: %r", result.content[:200])
        raise LLMError("意图解析输出非法")
    return parsed


def _extract_intent_json(raw: str) -> dict | None:
    """从 LLM 原始输出容错提取意图 JSON 并校验归一（独立纯函数，便于单测）。

    说明：
        定位首个 '{' 到末个 '}' 截取，json.loads 失败返回 None；
        action 不在枚举内 / 顶层非 dict 归一为 none；
        minutes/step_no 尝试转 int（非法置 null），question/reply 仅保留非空字符串。

    参数：
        raw：LLM 输出文本（可能带围栏/杂字）。

    返回值：
        dict | None：归一后的意图对象；无法解析返回 None。

    异常：
        不抛出（解析失败返回 None）。
    """
    start = raw.find("{")
    end = raw.rfind("}")
    if start < 0 or end <= start:
        return None
    try:
        data = json.loads(raw[start : end + 1])
    except (json.JSONDecodeError, ValueError):
        return None
    if not isinstance(data, dict):
        return None
    action = str(data.get("action") or "none").strip().lower()
    if action not in VALID_ACTIONS:
        action = "none"

    def _int_or_none(value: object) -> int | None:
        if isinstance(value, bool) or value is None:
            return None
        try:
            return int(value)  # type: ignore[arg-type]
        except (TypeError, ValueError):
            return None

    def _str_or_none(value: object) -> str | None:
        if isinstance(value, str) and value.strip():
            return value.strip()
        return None

    return {
        "action": action,
        "minutes": _int_or_none(data.get("minutes")),
        "step_no": _int_or_none(data.get("step_no")),
        "question": _str_or_none(data.get("question")),
        "reply": _str_or_none(data.get("reply")),
    }
