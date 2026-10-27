"""OpenAPI schema 防复发测试：operation_id 全局唯一（质量债清理）。

背景：
    多个测试模块在导入期向同一 router/app 补挂载功能路由；同一 router 被
    重复 include 会让 FastAPI get_openapi() 发出 "Duplicate Operation ID"
    UserWarning。守卫（conftest.ensure_router_registered）防重复注册；
    本测试把该告警升级为错误并断言 operation_id 全局唯一，防止守卫被
    移除后问题静默复发。
"""

from __future__ import annotations

import warnings

from app.main import app


def test_openapi_operation_ids_unique() -> None:
    """app.openapi() 无 Duplicate Operation ID 告警且 operation_id 全局唯一（测试）。

    说明：
        先清 app.openapi_schema 缓存强制重新生成（否则其他测试已生成过缓存，
        重复路由不会再次触发告警）；将 "Duplicate Operation ID" UserWarning
        升级为错误；再收集 paths 下全部 operationId 断言无重复（双保险）。

    参数：
        无。

    返回值：
        None。

    异常：
        Duplicate Operation ID 告警触发或 operation_id 有重复时断言失败。
    """
    app.openapi_schema = None  # 清缓存：强制 get_openapi 重新生成并重新检查
    with warnings.catch_warnings():
        warnings.filterwarnings("error", message="Duplicate Operation ID", category=UserWarning)
        schema = app.openapi()
    operation_ids = [
        str(operation["operationId"])
        for path_item in schema["paths"].values()
        for operation in path_item.values()
        if isinstance(operation, dict) and "operationId" in operation
    ]
    assert operation_ids, "OpenAPI paths 应包含带 operationId 的操作"
    assert len(operation_ids) == len(set(operation_ids)), "OpenAPI operation_id 必须全局唯一"
