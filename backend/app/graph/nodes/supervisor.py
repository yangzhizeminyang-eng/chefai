"""supervisor 意图识别节点模块。

职责：
    LLM 意图识别（9 类意图枚举，输出 JSON {intent}）→ 确定性字典路由（路由映射在
    main_graph.INTENT_ROUTES，LLM 只识别意图、不决定调用哪个工具）；
    LLMError / 解析失败 → 关键词兜底分类（降级，trace 记 degraded）。

复合意图（M.3）：
    用户输入同时包含「推荐诉求」（做菜/做个菜/推荐/吃什么）与「营养诉求」（营养/热量/
    卡路里）时，意图置为 composite_recommend_nutrition——LLM 提示词中定义该复合意图，
    关键词兜底路径同样覆盖（LLM 不可用/解析失败时仍可识别复合），路由复用推荐子图
    （子图内 recipe_rank ∥ node_nutrition 天然并行，营养部分由并行节点覆盖）。

双保险入口守卫：
    节点入口检查 input_verdict.overrides_all：若一票否决标记存在，节点直接以
    skipped_by_veto 状态返回（intent 置为 __veto__，由路由字典映射到否决出口），
    不执行任何业务逻辑（架构文档 §4.4 双保险的非 Command 等价实现，避免双重跳转歧义）。
"""

from __future__ import annotations

import json
import re

from app.ability import LLMError, get_llm_client
from app.core.logging import get_logger
from app.graph.nodes.common import make_span, now_ms
from app.graph.registry import register

logger = get_logger(__name__)

# 意图枚举（架构文档 §4.3 八类 + M.3 复合意图 + 模块 O 创新意图，共 10 类）
INTENTS: tuple[str, ...] = (
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
)

# 一票否决时的伪意图（仅由双保险守卫写入，路由字典映射到否决出口）
VETO_INTENT = "__veto__"

# 复合意图（M.3）关键词组：推荐诉求词 + 营养诉求词 同现即判复合
# （推荐词用短语级避免「怎么做」类搜索句被单字「做」误判）
_COMPOSITE_RECOMMEND_KWS: tuple[str, ...] = ("做菜", "做个菜", "做点", "推荐", "吃什么")
_COMPOSITE_NUTRITION_KWS: tuple[str, ...] = ("营养", "热量", "卡路里")

# 意图识别系统提示（只识别意图，不做回答）
SUPERVISOR_SYSTEM_PROMPT = (
    "你是烹饪助手的意图分类器。只输出 JSON，格式为 {\"intent\": \"<意图>\"}，不要输出任何其他内容。\n"
    "意图必须从以下 10 类中选一：\n"
    "recommend_by_ingredients：用户给出食材/想用现有食材做菜/要推荐；\n"
    "search_recipe：用户想知道某道具体菜怎么做/做法；\n"
    "photo_recognize：用户想拍照识别食材；\n"
    "free_qa：烹饪相关的其他问题或求助；\n"
    "cooking_help：烹饪过程中的临时求助（糊了/咸了怎么办）；\n"
    "nutrition_query：询问热量/卡路里/营养成分；\n"
    "inventory_op：库存/采购清单操作；\n"
    "smalltalk_or_out_of_scope：闲聊或与烹饪无关；\n"
    "innovation：用户想要 AI 创新/创造一道新菜/新奇搭配（如：帮我创新一个菜）；\n"
    "composite_recommend_nutrition：用户同时提出「用食材做菜/推荐」与「营养/热量查询」"
    "两类诉求（如：用鸡蛋做个菜，顺便看看今天营养）。"
)


def _parse_intent(content: str) -> str | None:
    """解析 LLM 输出的意图 JSON（函数）。

    说明：
        容忍模型输出代码块/前后缀文本：以正则抽取第一个 {...} 片段再 json.loads；
        意图不在枚举内视为失败。

    参数：
        content：LLM 输出文本。

    返回值：
        str | None：合法意图名；解析失败返回 None。

    异常：
        不抛出。
    """
    if not content:
        return None
    try:
        match = re.search(r"\{.*\}", content, re.DOTALL)
        if not match:
            return None
        data = json.loads(match.group(0))
        intent = data.get("intent")
        return intent if intent in INTENTS else None
    except Exception:  # noqa: BLE001 —— 解析失败交给关键词兜底
        return None


def _is_composite(text: str) -> bool:
    """判断文本是否为复合意图（推荐 + 营养诉求同现）（函数）。

    说明：
        M.3 复合意图的确定性判定：推荐诉求词与营养诉求词至少各命中一个；
        推荐词使用短语级（做菜/做个菜/做点/推荐/吃什么），避免「红烧肉怎么做，
        热量高吗」这类搜索+营养句被单字「做」误判为复合。

    参数：
        text：用户输入文本。

    返回值：
        bool：两类诉求词同现返回 True。

    异常：
        无。
    """
    t = text or ""
    has_recommend = any(k in t for k in _COMPOSITE_RECOMMEND_KWS)
    has_nutrition = any(k in t for k in _COMPOSITE_NUTRITION_KWS)
    return has_recommend and has_nutrition


def _keyword_fallback(text: str, has_ingredients: bool) -> str:
    """关键词兜底意图分类（函数）。

    说明：
        LLM 不可用/解析失败时的确定性降级路径（可枚举、可测试）：
        复合（推荐词+营养词同现）→ composite_recommend_nutrition；
        做法/怎么烧 → search_recipe；冰箱/库存 → inventory_op；
        忘了/糊了/咸了 → cooking_help；热量/营养 → nutrition_query；
        推荐/做/吃 → recommend_by_ingredients；怎么办/帮 → free_qa；
        其余 → free_qa；空文本且有食材 → recommend_by_ingredients。

    参数：
        text：用户输入文本。
        has_ingredients：是否携带食材（影响空文本默认意图）。

    返回值：
        str：意图名。

    异常：
        无。
    """
    t = text or ""
    # 0) 复合意图（M.3）：推荐诉求 + 营养诉求同现（先于单类意图判定）
    if _is_composite(t):
        return "composite_recommend_nutrition"
    # 0.5) 创新意图（模块 O）：创新/新搭配类表述（先于搜索/推荐，避免「创新菜怎么做」误入搜索）
    if any(k in t for k in ("创新", "新菜", "新奇搭配", "创造一道", "搭配出一道")):
        return "innovation"
    # 顺序：搜索（怎么做/做法）→ 库存 → 烹饪求助 → 营养 → 推荐 → 求助 → 兜底
    if any(k in t for k in ("怎么做", "做法", "怎么烧", "怎么炒", "怎么炖", "怎么做菜谱", "食谱")):
        return "search_recipe"
    if any(k in t for k in ("冰箱", "库存", "采购清单", "快过期", "临期", "还有什么食材")):
        return "inventory_op"
    if any(k in t for k in ("忘了", "忘记", "糊了", "糊锅", "太咸", "咸了", "烧干", "步骤忘了")):
        return "cooking_help"
    if any(k in t for k in ("热量", "卡路里", "营养", "蛋白质多少", "脂肪多少")):
        return "nutrition_query"
    if any(k in t for k in ("推荐", "做点", "有什么", "做", "吃")) or (not t and has_ingredients):
        return "recommend_by_ingredients"
    if any(k in t for k in ("怎么办", "帮", "请问", "如何")):
        return "free_qa"
    if not t:
        return "smalltalk_or_out_of_scope"
    return "free_qa"


def make_supervisor():
    """supervisor 节点工厂（函数）。

    返回值：
        Callable：节点函数。

    异常：
        无。
    """

    def supervisor(state: dict) -> dict:
        """意图识别节点（函数）。

        参数：
            state：编排状态。

        返回值：
            dict：{"intent": 意图名, "trace": [span]}（span 含 model/tokens/cost，
            LLM 失败时 status=degraded）。

        异常：
            不抛出（LLM 异常全部转关键词兜底）。
        """
        start = now_ms()
        # ---- 双保险入口守卫：一票否决标记存在时不执行任何业务逻辑 ----
        iv = state.get("input_verdict") or {}
        if iv.get("overrides_all"):
            return {
                "intent": VETO_INTENT,
                "trace": [make_span("supervisor", "skipped_by_veto", now_ms() - start)],
            }

        text = state.get("input_text") or ""
        names = list(state.get("resolved_ingredient_names") or [])
        if not names:
            # 显式食材未解析时，用原始输入的字符串食材兜底展示
            names = [i for i in (state.get("ingredients") or []) if isinstance(i, str)]
        has_ingredients = bool(names or state.get("resolved_ingredient_ids"))

        intent: str | None = None
        status = "ok"
        model_name: str | None = None
        prompt_tokens = completion_tokens = 0
        cost_cents: float | None = None
        try:
            client = get_llm_client()
            user_msg = (
                f"用户输入：{text if text else '（无文本，仅选择了食材）'}\n"
                f"已选食材：{'、'.join(names) if names else '无'}"
            )
            result = client.chat(SUPERVISOR_SYSTEM_PROMPT, user_msg, temperature=0.0)
            intent = _parse_intent(result.content)
            model_name = result.model
            prompt_tokens = result.prompt_tokens
            completion_tokens = result.completion_tokens
            cost_cents = result.cost_cents
            if intent is None:
                status = "degraded"  # LLM 通了但意图解析失败 → 兜底
        except LLMError:
            status = "degraded"  # LLM 不可用 → 关键词兜底

        if intent is None:
            intent = _keyword_fallback(text, has_ingredients)

        span = make_span(
            "supervisor",
            status,
            now_ms() - start,
            model_name=model_name,
            prompt_tokens=prompt_tokens or None,
            completion_tokens=completion_tokens or None,
            cost_cents=cost_cents,
        )
        logger.info("supervisor intent=%s status=%s", intent, status)
        return {"intent": intent, "trace": [span]}

    return supervisor


# ---- 注册 ----
register("supervisor", make_supervisor, forms="llm", timeout_ms=3000, description="LLM 意图识别（9 类含 M.3 复合意图）+ 关键词兜底（确定性字典路由）")
