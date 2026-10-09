"""后台管理端路由聚合模块。

职责：
    定义 /admin/v1 前缀的 APIRouter 并聚合各子路由：
    auth（登录/成员）/ recipes_admin / ingredients_admin（含营养）/
    risk_admin（规则+敏感词）/ logs_admin / feedbacks_admin /
    dashboard_admin / switches_admin / orders_admin / innovation_admin。
    由 app/main.py 追加一行 app.include_router(admin_router) 挂载。
"""

from fastapi import APIRouter

from app.api.admin import (
    auth,
    dashboard_admin,
    feedbacks_admin,
    ingredients_admin,
    innovation_admin,
    logs_admin,
    orders_admin,
    recipes_admin,
    risk_admin,
    switches_admin,
)

admin_router = APIRouter(prefix="/admin/v1")

# 各业务域子路由（tag 见各模块定义）
admin_router.include_router(auth.router)
admin_router.include_router(recipes_admin.router)
admin_router.include_router(ingredients_admin.router)
admin_router.include_router(risk_admin.router)
admin_router.include_router(logs_admin.router)
admin_router.include_router(feedbacks_admin.router)
admin_router.include_router(dashboard_admin.router)
admin_router.include_router(switches_admin.router)
admin_router.include_router(orders_admin.router)
admin_router.include_router(innovation_admin.router)
