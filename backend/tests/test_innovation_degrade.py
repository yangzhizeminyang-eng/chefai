"""创新生成 LLM 硬超时降级测试（P1 DEF-01 配套）。

覆盖：
    - LLM 表达超过硬超时（LLM_HARD_TIMEOUT_SECONDS 被 monkeypatch 调小以模拟
      慢调用）→ 接口仍成功返回完整创新菜，basis.generated_by == "template"
      （规则模板降级：配比模板量化用量 + 技法白名单 + 搭配依据，响应结构不变）；
    - LLM 调用抛 LLMError（异常路径）→ 同样降级 template；
    - LLM 正常返回合规 JSON → generated_by == "llm"（不降级）。

数据约定：
    与 test_api_innovation 同口径：真实本地库（aicook，种子数据就绪），测试用户
    自建自清理（innovation_recipe 随 user 级联删除）；不触碰风控闸门与拦截语义。
"""

from __future__ import annotations

import json
import time
import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.ability.llm import LLMError, LLMResult
from app.api.v1 import innovation as innovation_api
from app.api.v1.router import api_router
from app.core.db import SessionLocal
from app.graph.subgraphs import innovation as innovation_subgraph
from app.models import Family, User

# 并行开发约定：与 test_api_innovation 一致，router 未注册时补注册（进程级守卫防重复）
if not getattr(api_router, "_t7_innovation_registered", False):
    api_router.include_router(innovation_api.router)
    api_router._t7_innovation_registered = True

# 模糊用量违禁词（与子图 _VAGUE_WORDS 同口径的断言子集）
_VAGUE_WORDS: tuple[str, ...] = ("适量", "少许")


class _SlowLLMClient:
    """慢 LLM 替身（模型类）：chat 阻塞指定秒数后返回，用于触发硬超时路径。

    属性：
        _delay：chat 阻塞秒数（远大于被调小后的硬超时）。
    """

    def __init__(self, delay: float) -> None:
        """构造替身（函数）。

        参数：
            delay：chat 阻塞秒数。

        返回值：
            None。

        异常：
            无。
        """
        self._delay = delay

    def chat(self, system: str, user: str, temperature: float = 0.2) -> LLMResult:
        """模拟慢补全（函数）：阻塞 delay 秒后返回占位结果。

        参数：
            system：系统提示词（替身不消费）。
            user：用户消息（替身不消费）。
            temperature：采样温度（替身不消费）。

        返回值：
            LLMResult：占位结果（content 为空 JSON，正常路径下不会被使用——
            调用方会在超时后放弃等待）。

        异常：
            无。
        """
        time.sleep(self._delay)
        return LLMResult(content="{}", prompt_tokens=1, completion_tokens=1, model="fake-slow")


class _ErrorLLMClient:
    """抛错 LLM 替身（模型类）：chat 直接抛 LLMError，用于异常降级路径。"""

    def chat(self, system: str, user: str, temperature: float = 0.2) -> LLMResult:
        """模拟调用失败（函数）。

        参数：
            system：系统提示词（替身不消费）。
            user：用户消息（替身不消费）。
            temperature：采样温度（替身不消费）。

        返回值：
            LLMResult：永不返回。

        异常：
            LLMError：恒抛出（模拟网络级失败）。
        """
        raise LLMError("simulated llm failure")


class _FakeSuccessLLMClient:
    """成功 LLM 替身（模型类）：返回 100% 量化的合规创新菜 JSON。"""

    # 合规草稿：用量数值+白名单单位、步骤含正整数 duration_sec、无模糊词
    _PAYLOAD: dict = {
        "name": "番茄滑蛋",
        "ingredients": [
            {"name": "西红柿", "amount": 200, "unit": "g"},
            {"name": "鸡蛋", "amount": 3, "unit": "个"},
            {"name": "食用油", "amount": 15, "unit": "ml"},
            {"name": "盐", "amount": 2, "unit": "g"},
        ],
        "steps": [
            {"no": 1, "description": "西红柿切块，鸡蛋打散备用。", "duration_sec": 90, "tips": "鸡蛋加一勺清水更嫩"},
            {"no": 2, "description": "热锅倒入食用油15ml，下蛋液炒散盛出。", "duration_sec": 60, "tips": None},
            {"no": 3, "description": "下西红柿翻炒240秒后回锅鸡蛋，加盐2g拌匀出锅。", "duration_sec": 240, "tips": None},
        ],
    }

    def chat(self, system: str, user: str, temperature: float = 0.2) -> LLMResult:
        """返回合规草稿（函数）。

        参数：
            system：系统提示词（替身不消费）。
            user：用户消息（替身不消费）。
            temperature：采样温度（替身不消费）。

        返回值：
            LLMResult：content 为合规 JSON 草稿。

        异常：
            无。
        """
        return LLMResult(
            content=json.dumps(self._PAYLOAD, ensure_ascii=False),
            prompt_tokens=120,
            completion_tokens=260,
            model="fake-ok",
        )


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


def _anon() -> str:
    """生成唯一测试匿名 ID（函数）。

    返回值：
        str：anon_def01_ 前缀唯一 ID。

    异常：
        无。
    """
    return f"anon_def01_{uuid.uuid4().hex[:10]}"


def _delete_user(anon: str) -> None:
    """按匿名 ID 删除用户行（级联清理自建数据）（函数）。

    说明：
        与 test_api_innovation 同口径：先删 family 行（外键无 DB 级联），
        innovation_recipe 随 user 的 DB 级联删除。

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
            families = db.execute(select(Family).where(Family.user_id == int(user.id))).scalars().all()
            for family in families:
                db.delete(family)
            db.flush()
            db.delete(user)
            db.commit()


@pytest.fixture()
def anon_id() -> str:
    """唯一匿名 ID fixture（函数，teardown 级联清理）。

    返回值：
        str：唯一匿名 ID。

    异常：
        清理失败向上抛出。
    """
    value = _anon()
    yield value
    _delete_user(value)


def _generate(client: TestClient, anon: str) -> dict:
    """调用创新生成接口并返回响应体（函数）。

    参数：
        client：TestClient fixture。
        anon：匿名身份。

    返回值：
        dict：生成成功响应体（{ok, recipe, request_id, trace_id}）。

    异常：
        断言失败即测试失败。
    """
    resp = client.post(
        "/v1/innovation/generate",
        json={"ingredients": ["鸡蛋", "西红柿"]},
        headers=_headers(anon),
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["ok"] is True
    return body


def _assert_template_recipe_shape(recipe: dict) -> None:
    """断言降级模板创新菜结构完整且满足红线（函数）。

    说明：
        覆盖 DEF-01 断言清单：recipe 结构完整（name/ingredients/steps/basis/
        nutrition 字段在）、basis.generated_by == "template"、is_ai_innovated
        恒 true、visibility=private、status=generated、用量 100% 量化（数值 +
        白名单单位，全文无「适量/少许」）、步骤含正整数 duration_sec、营养含
        excluded_items 与 estimate_note。

    参数：
        recipe：生成响应中的 recipe 结构。

    返回值：
        None。

    异常：
        断言失败即测试失败。
    """
    # 结构完整
    for key in ("name", "ingredients", "steps", "basis", "nutrition"):
        assert key in recipe, f"recipe 缺少字段 {key}"
    assert recipe["name"]
    assert recipe["ingredients"]
    assert recipe["steps"]

    # 🔴 标识红线（不得改动语义）
    assert recipe["is_ai_innovated"] is True
    assert recipe["visibility"] == "private"
    assert recipe["status"] == "generated"
    assert recipe["disclaimer"]

    # 降级来源标注
    basis = recipe["basis"]
    for key in ("pairings", "properties", "techniques_whitelist", "generated_by"):
        assert key in basis, f"basis 缺少字段 {key}"
    assert basis["generated_by"] == "template"
    # 搭配依据可追溯（鸡蛋×西红柿 为种子 recommend 规则，结构不变）
    assert any(p["relation"] == "recommend" for p in basis["pairings"])

    # 用量 100% 量化（数值 + 非空单位）
    for item in recipe["ingredients"]:
        assert isinstance(item["amount"], (int, float)) and not isinstance(item["amount"], bool)
        assert item["amount"] > 0
        assert item["unit"]

    # 步骤可执行（含时长秒）
    for step in recipe["steps"]:
        assert isinstance(step["duration_sec"], (int, float)) and not isinstance(step["duration_sec"], bool)
        assert step["duration_sec"] > 0
        assert step["description"]

    # 全文无模糊用量词
    full_text = json.dumps(recipe, ensure_ascii=False)
    for word in _VAGUE_WORDS:
        assert word not in full_text, f"降级产出含模糊用量词「{word}」：{full_text}"

    # 营养结构（缺失项 excluded_items 标注，不按 0 计）
    nutrition = recipe["nutrition"]
    assert "excluded_items" in nutrition
    assert nutrition.get("estimate_note")


# ---------------------------------------------------------------------------
# 1) LLM 慢调用超过硬超时 → 降级 template（DEF-01 核心场景）
# ---------------------------------------------------------------------------
def test_llm_hard_timeout_degrades_to_template(client: TestClient, monkeypatch, anon_id: str) -> None:
    """LLM 表达超过硬超时 → 200/201 成功返回模板降级结果（函数）。

    说明：
        monkeypatch 将硬超时调小为 0.3s，LLM 替身阻塞 2s → future.result 超时
        抛 LLMError → 规则模板降级；响应结构完整、generated_by == "template"。

    参数：
        client：TestClient fixture。
        monkeypatch：pytest monkeypatch fixture。
        anon_id：唯一匿名身份 fixture。

    返回值：
        None。

    异常：
        断言失败即测试失败。
    """
    monkeypatch.setattr(innovation_subgraph, "LLM_HARD_TIMEOUT_SECONDS", 0.3)
    monkeypatch.setattr(innovation_subgraph, "get_llm_client", lambda: _SlowLLMClient(delay=2.0))

    body = _generate(client, anon_id)
    _assert_template_recipe_shape(body["recipe"])


# ---------------------------------------------------------------------------
# 2) LLM 抛异常 → 降级 template（异常路径）
# ---------------------------------------------------------------------------
def test_llm_error_degrades_to_template(client: TestClient, monkeypatch, anon_id: str) -> None:
    """LLM 调用抛 LLMError → 规则模板降级（函数）。

    参数：
        client：TestClient fixture。
        monkeypatch：pytest monkeypatch fixture。
        anon_id：唯一匿名身份 fixture。

    返回值：
        None。

    异常：
        断言失败即测试失败。
    """
    monkeypatch.setattr(innovation_subgraph, "get_llm_client", lambda: _ErrorLLMClient())

    body = _generate(client, anon_id)
    _assert_template_recipe_shape(body["recipe"])


# ---------------------------------------------------------------------------
# 3) LLM 正常返回合规 JSON → generated_by == "llm"（不降级）
# ---------------------------------------------------------------------------
def test_llm_success_generated_by_llm(client: TestClient, monkeypatch, anon_id: str) -> None:
    """LLM 正常返回合规草稿 → generated_by == "llm"（函数）。

    参数：
        client：TestClient fixture。
        monkeypatch：pytest monkeypatch fixture。
        anon_id：唯一匿名身份 fixture。

    返回值：
        None。

    异常：
        断言失败即测试失败。
    """
    monkeypatch.setattr(innovation_subgraph, "get_llm_client", lambda: _FakeSuccessLLMClient())

    body = _generate(client, anon_id)
    recipe = body["recipe"]
    assert recipe["basis"]["generated_by"] == "llm"
    # LLM 输出同样必须满足结构完整与量化红线
    assert recipe["name"] == "番茄滑蛋"
    for item in recipe["ingredients"]:
        assert isinstance(item["amount"], (int, float)) and item["amount"] > 0
        assert item["unit"]
    full_text = json.dumps(recipe, ensure_ascii=False)
    for word in _VAGUE_WORDS:
        assert word not in full_text
