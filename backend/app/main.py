"""FastAPI 应用入口。

职责：
    - 创建 FastAPI 实例（标题/版本对齐 PRD）；
    - CORS 允许 Web 演示端源（http://localhost:5173 / http://127.0.0.1:5173）；
    - request_id 中间件：无 X-Request-Id 请求头时生成，回写响应头，并通过 ContextVar 贯穿结构化日志；
    - 全局异常处理器：统一错误 JSON {code, message, detail}；
    - 健康检查三路由共用同一 handler：GET /api/health（既有兼容）/ GET /healthz
      （docker healthcheck 根级口径，04-V1.1 §7）/ GET /v1/healthz（05-V1.1 §9.5/§12.3）；
      SELECT 1 检查数据库连通性（异常 503）；
    - 挂载 /v1 业务路由（app/api/v1/router.py，由后续任务填充）。
"""

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.api.admin.router import admin_router
from app.api.v1.router import api_router
from app.core.config import settings
from app.core.db import SessionLocal
from app.core.logging import configure_logging, get_logger, new_request_id, request_id_var

# 应用启动时装配结构化日志
configure_logging()
logger = get_logger(__name__)

app = FastAPI(title="AI 厨娘・智能烹饪助手 API", version="1.0.0")

# CORS：允许阶段一 Web 演示端（Vite 默认端口 5173）跨域携带凭证
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def request_id_middleware(request: Request, call_next):
    """request_id 中间件（函数）。

    说明：
        优先复用客户端传入的 X-Request-Id（幂等键），否则生成新的；
        回写响应头并设置日志上下文变量，实现全链路贯穿。

    参数：
        request：FastAPI 请求对象。
        call_next：下游处理链。

    返回值：
        Response：附加 X-Request-Id 响应头的响应对象。

    异常：
        下游异常继续向上抛出，由全局异常处理器统一兜底。
    """
    rid = request.headers.get("X-Request-Id") or new_request_id()
    # 设置 ContextVar，本请求内所有结构化日志自动携带 request_id
    token = request_id_var.set(rid)
    try:
        response = await call_next(request)
        response.headers["X-Request-Id"] = rid
        return response
    finally:
        request_id_var.reset(token)


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """全局异常处理器（函数）。

    说明：
        兜底所有未处理异常，返回统一错误 JSON，避免堆栈外泄。

    参数：
        request：FastAPI 请求对象。
        exc：抛出的异常。

    返回值：
        JSONResponse：500 状态码，形如 {"code","message","detail"} 的错误体。

    异常：
        本处理器自身不再抛出异常（detail 序列化失败时降级为空串）。
    """
    logger.error("unhandled_exception", extra={"path": request.url.path})
    try:
        detail = str(exc)
    except Exception:
        detail = ""
    return JSONResponse(
        status_code=500,
        content={"code": "INTERNAL_ERROR", "message": "服务内部错误，请稍后重试", "detail": detail},
    )


@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(request: Request, exc: StarletteHTTPException) -> JSONResponse:
    """HTTPException 统一处理器（函数）。

    说明：
        路由内抛出的 HTTPException（detail 携带 {code, message, detail} 结构）展开为
        顶层统一错误 JSON；兼容 detail 为字符串的默认异常（404 路由未命中等）。

    参数：
        request：FastAPI 请求对象。
        exc：HTTPException 实例。

    返回值：
        JSONResponse：状态码取 exc.status_code，错误体 {code, message, detail}。

    异常：
        本处理器自身不再抛出异常（detail 结构异常时降级为字符串）。
    """
    if isinstance(exc.detail, dict):
        body = {
            "code": exc.detail.get("code", f"HTTP_{exc.status_code}"),
            "message": exc.detail.get("message", str(exc.detail)),
            "detail": exc.detail.get("detail"),
        }
    else:
        body = {"code": f"HTTP_{exc.status_code}", "message": str(exc.detail), "detail": None}
    return JSONResponse(status_code=exc.status_code, content=body, headers=getattr(exc, "headers", None))


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    """请求参数校验异常处理器（函数）。

    参数：
        request：FastAPI 请求对象。
        exc：参数校验异常。

    返回值：
        JSONResponse：422 状态码的统一错误 JSON。

    异常：
        无。
    """
    return JSONResponse(
        status_code=422,
        content={"code": "VALIDATION_ERROR", "message": "请求参数不合法", "detail": str(exc.errors())},
    )


# 健康检查三路由共用同一 handler（spec fix-onestart-align-v11）：
#   - GET /api/health   既有兼容口径（保持 200/503 与 status/database 语义不变）；
#   - GET /healthz      04-V1.1 §7 容器 healthcheck 根级口径；
#   - GET /v1/healthz   05-V1.1 §9.5/§12.3 与 manage.ps1 探测口径。
@app.get("/api/health", summary="健康检查（既有兼容口径）")
@app.get("/healthz", summary="健康检查（docker healthcheck 根级口径，04-V1.1 §7）")
@app.get("/v1/healthz", summary="健康检查（05-V1.1 §9.5/§12.3 标准口径）")
def health_check() -> JSONResponse:
    """健康检查接口（函数）。

    说明：
        执行 SELECT 1 验证数据库连通性；数据库异常时返回 503 与 database=down。
        200 响应附带应用版本号 version（取 FastAPI 实例 version 字段）。

    参数：
        无。

    返回值：
        JSONResponse：200 {"status":"ok","database":"up","version":"1.0.0"}
        或 503 {"status":"degraded","database":"down"}。

    异常：
        数据库连接异常被捕获并转换为 503，不向外抛出。
    """
    try:
        # 独立短会话探活，不复用请求级会话
        with SessionLocal() as session:
            session.execute(text("SELECT 1"))
        return JSONResponse(content={"status": "ok", "database": "up", "version": app.version})
    except Exception as exc:
        logger.error("health_check_db_down", extra={"error": str(exc)})
        return JSONResponse(
            status_code=503,
            content={"status": "degraded", "database": "down"},
        )


# 挂载 /v1 业务路由（阶段一 REST API，由 Task 5 填充具体端点）
app.include_router(api_router)

# 挂载 /admin/v1 后台管理路由（模块 K，JWT 鉴权 + 三级角色）
app.include_router(admin_router)


@app.on_event("startup")
def on_startup() -> None:
    """应用启动钩子（函数）。

    说明：
        打印配置摘要（脱敏，不输出 API Key），便于排查部署环境。

    参数：
        无。

    返回值：
        None。

    异常：
        无。
    """
    logger.info(
        "startup",
        extra={
            "db": f"{settings.DB_HOST}:{settings.DB_PORT}/{settings.DB_NAME}",
            "llm_model": settings.LLM_MODEL,
            "port": settings.APP_PORT,
        },
    )
