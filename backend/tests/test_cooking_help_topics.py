"""烹饪求助端点测试（求助子智能体版）。

覆盖：
    - 正常求助：测试环境智能体默认关闭（conftest 离线化）→ 单条「暂时不可用」
      诚实提示（产品决策：模板降级答非所问，已移除）；
    - 风控回归：input 闸门拦截的高危问题（SP-001 婴儿蜂蜜）仍返回 blocked
      结构（rule_id/message/空 answers）；
    - 会话归属：他人会话 404。
    （限次 3 次/会话由 test_api_personal.py::test_help_answers_block_and_limit 覆盖；
      智能体生成逻辑由 test_cooking_help_agent.py 桩测覆盖。）

说明：
    - 每个用例独立创建会话；会话创建与 help 调用必须携带同一
      X-Anonymous-Id（否则 help 因「会话不属于本人」返回 404）；
    - 自建用户用例结束后级联清理，复用种子库（recipe_id=1 番茄炒蛋）。
"""

from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.core.db import SessionLocal
from app.models import User

# 智能体不可用时的诚实提示（与端点常量口径一致）
_UNAVAILABLE = "求助助手暂时不可用，请稍后再试一次；紧急情况请先按菜谱步骤保守操作。"


def _headers(anon: str) -> dict:
    """构造带匿名身份的请求头（函数）。

    参数：
        anon：匿名会话 ID。

    返回值：
        dict：X-Anonymous-Id 请求头。

    异常：
        无。
    """
    return {"X-Anonymous-Id": anon}


def _create_session(client: TestClient, anon: str, recipe_id: int = 1) -> str:
    """创建测试烹饪会话并返回会话 ID（函数）。

    参数：
        client：TestClient fixture。
        anon：匿名会话 ID（会话归属用户，help 调用须同身份）。
        recipe_id：菜谱 ID（默认 1 = 番茄炒蛋，已发布种子数据）。

    返回值：
        str：会话 ID（字符串化主键）。

    异常：
        断言失败即测试失败。
    """
    resp = client.post(
        "/v1/cooking/sessions",
        json={"recipe_id": recipe_id, "servings": 2},
        headers=_headers(anon),
    )
    assert resp.status_code == 200
    return str(resp.json()["id"])


def _delete_user(anon: str) -> None:
    """按匿名 ID 删除用户行（级联清理自建数据）（函数）。

    参数：
        anon：匿名会话 ID。

    返回值：
        None。

    异常：
        数据库异常向上抛出。
    """
    with SessionLocal() as db:
        user = db.execute(select(User).where(User.anonymous_id == anon)).scalar_one_or_none()
        if user is not None:
            db.delete(user)
            db.commit()


@pytest.fixture()
def anon_id() -> str:
    """唯一匿名 ID fixture（函数）。

    说明：
        自建数据自清理：用例结束（含失败）后级联删除该用户。

    返回值：
        str：唯一匿名 ID。

    异常：
        清理失败向上抛出。
    """
    value = f"anon_t6help_{uuid.uuid4().hex[:10]}"
    yield value
    _delete_user(value)


def test_help_unavailable_message_when_agent_off(client: TestClient, anon_id: str) -> None:
    """智能体关闭时任意问题返回单条诚实提示，不输出模板（函数）。

    参数：
        client：TestClient fixture。
        anon_id：唯一匿名身份 fixture。

    返回值：
        None。

    异常：
        断言失败即测试失败。
    """
    sid = _create_session(client, anon_id)
    resp = client.post(
        f"/v1/cooking/sessions/{sid}/help",
        json={"question": "盐放多了怎么办"},
        headers=_headers(anon_id),
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["blocked"] is False
    assert body["answers"] == [_UNAVAILABLE]


def test_help_blocked_regression_risk_gate_first(client: TestClient, anon_id: str) -> None:
    """风控回归：高危问题仍走 input 闸门 blocked 结构（函数）。

    说明：
        SP-001（一岁宝宝吃蜂蜜）→ blocked=true、rule_id=SP-001、answers 空。

    参数：
        client：TestClient fixture。
        anon_id：唯一匿名身份 fixture。

    返回值：
        None。

    异常：
        断言失败即测试失败。
    """
    sid = _create_session(client, anon_id)
    resp = client.post(
        f"/v1/cooking/sessions/{sid}/help",
        json={"question": "一岁宝宝能吃蜂蜜吗"},
        headers=_headers(anon_id),
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["blocked"] is True
    assert body["rule_id"] == "SP-001"
    assert body["message"]
    assert body["answers"] == []


def test_help_ownership_404(client: TestClient, anon_id: str) -> None:
    """他人会话求助 404（函数）。

    参数：
        client：TestClient fixture。
        anon_id：唯一匿名身份 fixture。

    返回值：
        None。

    异常：
        断言失败即测试失败。
    """
    sid = _create_session(client, anon_id)
    other_anon = f"anon_t6help_other_{uuid.uuid4().hex[:8]}"
    try:
        resp = client.post(
            f"/v1/cooking/sessions/{sid}/help",
            json={"question": "在吗"},
            headers=_headers(other_anon),
        )
        assert resp.status_code == 404
    finally:
        _delete_user(other_anon)
