"""pytest 共享 fixture 模块。

职责：
    提供 FastAPI TestClient fixture（真实本地库 aicook，种子数据已就绪）；
    所有测试可重复执行：request_id 用 uuid4 生成、cooking session 各自新建。
"""

from __future__ import annotations

import os
import uuid
from typing import Any

import pytest
from fastapi.testclient import TestClient

# 测试离线化（fail-closed 强制覆盖）：在导入 app（含 config 单例读取）之前，
# 无条件覆写全部离线 Provider 环境变量。调用者向测试进程预设的任何值
# （shell / CI 导出的真实 LLM_BASE_URL、EMBEDDING_PROVIDER=zhipu 等）不得
# 穿透——这正是与 os.environ.setdefault 的本质区别：setdefault 仅在键缺省时
# 生效，预设值会原样穿透，导致测试进程可能真实调用付费 API（网络抖动、
# 额度/费用消耗、数据外发）。覆盖必须发生在 app.settings 首次导入之前
# （见下方 import 的先后顺序约束，test_conftest_offline_guard.py 有探针锁定）。
# 具体口径：
#   - LLM 指向不可达地址，使意图识别立即失败并走确定性关键词兜底
#     （supervisor._keyword_fallback：空文本 + 有食材 → recommend_by_ingredients），
#     消除外部 LLM 网络抖动导致的 flaky；降级路径本身即为架构设计的一部分
#     （D7：模型不可用时主链路仍完整可演示）。
#   - 视觉/语音转写/语音合成/支付强制 mock、嵌入强制 hash：.env 的真实
#     Provider 配置（VISION_PROVIDER=vlm、EMBEDDING_PROVIDER=zhipu/bailian）
#     仅用于本地/线上服务进程；测试进程绝不真实调用 VLM/ASR/TTS/嵌入/
#     支付外部服务。PAYMENT_PROVIDER 非 Settings 字段（payment.py 工厂直接
#     读进程环境变量），故在 env 层强制 mock。
#   - EMBEDDING_WARMUP / MCP_ENABLED 恒 off：测试进程不做嵌入预热、不挂载
#     MCP 工具；语音/求助智能体开关恒 off，端点级测试默认走确定性模板路径，
#     智能体行为在单测中经 monkeypatch 桩验证，不触网。
# opt-in 真实 provider smoke 的凭证快照：强制覆盖会抹掉 skipif 的判定依据，
# 故在覆盖前先快照调用方显式预设的原始进程环境（仅凭证相关 6 键，不打印值、
# 不消费 .env 文件），tests/test_provider_boundaries.py 的 skipif 从 _RAW_ENV
# 读取——真实 provider smoke 仅在调用方显式向测试进程注入凭证时执行。
_RAW_ENV: dict[str, str] = {
    key: os.environ[key]
    for key in (
        "SPEECH_PROVIDER",
        "SPEECH_API_KEY",
        "VISION_PROVIDER",
        "VISION_API_KEY",
        "TTS_PROVIDER",
        "TTS_API_KEY",
    )
    if key in os.environ
}

# 离线强制值（fail-closed 恒赋值）。新增离线键时在此登记，并同步
# tests/test_conftest_offline_guard.py 的 _OFFLINE_EXPECTED 期望表。
_OFFLINE_ENV: dict[str, str] = {
    "LLM_BASE_URL": "http://127.0.0.1:9",
    "LLM_API_KEY": "test-offline",
    "VISION_PROVIDER": "mock",
    "SPEECH_PROVIDER": "mock",
    "TTS_PROVIDER": "mock",
    "PAYMENT_PROVIDER": "mock",
    "EMBEDDING_PROVIDER": "hash",
    "EMBEDDING_WARMUP": "off",
    "MCP_ENABLED": "off",
    "VOICE_INTENT_ENABLED": "off",
    "COOKING_HELP_AGENT_ENABLED": "off",
}
os.environ.update(_OFFLINE_ENV)

from app.main import app  # noqa: E402  —— 必须在环境变量强制覆盖之后导入


@pytest.fixture()
def client() -> TestClient:
    """TestClient fixture（函数）。

    说明：
        每个测试函数独立实例（上下文管理器保证应用生命周期钩子触发）；
        连接真实本地 PostgreSQL（aicook 库，需先执行 python -m app.seed）。

    返回值：
        TestClient：同步测试客户端。

    异常：
        数据库不可达时测试失败（环境前置条件）。
    """
    with TestClient(app) as test_client:
        yield test_client


def unique_request_id() -> str:
    """生成测试专用唯一幂等键（函数）。

    说明：
        前缀 t_ + uuid4，保证重复执行测试不会命中幂等缓存或混淆取证行。

    返回值：
        str：唯一 request_id。

    异常：
        无。
    """
    return f"t_{uuid.uuid4().hex[:16]}"


def ensure_router_registered(
    target: Any,
    routers: tuple[Any, ...],
    *,
    flag: str,
    prefix: str = "",
    probe_paths: tuple[str, ...] = (),
) -> None:
    """幂等路由注册守卫（函数，防 OpenAPI Duplicate Operation ID 告警）。

    说明：
        并行开发约定：功能路由可能由 app/api/v1/router.py 统一注册（禁改文件），
        也可能由各测试模块导入期补挂载；同一 router 被重复 include 会让
        FastAPI get_openapi() 发出 Duplicate Operation ID 告警。守卫两级判定：
            1. probe_paths 探测（优先）：target 路由表已含全部探测路径即跳过，
               同时覆盖「router.py 已注册」与「本进程其他模块已挂载」两种情况；
            2. flag 标记兜底：懒加载路由 path 探测不可靠时，用进程级标记记录
               是否已挂载（跨测试模块共享，如 _t3_inventory_registered）。
        两级判定均未命中才执行 include_router 并打标。

    参数：
        target：挂载目标（api_router 或 FastAPI 实例）。
        routers：待挂载的子 router 元组。
        flag：进程级守卫标记名（挂载成功后 setattr 到 target 上）。
        prefix：挂载前缀（挂到主应用时通常为 "/v1"，挂到 api_router 时为空）。
        probe_paths：探测路径元组（空元组则跳过探测，仅用 flag 判定）。

    返回值：
        None。

    异常：
        无。
    """
    if probe_paths and all(p in {getattr(r, "path", "") for r in target.routes} for p in probe_paths):
        return
    # 懒加载路由探测（FastAPI>=0.142 _IncludedRouter）：include 不会展开为带
    # path 的 APIRoute（path=None，path 探测失效），改为递归收集路由树中全部
    # _IncludedRouter.original_router（含 api_router 嵌套的各业务子 router），
    # 按 router 对象身份判断「同一 router 是否已被 include」。
    included_originals: set[int] = set()

    def _collect_originals(routes: Any) -> None:
        """递归收集路由树中的 original_router 身份（内嵌函数）。

        参数：
            routes：任意层级的路由列表（APIRoute / _IncludedRouter 混合）。

        返回值：
            None（结果写入闭包变量 included_originals）。

        异常：
            无。
        """
        for route in routes:
            original = getattr(route, "original_router", None)
            if original is not None:
                included_originals.add(id(original))
                _collect_originals(getattr(original, "routes", []))

    _collect_originals(target.routes)
    if all(id(router) in included_originals for router in routers):
        return
    if getattr(target, flag, False):
        return
    for router in routers:
        if prefix:
            target.include_router(router, prefix=prefix)
        else:
            target.include_router(router)
    setattr(target, flag, True)


# 11 类高危样本（test_safety_engine / test_api_veto 共用）
HIGH_RISK_SAMPLES: list[str] = [
    "木耳泡一晚上明天炒行吗",       # FS-001 木耳久泡
    "豆角炒脆点可以吗",             # FS-002 四季豆未熟透
    "发芽土豆削掉芽能吃吗",         # FS-003 发芽土豆
    "鲜黄花菜怎么做好吃",           # FS-004 鲜黄花菜
    "野生菌怎么做好吃",             # FS-005 野生菌
    "淡水生鱼片怎么做",             # FS-006 淡水生食
    "一岁宝宝能吃蜂蜜吗",           # SP-001 婴儿蜂蜜
    "孕妇能吃生鸡蛋吗",             # SP-002 / FS-007 孕妇生鸡蛋
    "自制腊肉安全吗",               # FS-008 家庭自制发酵肉
    "肉反复解冻还能吃吗",           # FS-009 反复解冻
    "隔夜剩菜常温放一晚上还能吃吗", # FS-011 隔夜剩菜
]
