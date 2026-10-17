"""Agent 标准工具调用框架模块（阶段二）。

职责：
    提供主图节点（tool_loop）可安全调用的标准工具协议与执行框架：
    - ToolError：结构化工具错误（code ∈ invalid_params/timeout/permission_denied/
      unavailable/internal），供执行框架转结构化结果而非向调用方抛异常；
    - ToolContext：单次工具执行的上下文（user_id/request_id/超时预算）；
    - AgentTool 抽象基类：name/description/read_only 属性 + parameters_schema()
      （JSON Schema）+ execute()（抽象，子类实现业务逻辑）；
    - ToolResult：审计友好的执行结果（tool_name/params_summary/elapsed_ms/
      attempts/status/error_code/cached/result/message）；
    - execute_tool：统一执行入口——pydantic 参数校验（失败返回 invalid_params，
      不抛异常给调用方）→ 幂等缓存（只读工具，LRU）→ 线程池超时控制 →
      tenacity 重试（仅 unavailable/timeout，最多 2 次重试共 3 次尝试）。

复用红线：
    工具只读且只复用既有业务函数（retrieval/nutrition），不重写业务逻辑；
    检索走 use_vector=False（避免触发 embedding 惰性回填写库，保持只读语义）。
"""

from __future__ import annotations

import json
import threading
import time
from abc import ABC, abstractmethod
from collections import OrderedDict
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from typing import Any

from pydantic import BaseModel, Field, ValidationError, create_model
from sqlalchemy import func, select, text
from tenacity import RetryCallState, retry, retry_if_exception, stop_after_attempt, wait_fixed

from app.ability.nutrition import estimate_recipe_nutrition
from app.ability.retrieval import retrieve_candidates
from app.core.db import SessionLocal
from app.core.logging import get_logger
from app.models import Ingredient, InventoryItem, Recipe, RecipeIngredient, RecipeStep

logger = get_logger(__name__)

# 可重试错误码集合（unavailable=依赖暂不可用 / timeout=执行超时，其余不重试）
_RETRYABLE_CODES: frozenset[str] = frozenset({"unavailable", "timeout"})

# 最大重试次数（tenacity stop_after_attempt 为总尝试次数：1 次初始 + 2 次重试）
_MAX_ATTEMPTS = 3

# 重试间隔秒数（固定短等待，避免拖慢主链路）
_RETRY_WAIT_SECONDS = 0.05

# 幂等缓存容量（LRU，进程内；只缓存只读工具的成功结果）
_CACHE_CAPACITY = 128

# params_summary 截断长度（审计摘要防刷屏，不含敏感字段值）
_SUMMARY_MAX_CHARS = 200

# 敏感字段名（params_summary 中这些键的值被掩码，不进审计/日志）
_SENSITIVE_KEYS: frozenset[str] = frozenset({"api_key", "apikey", "password", "token", "secret"})


class ToolError(Exception):
    """工具执行错误（模型类）。

    说明：
        工具与执行框架内部用异常传递失败，execute_tool 统一捕获转为
        ToolResult（status=error + error_code），绝不向调用方（编排节点）抛出。

    属性：
        code：错误码（invalid_params/timeout/permission_denied/unavailable/internal）。
        message：错误描述。
    """

    def __init__(self, code: str, message: str) -> None:
        """构造异常（函数）。

        参数：
            code：错误码（五个枚举值之一）。
            message：错误描述。

        返回值：
            None。

        异常：
            无。
        """
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass
class ToolContext:
    """单次工具执行上下文（模型类）。

    属性：
        user_id：当前用户数字 ID（None=未登录/匿名，需要归属的工具据此拒绝）。
        request_id：请求唯一标识（审计关联）。
        max_timeout_seconds：单次执行超时预算秒数（默认 10，编排侧按剩余预算收紧）。
    """

    user_id: int | None = None
    request_id: str = ""
    max_timeout_seconds: float = 10.0


@dataclass
class ToolResult:
    """工具执行结果（模型类）。

    说明：
        既是返回载荷（result）也是审计记录（tool_name/params_summary/elapsed_ms/
        attempts/status/error_code）；cached=True 表示命中幂等缓存（未实际执行）。

    属性：
        tool_name：工具名。
        params_summary：参数审计摘要（JSON 截断 + 敏感值掩码）。
        elapsed_ms：耗时毫秒（缓存命中时接近 0）。
        attempts：实际执行尝试次数（校验失败/缓存命中为 0）。
        status：执行状态（ok/error）。
        error_code：失败时的错误码（成功为 None）。
        message：失败描述（成功为 None）。
        cached：是否命中幂等缓存。
        result：成功时的返回数据（dict）。
    """

    tool_name: str
    params_summary: str = ""
    elapsed_ms: float = 0.0
    attempts: int = 0
    status: str = "ok"
    error_code: str | None = None
    message: str | None = None
    cached: bool = False
    result: dict[str, Any] = field(default_factory=dict)


class AgentTool(ABC):
    """Agent 标准工具抽象基类（模型类）。

    说明：
        子类实现 parameters_schema() 与 execute()；read_only=True 的工具才有资格
        进入幂等缓存与 MCP 只读白名单。执行统一经 execute_tool（校验/超时/重试/
        缓存/审计），子类不要绕过。

    属性：
        name：工具名（注册键，全局唯一）。
        description：用途描述（进入 LLM 工具选择提示词）。
        read_only：是否只读（True 才可缓存 / 进 MCP 白名单）。
    """

    name: str = ""
    description: str = ""
    read_only: bool = True

    @abstractmethod
    def parameters_schema(self) -> dict:
        """返回工具参数 JSON Schema（函数）。

        返回值：
            dict：JSON Schema（type=object，properties/required 与 pydantic 校验对齐）。

        异常：
            无。
        """

    @abstractmethod
    def execute(self, params: dict, ctx: ToolContext) -> dict:
        """执行工具业务逻辑（函数）。

        说明：
            只描述业务成功路径；一切失败通过 ToolError(code, message) 抛出，
            由 execute_tool 捕获转结构化结果。

        参数：
            params：已通过校验的参数字典。
            ctx：执行上下文（user_id/request_id/超时预算）。

        返回值：
            dict：工具结果数据（可 JSON 序列化）。

        异常：
            ToolError：参数/权限/依赖不可用/内部错误（code 区分）。
        """


# ---------------------------------------------------------------------------
# 幂等缓存（进程内 LRU，只缓存只读工具成功结果）
# ---------------------------------------------------------------------------
_tool_cache: OrderedDict[str, dict] = OrderedDict()
_cache_lock = threading.Lock()


def clear_tool_cache() -> None:
    """清空工具幂等缓存（函数）。

    说明：
        供测试隔离与运维手工清理；生产进程内缓存随结果自然淘汰。

    参数：
        无。

    返回值：
        None。

    异常：
        无。
    """
    with _cache_lock:
        _tool_cache.clear()


def _cache_key(tool_name: str, params: dict) -> str:
    """构造幂等缓存键（函数）。

    说明：
        键 = tool_name + 规范化参数 JSON（sort_keys 确保键序无关；ensure_ascii=False
        保持中文可读）；规范化失败的极端情况退化为 str(params)。

    参数：
        tool_name：工具名。
        params：校验后的参数字典。

    返回值：
        str：缓存键。

    异常：
        无。
    """
    try:
        canonical = json.dumps(params, sort_keys=True, ensure_ascii=False, default=str)
    except Exception:  # noqa: BLE001 —— 不可序列化参数退化为字符串表示
        canonical = str(params)
    return f"{tool_name}::{canonical}"


def _cache_get(key: str) -> dict | None:
    """读取缓存（LRU 命中提升，函数）。

    参数：
        key：缓存键。

    返回值：
        dict | None：命中返回结果副本；未命中返回 None。

    异常：
        无。
    """
    with _cache_lock:
        value = _tool_cache.get(key)
        if value is None:
            return None
        _tool_cache.move_to_end(key)
        return dict(value)


def _cache_put(key: str, value: dict) -> None:
    """写入缓存（超容量淘汰最旧，函数）。

    参数：
        key：缓存键。
        value：工具结果数据。

    返回值：
        None。

    异常：
        无。
    """
    with _cache_lock:
        _tool_cache[key] = dict(value)
        _tool_cache.move_to_end(key)
        while len(_tool_cache) > _CACHE_CAPACITY:
            _tool_cache.popitem(last=False)


# ---------------------------------------------------------------------------
# 参数校验（JSON Schema → pydantic 动态模型）
# ---------------------------------------------------------------------------
_JSON_TYPE_MAP: dict[str, Any] = {
    "string": str,
    "integer": int,
    "number": float,
    "boolean": bool,
    "array": list,
    "object": dict,
}


def _model_from_schema(tool_name: str, schema: dict) -> type[BaseModel] | None:
    """按 JSON Schema 动态构造 pydantic 校验模型（函数）。

    说明：
        支持 string/integer/number/boolean/array/object 六类字段类型、required
        必填、default 默认值与 minimum/maximum（映射 ge/le）；schema 不规范时
        返回 None（跳过校验，交由工具自身防御）。

    参数：
        tool_name：工具名（用作动态模型名）。
        schema：工具 parameters_schema() 返回的 JSON Schema。

    返回值：
        type[BaseModel] | None：动态校验模型；schema 缺失/不规范返回 None。

    异常：
        无（构造失败按 None 处理）。
    """
    try:
        if not isinstance(schema, dict) or schema.get("type") != "object":
            return None
        properties = schema.get("properties") or {}
        required = set(schema.get("required") or [])
        fields: dict[str, Any] = {}
        for key, spec in properties.items():
            if not isinstance(spec, dict):
                continue
            py_type = _JSON_TYPE_MAP.get(str(spec.get("type") or "string"), str)
            constraints: dict[str, Any] = {}
            if spec.get("minimum") is not None:
                constraints["ge"] = spec["minimum"]
            if spec.get("maximum") is not None:
                constraints["le"] = spec["maximum"]
            field_default = ... if key in required else spec.get("default", None)
            fields[key] = (py_type | None, Field(default=field_default, description=spec.get("description"), **constraints))
        if not fields:
            return None
        return create_model(f"{tool_name}Params", **fields)
    except Exception as exc:  # noqa: BLE001 —— schema 异常不阻断执行
        logger.warning("build params model failed (tool=%s): %s", tool_name, exc)
        return None


def _validate_params(tool: AgentTool, params: dict) -> dict:
    """校验工具参数（函数）。

    说明：
        params 非字典直接 invalid_params；动态模型构造成功时按模型校验
        （未知键忽略，容错 LLM 输出），校验失败抛 ToolError(invalid_params)。

    参数：
        tool：工具实例。
        params：原始参数字典。

    返回值：
        dict：校验后的参数（含默认值填充）。

    异常：
        ToolError：code=invalid_params。
    """
    if params is None:
        params = {}
    if not isinstance(params, dict):
        raise ToolError("invalid_params", "params must be a JSON object")
    model = _model_from_schema(tool.name, tool.parameters_schema())
    if model is None:
        return params
    try:
        validated = model(**params)
    except ValidationError as exc:
        first = exc.errors()[0] if exc.errors() else {}
        loc = ".".join(str(p) for p in first.get("loc", ()) )
        raise ToolError("invalid_params", f"param validation failed: {loc} {first.get('msg', '')}".strip()) from exc
    dumped = validated.model_dump(exclude_none=True)
    # 透传 schema 未声明的额外键（宽松容错，LLM 多输出的键不致命）
    for key, value in params.items():
        if key not in dumped:
            dumped[key] = value
    return dumped


def _params_summary(params: dict) -> str:
    """生成参数审计摘要（函数）。

    说明：
        JSON 序列化后截断到 _SUMMARY_MAX_CHARS；敏感字段（api_key/password/
        token/secret 等，键名不区分大小写）的值以 *** 掩码，不进审计与日志。

    参数：
        params：参数字典（可含任意可序列化值）。

    返回值：
        str：截断掩码后的摘要字符串。

    异常：
        无。
    """

    def _mask(data: Any) -> Any:
        if isinstance(data, dict):
            return {
                k: ("***" if str(k).lower() in _SENSITIVE_KEYS else _mask(v))
                for k, v in data.items()
            }
        if isinstance(data, list):
            return [_mask(item) for item in data]
        return data

    try:
        text_value = json.dumps(_mask(params), ensure_ascii=False, default=str)
    except Exception:  # noqa: BLE001
        text_value = str(params)
    if len(text_value) > _SUMMARY_MAX_CHARS:
        text_value = text_value[:_SUMMARY_MAX_CHARS] + "...(truncated)"
    return text_value


# ---------------------------------------------------------------------------
# 执行框架（超时 + 重试 + 缓存 + 审计）
# ---------------------------------------------------------------------------
_executor: ThreadPoolExecutor | None = None
_executor_lock = threading.Lock()


def _get_executor() -> ThreadPoolExecutor:
    """获取工具执行线程池单例（函数）。

    说明：
        模块级共享线程池（放弃超时 future 时不阻塞进程退出——worker 为
        atexit 兜底线程）；超时后底层线程继续运行属预期，任务本身须短平快。

    参数：
        无。

    返回值：
        ThreadPoolExecutor：共享执行器。

    异常：
        无。
    """
    global _executor
    if _executor is None:
        with _executor_lock:
            if _executor is None:
                _executor = ThreadPoolExecutor(max_workers=8, thread_name_prefix="agent-tool")
    return _executor


def _run_once(tool: AgentTool, params: dict, ctx: ToolContext) -> dict:
    """单次执行工具（含超时控制，函数）。

    说明：
        提交到共享线程池并按 ctx.max_timeout_seconds 等待；超时转
        ToolError(timeout)（底层线程不中断，由任务自身尽快结束）。

    参数：
        tool：工具实例。
        params：校验后的参数。
        ctx：执行上下文。

    返回值：
        dict：工具结果。

    异常：
        ToolError：timeout（超时）/ internal（工具未分类异常）/ 工具自身 ToolError 原样透传。
    """
    future = _get_executor().submit(tool.execute, params, ctx)
    try:
        return future.result(timeout=ctx.max_timeout_seconds)
    except ToolError:
        raise  # 工具业务异常原样透传（错误码语义由工具决定）
    except Exception as exc:  # noqa: BLE001 —— 含 futures.TimeoutError 与未分类异常
        from concurrent.futures import TimeoutError as FutureTimeoutError

        if isinstance(exc, FutureTimeoutError):
            raise ToolError(
                "timeout",
                f"tool {tool.name} timed out after {ctx.max_timeout_seconds}s",
            ) from exc
        raise ToolError("internal", f"tool {tool.name} raised unexpected error: {exc}") from exc


def _is_retryable(exc: BaseException) -> bool:
    """判断异常是否可重试（函数）。

    参数：
        exc：待判定异常。

    返回值：
        bool：ToolError 且 code ∈ {unavailable, timeout} 时可重试。

    异常：
        无。
    """
    return isinstance(exc, ToolError) and exc.code in _RETRYABLE_CODES


def _run_with_retry(tool: AgentTool, params: dict, ctx: ToolContext, attempts: dict) -> dict:
    """带重试地执行工具（函数）。

    说明：
        tenacity：仅对 unavailable/timeout 重试，stop_after_attempt(3) 即
        1 次初始 + 2 次重试；reraise=True 让最终 ToolError 透传给调用方；
        attempts 字典记录实际尝试次数（审计字段）。

    参数：
        tool：工具实例。
        params：校验后的参数。
        ctx：执行上下文。
        attempts：尝试次数字典（in-out，键 "n"）。

    返回值：
        dict：工具结果。

    异常：
        ToolError：重试耗尽后抛出最后一次错误（invalid_params/permission_denied 不重试直接透传）。
    """

    def _once() -> dict:
        attempts["n"] += 1
        return _run_once(tool, params, ctx)

    def _count_retry(retry_state: RetryCallState) -> None:
        logger.warning(
            "tool retry (tool=%s attempt=%s) last_error=%s",
            tool.name,
            retry_state.attempt_number,
            retry_state.outcome.exception() if retry_state.outcome else None,
        )

    runner = retry(
        retry=retry_if_exception(_is_retryable),
        stop=stop_after_attempt(_MAX_ATTEMPTS),
        wait=wait_fixed(_RETRY_WAIT_SECONDS),
        before_sleep=_count_retry,
        reraise=True,
    )(_once)
    return runner()


def execute_tool(tool: AgentTool, params: dict, ctx: ToolContext) -> ToolResult:
    """执行工具的统一入口（函数）。

    说明：
        流程：参数校验（失败返回 invalid_params 结构化结果，不抛异常）→
        幂等缓存查询（仅 read_only 工具，命中直接返回 cached=True）→
        线程池超时执行 + tenacity 重试（unavailable/timeout，最多 3 次尝试）→
        成功结果写入缓存；任何分支都不向调用方抛异常。

    参数：
        tool：工具实例。
        params：原始参数字典（可缺省/含未知键）。
        ctx：执行上下文。

    返回值：
        ToolResult：结构化结果（status=ok/error，审计字段齐备）。

    异常：
        不抛出（全部异常转结构化结果）。
    """
    start = time.perf_counter()
    summary = _params_summary(params if isinstance(params, dict) else {})

    def _finish(result: ToolResult) -> ToolResult:
        result.tool_name = tool.name
        result.params_summary = summary
        result.elapsed_ms = round((time.perf_counter() - start) * 1000, 1)
        return result

    # 1) 参数校验
    try:
        validated = _validate_params(tool, params)
    except ToolError as exc:
        return _finish(
            ToolResult(tool_name=tool.name, status="error", error_code=exc.code, message=exc.message, attempts=0)
        )

    # 2) 幂等缓存（仅只读工具）
    if tool.read_only:
        key = _cache_key(tool.name, validated)
        hit = _cache_get(key)
        if hit is not None:
            return _finish(
                ToolResult(
                    tool_name=tool.name,
                    status="ok",
                    cached=True,
                    result=hit,
                    attempts=0,
                )
            )
    else:
        key = ""

    # 3) 超时执行 + 重试
    attempts = {"n": 0}
    try:
        data = _run_with_retry(tool, validated, ctx, attempts)
        if tool.read_only:
            _cache_put(key, data)
        return _finish(
            ToolResult(tool_name=tool.name, status="ok", result=data, attempts=attempts["n"], cached=False)
        )
    except ToolError as exc:
        return _finish(
            ToolResult(
                tool_name=tool.name,
                status="error",
                error_code=exc.code,
                message=exc.message,
                attempts=attempts["n"],
            )
        )
    except Exception as exc:  # noqa: BLE001 —— 兜底：框架自身异常不向编排层抛出
        logger.error("execute_tool unexpected failure (tool=%s): %s", tool.name, exc)
        return _finish(
            ToolResult(
                tool_name=tool.name,
                status="error",
                error_code="internal",
                message=str(exc),
                attempts=attempts["n"],
            )
        )


# ---------------------------------------------------------------------------
# 数据库探测（工具层统一降级口径：DB 不可用 → ToolError(unavailable)）
# ---------------------------------------------------------------------------
def probe_db() -> None:
    """探测数据库可达性（函数）。

    说明：
        工具执行前的轻量探针（SELECT 1，复用 SessionLocal/pool_pre_ping）；
        不可达时抛 ToolError(unavailable)，由执行框架转结构化结果。

    参数：
        无。

    返回值：
        None。

    异常：
        ToolError：code=unavailable（数据库连接/查询失败）。
    """
    try:
        with SessionLocal() as session:
            session.execute(text("SELECT 1"))
    except Exception as exc:  # noqa: BLE001 —— 连接失败统一转 unavailable
        raise ToolError("unavailable", f"database unavailable: {exc}") from exc


# ---------------------------------------------------------------------------
# 内置只读工具（复用既有业务函数，不重写业务逻辑）
# ---------------------------------------------------------------------------
class RecipeSearchTool(AgentTool):
    """菜谱文本检索工具（模型类）。

    说明：
        复用 retrieval.retrieve_candidates 的文本/食材召回路径（use_vector=False
        保持只读：避免触发嵌入惰性回填写库）；DB 不可用抛 ToolError(unavailable)。

    属性：
        name：recipe_search。
        description：按查询文本检索已发布菜谱候选。
        read_only：True。
    """

    name = "recipe_search"
    description = "按自然语言查询文本检索菜谱候选列表（菜名/食材匹配），返回候选摘要。"
    read_only = True

    def parameters_schema(self) -> dict:
        """返回参数 Schema（函数）。

        返回值：
            dict：{"query": 必填字符串, "top_k": 可选整数 1-20 默认 5}。

        异常：
            无。
        """
        return {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "用户查询文本（菜名/食材/做法描述）"},
                "top_k": {"type": "integer", "minimum": 1, "maximum": 20, "default": 5, "description": "返回条数上限"},
            },
            "required": ["query"],
        }

    def execute(self, params: dict, ctx: ToolContext) -> dict:
        """执行检索（函数）。

        参数：
            params：{"query": str, "top_k"?: int}。
            ctx：执行上下文（未使用，接口一致性）。

        返回值：
            dict：{"results": 候选列表, "count": 条数}。

        异常：
            ToolError：unavailable（DB 不可用）。
        """
        probe_db()
        query = str(params.get("query") or "").strip()
        top_k = int(params.get("top_k") or 5)
        with SessionLocal() as session:
            candidates = retrieve_candidates(session, [], query_text=query, top_k=top_k, use_vector=False)
        return {"results": candidates, "count": len(candidates)}


class RecipeDetailTool(AgentTool):
    """菜谱详情查询工具（模型类）。

    说明：
        按 recipe_id 查主记录 + 食材名摘要 + 步骤数；菜谱不存在时返回
        found=False（不视为错误）；DB 不可用抛 ToolError(unavailable)。

    属性：
        name：recipe_detail。
        description：查询单个菜谱的详情（标题/食材摘要/步骤数）。
        read_only：True。
    """

    name = "recipe_detail"
    description = "按菜谱 ID 查询详情：标题、食材名摘要、步骤数、难度与耗时。"
    read_only = True

    def parameters_schema(self) -> dict:
        """返回参数 Schema（函数）。

        返回值：
            dict：{"recipe_id": 必填整数}。

        异常：
            无。
        """
        return {
            "type": "object",
            "properties": {
                "recipe_id": {"type": "integer", "description": "菜谱 ID"},
            },
            "required": ["recipe_id"],
        }

    def execute(self, params: dict, ctx: ToolContext) -> dict:
        """执行详情查询（函数）。

        参数：
            params：{"recipe_id": int}。
            ctx：执行上下文（未使用）。

        返回值：
            dict：{"found": bool, "recipe": {...}}（未找到时 recipe 为空 dict）。

        异常：
            ToolError：unavailable（DB 不可用）。
        """
        probe_db()
        recipe_id = int(params.get("recipe_id"))
        with SessionLocal() as session:
            recipe = session.execute(
                select(Recipe).where(Recipe.id == recipe_id)
            ).scalar_one_or_none()
            if recipe is None:
                return {"found": False, "recipe": {}}
            ingredient_rows = session.execute(
                select(Ingredient.name)
                .join(RecipeIngredient, RecipeIngredient.ingredient_id == Ingredient.id)
                .where(RecipeIngredient.recipe_id == recipe_id)
                .limit(10)
            ).scalars().all()
            steps_count = session.execute(
                select(func.count()).select_from(RecipeStep).where(RecipeStep.recipe_id == recipe_id)
            ).scalar_one()
        return {
            "found": True,
            "recipe": {
                "recipe_id": int(recipe.id),
                "title": recipe.title,
                "difficulty": int(recipe.difficulty),
                "time_minutes": recipe.time_minutes,
                "servings": int(recipe.servings),
                "calories_kcal": recipe.calories_kcal,
                "ingredients_preview": [str(n) for n in ingredient_rows],
                "steps_count": int(steps_count or 0),
            },
        }


class NutritionEstimateTool(AgentTool):
    """菜谱营养估算工具（模型类）。

    说明：
        复用 nutrition.estimate_recipe_nutrition 对单菜谱的确定性估算
        （菜谱缺失/无营养数据由该函数内建降级结构表达，不抛错）。

    属性：
        name：nutrition_estimate。
        description：按菜谱 ID 估算整菜与每份营养（含未纳入统计标注）。
        read_only：True。
    """

    name = "nutrition_estimate"
    description = "按菜谱 ID 估算营养：总量与每份 kcal/蛋白/脂肪/碳水/钠（估算值，含误差标注）。"
    read_only = True

    def parameters_schema(self) -> dict:
        """返回参数 Schema（函数）。

        返回值：
            dict：{"recipe_id": 必填整数}。

        异常：
            无。
        """
        return {
            "type": "object",
            "properties": {
                "recipe_id": {"type": "integer", "description": "菜谱 ID"},
            },
            "required": ["recipe_id"],
        }

    def execute(self, params: dict, ctx: ToolContext) -> dict:
        """执行营养估算（函数）。

        参数：
            params：{"recipe_id": int}。
            ctx：执行上下文（未使用）。

        返回值：
            dict：estimate_recipe_nutrition 结果结构（total/per_serving/excluded_items 等）。

        异常：
            ToolError：unavailable（DB 不可用）。
        """
        probe_db()
        recipe_id = int(params.get("recipe_id"))
        with SessionLocal() as session:
            return estimate_recipe_nutrition(session, recipe_id, servings=2)


class InventoryQueryTool(AgentTool):
    """当前用户库存只读查询工具（模型类）。

    说明：
        权限敏感：ctx.user_id 为 None 时抛 ToolError(permission_denied)（无归属
        无法过滤 owner）；查询在库状态（normal/expiring）条目并联食材名。

    属性：
        name：inventory_query。
        description：查询当前用户的在库食材列表（数量档/储存位/临期日期）。
        read_only：True。
    """

    name = "inventory_query"
    description = "查询当前用户冰箱/储藏的在库食材列表（需要用户身份，只读）。"
    read_only = True

    def parameters_schema(self) -> dict:
        """返回参数 Schema（函数）。

        返回值：
            dict：空对象 Schema（无参数）。

        异常：
            无。
        """
        return {"type": "object", "properties": {}, "required": []}

    def execute(self, params: dict, ctx: ToolContext) -> dict:
        """执行库存查询（函数）。

        参数：
            params：{}（无参数）。
            ctx：执行上下文（user_id 必需，用于 owner 过滤）。

        返回值：
            dict：{"items": [{ingredient_id/name/quantity_level/storage/expiry_date}], "count": 条数}。

        异常：
            ToolError：permission_denied（user_id 缺失）/ unavailable（DB 不可用）。
        """
        if ctx.user_id is None:
            raise ToolError("permission_denied", "inventory query requires an authenticated user_id")
        probe_db()
        with SessionLocal() as session:
            rows = session.execute(
                select(InventoryItem, Ingredient.name)
                .join(Ingredient, Ingredient.id == InventoryItem.ingredient_id)
                .where(InventoryItem.user_id == int(ctx.user_id))
                .where(InventoryItem.status.in_(("normal", "expiring")))
                .order_by(InventoryItem.expiry_date.nulls_last(), InventoryItem.id)
                .limit(50)
            ).all()
        items = [
            {
                "ingredient_id": int(item.ingredient_id),
                "name": str(name),
                "quantity_level": item.quantity_level,
                "storage": item.storage,
                "expiry_date": str(item.expiry_date) if item.expiry_date else None,
                "expiring": item.status == "expiring",
            }
            for item, name in rows
        ]
        return {"items": items, "count": len(items)}


__all__ = [
    "AgentTool",
    "InventoryQueryTool",
    "NutritionEstimateTool",
    "RecipeDetailTool",
    "RecipeSearchTool",
    "ToolContext",
    "ToolError",
    "ToolResult",
    "clear_tool_cache",
    "execute_tool",
    "probe_db",
]
