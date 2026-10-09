"""进程内幂等缓存模块（spec D6：阶段一不引入 Redis）。

职责：
    为 POST /v1/recommend 与 POST /v1/ask 提供基于 request_id 的幂等能力：
    - 缓存键 = HTTP 方法 + 路径 + request_id（同一 request_id 重复提交直接返回首次响应）；
    - 进程内 dict + 过期时间戳实现 TTL（默认 600s），过期条目惰性清理；
    - 线程安全（threading.Lock 保护读写）。

边界说明：
    - 仅适用于单进程部署（uvicorn 单 worker，阶段一演示形态）；
    - 多 worker / 重启后缓存失效，此时重复 request_id 会重新执行编排（编排层无副作用，
      不会产生资源重复扣减，幂等语义降级但不破坏正确性）。
"""

from __future__ import annotations

import threading
import time

from app.core.logging import new_request_id

# 缓存条目 TTL（秒）：spec 5.6 要求 600s
_TTL_SECONDS = 600.0

# 缓存上限（条）：超出时批量清理过期与最旧条目，防止演示环境内存无限增长
_MAX_ENTRIES = 2000

# 全局缓存：{(method, path, request_id): (expires_at, payload_dict)}
_store: dict[tuple[str, str, str], tuple[float, dict]] = {}
_lock = threading.Lock()


def _cleanup_locked(now: float) -> None:
    """清理过期与超限条目（函数）。

    说明：
        仅在持有 _lock 时调用；先删除全部过期条目，若仍超限则按过期时间淘汰最旧一半。

    参数：
        now：当前单调时间戳（time.monotonic）。

    返回值：
        None。

    异常：
        无。
    """
    # 1) 惰性清理过期条目
    expired = [key for key, (expires_at, _) in _store.items() if expires_at <= now]
    for key in expired:
        _store.pop(key, None)
    # 2) 超限时按过期时间淘汰最旧的一半（演示环境简单策略即可）
    if len(_store) > _MAX_ENTRIES:
        ordered = sorted(_store.items(), key=lambda kv: kv[1][0])
        for key, _ in ordered[: len(ordered) // 2]:
            _store.pop(key, None)


def make_request_id() -> str:
    """生成幂等键（函数）。

    说明：
        POST /v1/recommend 与 /v1/ask 未显式携带 request_id 时由后端自动生成，
        格式复用日志中间件的 new_request_id（req_ 前缀）。

    返回值：
        str：形如 req_xxxxxxxx 的幂等键。

    异常：
        无。
    """
    return new_request_id()


def get_cached_response(method: str, path: str, request_id: str | None) -> dict | None:
    """读取幂等缓存响应（函数）。

    说明：
        命中且未过期时返回首次响应体（调用方应以 X-Idempotent-Replay: true 头返回）；
        未命中 / request_id 缺失 / 已过期均返回 None（正常执行业务）。

    参数：
        method：HTTP 方法（大写，如 POST）。
        path：请求路径（如 /v1/recommend）。
        request_id：幂等键（可 None）。

    返回值：
        dict | None：缓存响应体或 None。

    异常：
        无。
    """
    if not request_id:
        return None
    key = (method.upper(), path, str(request_id))
    now = time.monotonic()
    with _lock:
        _cleanup_locked(now)
        entry = _store.get(key)
        if entry is None:
            return None
        expires_at, payload = entry
        if expires_at <= now:
            _store.pop(key, None)
            return None
        return payload


def store_response(method: str, path: str, request_id: str | None, payload: dict) -> None:
    """写入幂等缓存响应（函数）。

    说明：
        request_id 缺失时不缓存（幂等以 request_id 为前提）；
        缓存响应体为 dict（JSON 可序列化），读取方直接原样返回。

    参数：
        method：HTTP 方法（大写）。
        path：请求路径。
        request_id：幂等键（可 None）。
        payload：响应体 dict。

    返回值：
        None。

    异常：
        无（缓存失败静默忽略，不影响正常响应）。
    """
    if not request_id:
        return
    key = (method.upper(), path, str(request_id))
    now = time.monotonic()
    with _lock:
        _cleanup_locked(now)
        # 已存在时保留首次响应（幂等语义：首次执行结果不被覆盖）
        _store.setdefault(key, (now + _TTL_SECONDS, payload))
