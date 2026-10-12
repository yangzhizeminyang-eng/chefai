"""API v1 路由聚合模块。

职责：
    定义 /v1 前缀的 APIRouter 并聚合各业务子路由（15 模块全量）：
    auth / consent / profile / ingredients / vision / speech / ask / recommend /
    recipes / cooking / nutrition / inventory(含 shopping-list) / personal(收藏历史个人) /
    home / member / feedback / innovation / trace / config。
    汇总顺序不影响路由匹配（各子路由前缀互不冲突）。
"""

from fastapi import APIRouter

from app.api.v1 import (
    ask,
    auth,
    config,
    consent,
    cooking,
    day_menu,
    feedback,
    home,
    ingredients,
    innovation,
    inventory,
    member,
    nutrition,
    personal,
    profile,
    recipes,
    recommend,
    seasonal,
    speech,
    trace,
    vision,
)

api_router = APIRouter(prefix="/v1")

# 各业务域子路由（tag/summary 见各模块端点定义）
api_router.include_router(auth.router)
api_router.include_router(consent.router)
api_router.include_router(profile.router)          # 模块 C 档案 + A.6 敏感同意
api_router.include_router(ingredients.router)
api_router.include_router(vision.router)           # 模块 D 识别
api_router.include_router(speech.router)           # 模块 D 语音
api_router.include_router(ask.router)
api_router.include_router(recommend.router)
api_router.include_router(day_menu.router)         # 零输入直出推荐（今天吃什么，add-home-entries-and-covers）
api_router.include_router(seasonal.router)         # 时令页聚合（时令吃什么，add-home-entries-and-covers）
api_router.include_router(recipes.router)
api_router.include_router(cooking.router)
api_router.include_router(nutrition.router)        # 模块 G 营养汇总/补录
api_router.include_router(inventory.router)        # 模块 H 库存 + 扣减建议
api_router.include_router(inventory.shopping_router)  # 模块 H 购物清单
api_router.include_router(personal.router)         # 模块 I 收藏/历史/个人中心
api_router.include_router(home.router)             # 模块 B 首页聚合
api_router.include_router(member.router)           # 模块 J 会员与支付（模拟）
api_router.include_router(feedback.router)         # 模块 N 用户反馈
api_router.include_router(innovation.router)       # 模块 O AI 菜品创新
api_router.include_router(trace.router)
api_router.include_router(config.router)
