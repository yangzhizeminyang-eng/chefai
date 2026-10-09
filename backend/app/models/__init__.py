"""ORM 模型汇总包。

职责：
    汇总导出 Base 与全部模型类（阶段一 28 张业务表 + recipe_embedding，
    阶段二新增 favorite_recipe 与模块 O 四表：ingredient_property /
    flavor_pairing_rule / technique_library / innovation_recipe），
    供 Base.metadata 与业务代码统一导入。
"""

from app.models.base import Base
from app.models.cooking import (
    CookingHelpLog,
    CookingSession,
    InventoryItem,
    MealRecord,
    RecipeFeedback,
    ShoppingListItem,
)
from app.models.ingredient import Ingredient, IngredientAlias, IngredientNutrition
from app.models.innovation import (
    FlavorPairingRule,
    IngredientProperty,
    InnovationRecipe,
    TechniqueLibrary,
)
from app.models.misc import AdminUser, Feedback, OperationLog, Order, RemoteConfig
from app.models.recipe import Recipe, RecipeEmbedding, RecipeIngredient, RecipeStep
from app.models.safety import AgentTrace, RiskLog, RiskMessage, RiskRule
from app.models.user import (
    ConsentRecord,
    DietGoal,
    DisclaimerConsent,
    Family,
    FamilyMember,
    FavoriteRecipe,
    User,
    UserSkillProfile,
)

# 显式重导出，消除 linter 未使用告警并明确公共接口
__all__ = [
    "Base",
    # 用户域（7 + 收藏）
    "User",
    "DisclaimerConsent",
    "ConsentRecord",
    "Family",
    "FamilyMember",
    "UserSkillProfile",
    "DietGoal",
    "FavoriteRecipe",
    # 食材域（3 + 五属性）
    "Ingredient",
    "IngredientAlias",
    "IngredientNutrition",
    "IngredientProperty",
    # 菜谱域（4）
    "Recipe",
    "RecipeIngredient",
    "RecipeStep",
    "RecipeEmbedding",
    # 烹饪与记录域（6）
    "InventoryItem",
    "CookingSession",
    "CookingHelpLog",
    "RecipeFeedback",
    "ShoppingListItem",
    "MealRecord",
    # 风控与调度域（4）
    "RiskRule",
    "RiskMessage",
    "RiskLog",
    "AgentTrace",
    # 运营与配置域（5）
    "Order",
    "RemoteConfig",
    "AdminUser",
    "OperationLog",
    "Feedback",
    # 模块 O（AI 菜品创新，4）
    "FlavorPairingRule",
    "TechniqueLibrary",
    "InnovationRecipe",
]
