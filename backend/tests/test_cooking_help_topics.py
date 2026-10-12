"""烹饪求助关键词库测试（DEF-06）。

覆盖（spec）：
    - 10 类话题（≥8 类要求）各 1 命中断言：创建会话 → 调 help →
      blocked=false、answers 1~3 条、含该类特征词、首条不带回退前缀；
    - 未命中回退：answers 首条带「以下是本步要点：」前缀（明示回退口径）；
    - 风控回归：input 闸门拦截的高危问题（SP-001 婴儿蜂蜜）仍返回 blocked
      结构（rule_id/message/空 answers），关键词库不越权放行（口径引用
      test_api_personal.py::test_help_answers_block_and_limit）。

说明：
    - 每个用例独立创建会话（help 每会话限 3 次，单用例至多 1 次调用不会触限）；
    - 会话创建与 help 调用必须携带同一 X-Anonymous-Id（否则两次请求各自新建
      匿名用户，help 会因「会话不属于本人」返回 404）；
    - 自建用户用例结束后级联清理，复用种子库（recipe_id=1 番茄炒蛋）。
"""

from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.core.db import SessionLocal
from app.models import User


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


# 参数化用例：(求助问题, 命中话题, 回答应包含的特征词)
# 覆盖 _HELP_TOPICS 全部 10 类，每类 1 条命中断言。
_TOPIC_CASES: list[tuple[str, str, str]] = [
    ("盐放多了怎么办", "太咸", "稀释"),
    ("味道太淡了怎么办", "太淡", "生抽"),
    ("锅底糊了怎么办", "糊锅", "关火"),
    ("糖色炒苦了还能救吗", "发苦", "重炒"),
    ("家里没有料酒了怎么办", "缺调料", "替代"),
    ("怎么判断油几成热", "火候", "成热"),
    ("被油溅到烫伤了怎么办", "溅油烫伤", "凉水"),
    ("菜太辣了怎么办", "太辣", "牛奶"),
    ("鱼腥味重怎么去腥", "腥味", "去腥"),
    ("鸡蛋粘锅了怎么办", "粘锅", "凉油"),
]


@pytest.mark.parametrize(("question", "topic", "keyword"), _TOPIC_CASES)
def test_help_topic_hit(client: TestClient, anon_id: str, question: str, topic: str, keyword: str) -> None:
    """关键词库逐类命中：回答为该话题针对性要点而非步骤上下文（函数）。

    参数：
        client：TestClient fixture。
        anon_id：唯一匿名身份 fixture。
        question：求助问题（含该话题关键词）。
        topic：话题名（仅用于失败时定位）。
        keyword：回答应包含的特征词。

    返回值：
        None。

    异常：
        断言失败即测试失败。
    """
    sid = _create_session(client, anon_id)
    resp = client.post(
        f"/v1/cooking/sessions/{sid}/help",
        json={"question": question},
        headers=_headers(anon_id),
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["blocked"] is False, f"话题「{topic}」不应被风控拦截"
    answers = body["answers"]
    # 回答 1~3 条（2 条要点 + 可选 1 条当前步骤提示），且含该类特征词
    assert 1 <= len(answers) <= 3
    assert any(keyword in a for a in answers), f"话题「{topic}」回答未含特征词「{keyword}」：{answers}"
    # 命中路径不走步骤回退前缀
    assert not answers[0].startswith("以下是本步要点")


def test_help_fallback_prefix_when_no_topic_hit(client: TestClient, anon_id: str) -> None:
    """未命中关键词库 → 回退当前步骤要点，首条带「以下是本步要点：」前缀（函数）。

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
        json={"question": "这一步要翻炒多久"},
        headers=_headers(anon_id),
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["blocked"] is False
    assert body["answers"], "回退路径仍应有步骤要点回答"
    assert body["answers"][0].startswith("以下是本步要点：")
    # 前缀之后仍是原有步骤结构化信息（第 1 步描述）
    assert "当前第 1 步" in body["answers"][0]


def test_help_blocked_regression_risk_gate_first(client: TestClient, anon_id: str) -> None:
    """风控回归：高危问题仍走 input 闸门 blocked 结构，不被关键词库放行（函数）。

    说明：
        口径与 test_api_personal.py::test_help_answers_block_and_limit 一致：
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
