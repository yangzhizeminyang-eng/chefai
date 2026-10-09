"""schemas 包：Pydantic v2 请求/响应模型。

职责：
    按业务域拆分的 API 契约模型汇总导出；字段命名以 web-stage1/src/api/types.ts
    为权威依据（snake_case 直译），附加字段仅做兼容冗余（多余无害）。
"""

from app.schemas.ask import AskRequest, AskResponse, BlockedResponse
from app.schemas.auth import (
    AnonymousRequest,
    AnonymousResponse,
    ConsentRequest,
    ConsentResponse,
)
from app.schemas.cooking import (
    CookingSessionCreate,
    CookingSessionDetailOut,
    CookingSessionOut,
    CookingSessionPatch,
    FinishRequest,
    FinishResponse,
)
from app.schemas.ingredients import IngredientItem, IngredientListResponse
from app.schemas.recipes import (
    NutritionOut,
    RecipeDetailResponse,
    RecipeIngredientItem,
    RecipeStepItem,
)
from app.schemas.recommend import (
    RecommendIngredient,
    RecommendOptions,
    RecommendRequest,
    RecommendResponse,
    RecommendResultItem,
)
from app.schemas.trace import (
    SwitchesResponse,
    TraceDetailResponse,
    TraceListItem,
    TraceSpanOut,
    TraceTotalsOut,
    TraceVetoOut,
)

__all__ = [
    # common
    "RiskDetailOut",
    # auth / consent
    "AnonymousRequest",
    "AnonymousResponse",
    "ConsentRequest",
    "ConsentResponse",
    # ingredients
    "IngredientItem",
    "IngredientListResponse",
    # ask
    "AskRequest",
    "AskResponse",
    "BlockedResponse",
    # recommend
    "RecommendIngredient",
    "RecommendOptions",
    "RecommendRequest",
    "RecommendResultItem",
    "RecommendResponse",
    # recipes / nutrition
    "NutritionOut",
    "RecipeDetailResponse",
    "RecipeIngredientItem",
    "RecipeStepItem",
    # cooking
    "CookingSessionCreate",
    "CookingSessionDetailOut",
    "CookingSessionOut",
    "CookingSessionPatch",
    "FinishRequest",
    "FinishResponse",
    # trace / config
    "SwitchesResponse",
    "TraceDetailResponse",
    "TraceListItem",
    "TraceSpanOut",
    "TraceTotalsOut",
    "TraceVetoOut",
]
