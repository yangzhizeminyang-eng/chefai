"""ability 包：能力适配层（LLM 客户端 / 检索 / 排序 / 营养估算）。

公共导出：
    LLMClient / LLMResult / LLMError / get_llm_client：大模型能力（失败抛 LLMError，调用方降级）；
    retrieve_candidates / match_ingredients_in_text：混合召回；
    hard_filter / weighted_rank / load_weights：布尔硬过滤与 7 因子排序；
    estimate_recipe_nutrition / estimate_nutrition_parallel：营养估算。
"""

from app.ability.llm import LLMClient, LLMError, LLMResult, get_llm_client
from app.ability.nutrition import estimate_nutrition_parallel, estimate_recipe_nutrition
from app.ability.ranking import hard_filter, load_weights, weighted_rank
from app.ability.retrieval import match_ingredients_in_text, retrieve_candidates

__all__ = [
    "LLMClient",
    "LLMResult",
    "LLMError",
    "get_llm_client",
    "retrieve_candidates",
    "match_ingredients_in_text",
    "hard_filter",
    "weighted_rank",
    "load_weights",
    "estimate_recipe_nutrition",
    "estimate_nutrition_parallel",
]
