"""后台管理端 API 包（模块 K）。

职责：
    聚合 /admin/v1/** 全部子路由模块（router.py 挂 prefix="/admin/v1"），
    并提供各子模块共享的工具函数：
    - api_error：统一错误 HTTPException（{code,message,detail} 结构）；
    - page_args：page/size 查询参数 → offset/limit（size 上限 100）；
    - unwrap_401/403 由 app/core/security.py 依赖层抛出，本包不再处理。

子模块清单：
    auth（登录/me/成员）、recipes_admin、ingredients_admin（含营养）、
    risk_admin（规则+敏感词）、logs_admin、feedbacks_admin、dashboard_admin、
    switches_admin、orders_admin、innovation_admin。
"""

from __future__ import annotations

from fastapi import HTTPException, Query

# 统一错误码（与 api/v1 口径一致，后台独立定义避免反向依赖）
ERR_NOT_FOUND = "NOT_FOUND"
ERR_CONFLICT = "STATE_CONFLICT"
ERR_BAD_REQUEST = "BAD_REQUEST"
ERR_VALIDATION = "VALIDATION_ERROR"
ERR_FORBIDDEN = "FORBIDDEN"


def api_error(status_code: int, code: str, message: str, detail=None) -> HTTPException:
    """构造统一错误 HTTPException（函数）。

    说明：
        detail 携带 {code, message, detail} 结构，由 main.py 全局处理器展开为
        顶层统一错误 JSON。

    参数：
        status_code：HTTP 状态码。
        code：业务错误码。
        message：错误文案。
        detail：补充信息（可 None）。

    返回值：
        HTTPException：可直接 raise 的异常实例。

    异常：
        无。
    """
    return HTTPException(
        status_code=status_code,
        detail={"code": code, "message": message, "detail": detail},
    )


async def page_args(
    page: int = Query(default=1, ge=1, description="页码，1 起"),
    size: int = Query(default=20, ge=1, le=100, description="每页条数，上限 100"),
) -> tuple[int, int]:
    """分页参数转 (offset, limit)（依赖函数）。

    参数：
        page：页码（1 起）。
        size：每页条数（1~100）。

    返回值：
        tuple[int, int]：(offset, limit)。

    异常：
        无（越界由 Query ge/le 校验转 422）。
    """
    return (page - 1) * size, size
