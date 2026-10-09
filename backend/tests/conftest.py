"""pytest 共享 fixture 模块。

职责：
    提供 FastAPI TestClient fixture（真实本地库 aicook，种子数据已就绪）；
    所有测试可重复执行：request_id 用 uuid4 生成、cooking session 各自新建。
"""

from __future__ import annotations

import os
import uuid

import pytest
from fastapi.testclient import TestClient

# 测试离线化：在导入 app（含 config 单例读取）之前将 LLM 指向不可达地址，
# 使意图识别立即失败并走确定性关键词兜底（supervisor._keyword_fallback：
# 空文本 + 有食材 → recommend_by_ingredients），消除外部 LLM 网络抖动导致的 flaky。
# 降级路径本身即为架构设计的一部分（D7：模型不可用时主链路仍完整可演示）。
os.environ.setdefault("LLM_BASE_URL", "http://127.0.0.1:9")
os.environ.setdefault("LLM_API_KEY", "test-offline")

from app.main import app  # noqa: E402  —— 必须在环境变量设置之后导入


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
