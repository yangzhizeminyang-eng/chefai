"""真实视觉模型 provider（VLM）单元测试（spec：integrate-vlm-report-actions A 节）。

覆盖：
    - JSON 容错解析 _extract_json_array：```json 围栏剥离 / 前后噪声文本 /
      非法输出抛 LLMError（走路由降级）；
    - 预处理纯函数：_strip_quantity 量词剥离（"鸡蛋 6个"→鸡蛋）、_is_noise
      噪声词 / 超长 / 纯 ASCII 品牌样拦截；
    - 名称归一化三路：ingredient.name 精确命中 high / IngredientAlias.alias
      命中 high / 向量最近邻阈值边界（≥0.85 high、0.60~0.85 low、<0.60 丢弃）；
    - 同名去重 + VISION_MAX_ITEMS 截断；
    - recognize 全链路（mock chat_with_image）：围栏输出解析 / VLM 异常向上
      传播（路由层降级）/ 空数组与空字节返回 []；
    - 工厂：vlm 分支 / 未知取值回退 mock；
    - RL-3 红线：system prompt 显式禁止可食性/安全性结论；VLM 输出混入
      「可以吃」等字段时 provider 输出仅含 name/confidence/ingredient_id。

说明：
    不调真实 API——chat_with_image 用 monkeypatch 桩替换；归一化用例通过
    临时 ingredient 行（uuid 后缀防种子冲突）自备数据，测试后清理。
"""

from __future__ import annotations

import uuid

import pytest

from app.ability import providers as providers_module
from app.ability.embedding import EmbeddingProvider
from app.ability.llm import LLMError, LLMResult
from app.ability.providers import (
    MOCK_ASR_TEXT,  # noqa: F401  —— 回归确认 __all__ 未破坏既有导出
    VLM_SYSTEM_PROMPT,
    VLM_USER_PROMPT,
    MockVisionProvider,
    MultimodalVisionProvider,
    _build_vision_provider,
    _extract_json_array,
    _is_noise,
    _strip_quantity,
)
from app.core.config import settings
from app.core.db import SessionLocal
from app.models import Ingredient, IngredientAlias


class _StubLLMClient:
    """桩 LLM 客户端（测试用）：chat_with_image 返回预设文本或抛预设异常（模型类）。

    属性：
        calls：每次调用的入参记录（断言 system/user/图片字节传递正确）。
    """

    def __init__(self, content: str = "", error: Exception | None = None) -> None:
        """构造桩客户端（函数）。

        参数：
            content：预设 VLM 输出文本。
            error：预设异常（非 None 时调用即抛出）。

        返回值：
            None。

        异常：
            无。
        """
        self._content = content
        self._error = error
        self.calls: list[dict] = []

    def chat_with_image(
        self,
        system: str,
        user: str,
        image_bytes: bytes,
        mime: str = "image/jpeg",
        temperature: float = 0.1,
        max_tokens: int = 800,
    ) -> LLMResult:
        """模拟视觉补全调用（函数）。

        参数：
            system：系统提示词（透传统计）。
            user：用户消息（透传统计）。
            image_bytes：图片字节（透传统计）。
            mime / temperature / max_tokens：与真实签名对齐（忽略）。

        返回值：
            LLMResult：预设文本包装结果（model 固定 stub-vlm）。

        异常：
            LLMError：构造时注入 error 非空时抛出。
        """
        self.calls.append({"system": system, "user": user, "image_bytes": image_bytes})
        if self._error is not None:
            raise self._error
        return LLMResult(content=self._content, prompt_tokens=10, completion_tokens=5, model="stub-vlm")


class _StubEmbedding(EmbeddingProvider):
    """桩嵌入提供方（测试用）：按文本查表返回预设向量，未映射返回全零（模型类）。

    说明：
        全零向量与任意向量点积为 0，等效「库内其余种子食材不参与最近邻」，
        使阈值边界完全由测试构造的映射控制。
    """

    def __init__(self, mapping: dict[str, list[float]]) -> None:
        """构造桩嵌入（函数）。

        参数：
            mapping：文本 → 预设归一化向量（等长，点积即余弦）。

        返回值：
            None。

        异常：
            无。
        """
        self._mapping = mapping

    def embed(self, texts: list[str]) -> list[list[float]]:
        """查表批量嵌入（函数）。

        参数：
            texts：文本列表。

        返回值：
            list[list[float]]：预设向量列表（未映射文本为全零，与映射等长）。

        异常：
            无。
        """
        return [list(self._mapping.get(text, [0.0, 0.0])) for text in texts]


@pytest.fixture()
def temp_ingredient():
    """插入临时食材 + 别名并在测试后清理（fixture）。

    说明：
        名字带 uuid 后缀防与种子冲突；返回 (ingredient_id, name, alias)；
        前后清空 providers 的库内向量缓存，防跨用例串扰。

    返回值：
        tuple[int, str, str]：(临时食材 ID, 食材名, 别名文本)。

    异常：
        数据库不可达时测试失败（环境前置条件）。
    """
    suffix = uuid.uuid4().hex[:6]
    name = f"测试苹果{suffix}"
    alias_text = f"红富士{suffix}"
    with SessionLocal() as session:
        row = Ingredient(name=name, category="veg")
        session.add(row)
        session.flush()
        alias_row = IngredientAlias(ingredient_id=int(row.id), alias=alias_text)
        session.add(alias_row)
        session.commit()
        ing_id = int(row.id)
    providers_module._ING_VEC_CACHE.clear()
    try:
        yield ing_id, name, alias_text
    finally:
        with SessionLocal() as session:
            row = session.get(Ingredient, ing_id)
            if row is not None:
                session.delete(row)  # 别名随食材级联删除
                session.commit()
        providers_module._ING_VEC_CACHE.clear()


@pytest.fixture()
def temp_ingredients_4():
    """插入 4 个临时食材并在测试后清理（fixture，供 MAX_ITEMS 截断用例）。

    返回值：
        tuple[list[int], list[str]]：(临时食材 ID 列表, 名字列表，保序)。

    异常：
        数据库不可达时测试失败（环境前置条件）。
    """
    suffix = uuid.uuid4().hex[:6]
    names = [f"截断食材{suffix}{i}" for i in range(4)]
    with SessionLocal() as session:
        rows = [Ingredient(name=n, category="veg") for n in names]
        session.add_all(rows)
        session.flush()
        ids = [int(row.id) for row in rows]
        session.commit()
    providers_module._ING_VEC_CACHE.clear()
    try:
        yield ids, names
    finally:
        with SessionLocal() as session:
            for ing_id in ids:
                row = session.get(Ingredient, ing_id)
                if row is not None:
                    session.delete(row)
            session.commit()
        providers_module._ING_VEC_CACHE.clear()


# ---------------------------------------------------------------------------
# JSON 容错解析（独立纯函数）
# ---------------------------------------------------------------------------


def test_extract_json_array_fenced() -> None:
    """```json 围栏包裹的输出可正确剥离解析（函数）。

    异常：
        断言失败即测试失败。
    """
    text = '好的，识别结果如下：\n```json\n[{"name": "番茄"}, {"name": "鸡蛋"}]\n```\n希望有帮助。'
    assert _extract_json_array(text) == [{"name": "番茄"}, {"name": "鸡蛋"}]


def test_extract_json_array_noise_text() -> None:
    """前后噪声文本（无围栏）按首个 '[' 到最后一个 ']' 截取（函数）。

    异常：
        断言失败即测试失败。
    """
    text = '识别结果：[{"name": "土豆"}]，请确认。以上仅供参考。'
    assert _extract_json_array(text) == [{"name": "土豆"}]


def test_extract_json_array_invalid_raises() -> None:
    """无数组结构 / 非法 JSON 统一抛 LLMError（函数）。

    说明：
        LLMError 由路由层既有降级捕获（degraded=true 不扣额度）。

    异常：
        断言失败即测试失败。
    """
    with pytest.raises(LLMError):
        _extract_json_array("抱歉，我认不出这张照片里的食材。")
    with pytest.raises(LLMError):
        _extract_json_array("[{broken json")
    with pytest.raises(LLMError):
        _extract_json_array('{"name": "顶层不是数组"}')


# ---------------------------------------------------------------------------
# 预处理纯函数：量词剥离 / 噪声过滤
# ---------------------------------------------------------------------------


def test_strip_quantity_cases() -> None:
    """首尾「数量+量词」片段被剥离，正常名字不受影响（函数）。

    异常：
        断言失败即测试失败。
    """
    assert _strip_quantity("鸡蛋 6个") == "鸡蛋"
    assert _strip_quantity("一盒鸡蛋") == "鸡蛋"
    assert _strip_quantity("6个鸡蛋") == "鸡蛋"
    assert _strip_quantity("牛奶 250ml") == "牛奶"
    assert _strip_quantity("猪肉500g") == "猪肉"
    assert _strip_quantity("三两猪肉") == "猪肉"
    assert _strip_quantity("番茄") == "番茄"
    assert _strip_quantity("小葱") == "小葱"
    assert _strip_quantity("6个") == ""  # 剥完为空由调用方丢弃


def test_is_noise_cases() -> None:
    """噪声词 / 超长 / 纯 ASCII 品牌样均被拦截（函数）。

    异常：
        断言失败即测试失败。
    """
    assert _is_noise("保鲜盒") is True
    assert _is_noise("冰箱贴") is True
    assert _is_noise("塑料袋装的菜") is True
    assert _is_noise("这是一个非常长的非食材描述文本") is True  # 长度 >12
    assert _is_noise("Coca-Cola") is True  # 纯 ASCII 且长度 >6
    assert _is_noise("番茄") is False
    assert _is_noise("土豆") is False


# ---------------------------------------------------------------------------
# 名称归一化三路（精确 / 别名 / 向量阈值边界）
# ---------------------------------------------------------------------------


def test_normalize_exact_and_alias_hits(temp_ingredient) -> None:
    """精确命中与别名命中均 high 且带表 ID，重复名只留第一个（函数）。

    参数：
        temp_ingredient：临时食材 fixture。

    返回值：
        None。

    异常：
        断言失败即测试失败。
    """
    ing_id, name, alias_text = temp_ingredient
    items = MultimodalVisionProvider()._normalize(
        [{"name": name}, {"name": alias_text}, {"name": name}]
    )
    assert [(i.name, i.confidence) for i in items] == [
        (name, "high"),
        (alias_text, "high"),
    ]
    assert all(i.ingredient_id == ing_id for i in items)


def test_normalize_quantity_stripped_then_exact_hit(temp_ingredient) -> None:
    """「名字 + 数量量词」剥后精确命中（如「测试苹果xx 6个」→ 测试苹果xx）（函数）。

    参数：
        temp_ingredient：临时食材 fixture。

    返回值：
        None。

    异常：
        断言失败即测试失败。
    """
    ing_id, name, _alias = temp_ingredient
    items = MultimodalVisionProvider()._normalize([{"name": f"{name} 6个"}, {"name": f"一盒{name}"}])
    # 两项剥后同名 → 去重只留第一个
    assert [(i.name, i.confidence, i.ingredient_id) for i in items] == [(name, "high", ing_id)]


def test_normalize_noise_entries_filtered() -> None:
    """噪声条目（保鲜盒/冰箱/超长描述）全部被拦截，输出空列表（函数）。

    返回值：
        None。

    异常：
        断言失败即测试失败。
    """
    items = MultimodalVisionProvider()._normalize(
        [{"name": "保鲜盒"}, {"name": "冰箱"}, {"name": "这是一段超长的非食材场景描述文字"}]
    )
    assert items == []


def test_normalize_vector_thresholds(monkeypatch: pytest.MonkeyPatch, temp_ingredient) -> None:
    """向量最近邻三档阈值边界：0.9→high、0.7→low、0.3→丢弃（函数）。

    参数：
        monkeypatch：替换嵌入提供方为可控桩。
        temp_ingredient：临时食材 fixture（库内唯一可比对项）。

    返回值：
        None。

    异常：
        断言失败即测试失败。
    """
    ing_id, name, _alias = temp_ingredient
    mapping = {
        name: [1.0, 0.0],
        f"红苹果{ing_id}": [0.9, 0.435889894354067],   # 点积 0.90 ≥0.85 → high
        f"雪梨{ing_id}": [0.7, 0.714142842854285],     # 点积 0.70 0.60~0.85 → low
        f"无关词q{ing_id}": [0.3, 0.9539392014169457], # 点积 0.30 <0.60 → 丢弃
    }
    monkeypatch.setattr(providers_module, "get_embedding_provider", lambda: _StubEmbedding(mapping))
    items = MultimodalVisionProvider()._normalize(
        [
            {"name": f"红苹果{ing_id}"},
            {"name": f"雪梨{ing_id}"},
            {"name": f"无关词q{ing_id}"},
        ]
    )
    got = {(i.name, i.confidence, i.ingredient_id) for i in items}
    assert (f"红苹果{ing_id}", "high", ing_id) in got
    assert (f"雪梨{ing_id}", "low", ing_id) in got
    assert all(i.name != f"无关词q{ing_id}" for i in items), "相似度 <0.60 的库外名必须丢弃"


def test_normalize_truncates_to_max_items(
    monkeypatch: pytest.MonkeyPatch, temp_ingredients_4
) -> None:
    """识别条目按 settings.VISION_MAX_ITEMS 保序截断（函数）。

    参数：
        monkeypatch：临时改小 VISION_MAX_ITEMS=2。
        temp_ingredients_4：4 个临时食材 fixture。

    返回值：
        None。

    异常：
        断言失败即测试失败。
    """
    _ids, names = temp_ingredients_4
    monkeypatch.setattr(settings, "VISION_MAX_ITEMS", 2)
    items = MultimodalVisionProvider()._normalize([{"name": n} for n in names])
    assert [i.name for i in items] == names[:2]
    assert all(i.confidence == "high" for i in items)


# ---------------------------------------------------------------------------
# recognize 全链路（mock chat_with_image，不调真实 API）
# ---------------------------------------------------------------------------


def test_recognize_parses_fenced_output(monkeypatch: pytest.MonkeyPatch, temp_ingredient) -> None:
    """全链路：VLM 围栏输出 → 解析 → 精确/别名命中（函数）。

    说明：
        同时断言 chat_with_image 收到的 system/user/图片字节正确。

    参数：
        monkeypatch：替换 get_llm_client 为桩。
        temp_ingredient：临时食材 fixture。

    返回值：
        None。

    异常：
        断言失败即测试失败。
    """
    ing_id, name, alias_text = temp_ingredient
    content = (
        f"识别完成：\n```json\n[{{\"name\": \"{name}\"}}, {{\"name\": \"{alias_text}\"}}]\n```\n以上。"
    )
    stub = _StubLLMClient(content=content)
    monkeypatch.setattr(providers_module, "get_llm_client", lambda: stub)
    items = MultimodalVisionProvider().recognize(b"fake-image-bytes")
    assert [(i.name, i.confidence) for i in items] == [(name, "high"), (alias_text, "high")]
    assert all(i.ingredient_id == ing_id for i in items)
    assert stub.calls[0]["system"] == VLM_SYSTEM_PROMPT
    assert stub.calls[0]["user"] == VLM_USER_PROMPT
    assert stub.calls[0]["image_bytes"] == b"fake-image-bytes"


def test_recognize_vlm_error_propagates(monkeypatch: pytest.MonkeyPatch) -> None:
    """VLM 调用失败异常向上传播（路由层据此降级 degraded=true 不扣额度）（函数）。

    参数：
        monkeypatch：替换 get_llm_client 为恒抛异常桩。

    返回值：
        None。

    异常：
        断言失败即测试失败。
    """
    stub = _StubLLMClient(error=LLMError("network unreachable"))
    monkeypatch.setattr(providers_module, "get_llm_client", lambda: stub)
    with pytest.raises(LLMError):
        MultimodalVisionProvider().recognize(b"fake-image-bytes")


def test_recognize_invalid_text_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    """VLM 输出无 JSON 数组时抛 LLMError 走降级（函数）。

    参数：
        monkeypatch：替换 get_llm_client 为纯文本桩。

    返回值：
        None。

    异常：
        断言失败即测试失败。
    """
    stub = _StubLLMClient(content="这张照片太模糊了，我认不出来。")
    monkeypatch.setattr(providers_module, "get_llm_client", lambda: stub)
    with pytest.raises(LLMError):
        MultimodalVisionProvider().recognize(b"fake-image-bytes")


def test_recognize_empty_array(monkeypatch: pytest.MonkeyPatch) -> None:
    """VLM 输出空数组时 recognize 返回 []（走全低置信不扣额度路径）（函数）。

    参数：
        monkeypatch：替换 get_llm_client 为空数组桩。

    返回值：
        None。

    异常：
        断言失败即测试失败。
    """
    stub = _StubLLMClient(content="[]")
    monkeypatch.setattr(providers_module, "get_llm_client", lambda: stub)
    assert MultimodalVisionProvider().recognize(b"fake-image-bytes") == []


def test_recognize_empty_bytes() -> None:
    """空图片字节直接返回 []（不发 VLM 请求）（函数）。

    返回值：
        None。

    异常：
        断言失败即测试失败。
    """
    assert MultimodalVisionProvider().recognize(b"") == []


# ---------------------------------------------------------------------------
# 工厂分支
# ---------------------------------------------------------------------------


def test_factory_vlm_branch(monkeypatch: pytest.MonkeyPatch) -> None:
    """VISION_PROVIDER=vlm 构建真实视觉 provider（函数）。

    参数：
        monkeypatch：临时改写 settings.VISION_PROVIDER（工厂现读 settings 而非
        os.environ，setenv 不再生效）。

    返回值：
        None。

    异常：
        断言失败即测试失败。
    """
    monkeypatch.setattr(settings, "VISION_PROVIDER", "vlm")
    assert isinstance(_build_vision_provider(), MultimodalVisionProvider)


def test_factory_mock_branch(monkeypatch: pytest.MonkeyPatch) -> None:
    """VISION_PROVIDER=mock 构建 mock provider（回退口径不变）（函数）。

    参数：
        monkeypatch：临时改写 settings.VISION_PROVIDER。

    返回值：
        None。

    异常：
        断言失败即测试失败。
    """
    monkeypatch.setattr(settings, "VISION_PROVIDER", "mock")
    assert isinstance(_build_vision_provider(), MockVisionProvider)


def test_factory_unknown_fallback_mock(monkeypatch: pytest.MonkeyPatch) -> None:
    """未知 VISION_PROVIDER 取值回退 mock（函数）。

    参数：
        monkeypatch：临时改写 settings.VISION_PROVIDER 为未知取值。

    返回值：
        None。

    异常：
        断言失败即测试失败。
    """
    monkeypatch.setattr(settings, "VISION_PROVIDER", "no-such-provider")
    assert isinstance(_build_vision_provider(), MockVisionProvider)


# ---------------------------------------------------------------------------
# RL-3 红线：绝不输出可食性/安全性结论
# ---------------------------------------------------------------------------


def test_rl3_system_prompt_forbids_edibility() -> None:
    """system prompt 必须显式禁止可食性/安全性结论表述（函数）。

    返回值：
        None。

    异常：
        断言失败即测试失败。
    """
    assert "禁止" in VLM_SYSTEM_PROMPT
    for word in ("能吃", "不能吃", "变质", "安全", "新鲜"):
        assert word in VLM_SYSTEM_PROMPT, f"system prompt 缺少对「{word}」的禁止表述"


def test_rl3_output_contains_only_name_confidence_id(temp_ingredient) -> None:
    """VLM 混入「可以吃」等字段时 provider 输出仅含 name/confidence/ingredient_id（函数）。

    参数：
        temp_ingredient：临时食材 fixture。

    返回值：
        None。

    异常：
        断言失败即测试失败。
    """
    ing_id, name, _alias = temp_ingredient
    raw = [{"name": name, "edible": True, "verdict": "可以吃", "safety": "安全"}]
    items = MultimodalVisionProvider()._normalize(raw)
    assert len(items) == 1
    item = items[0]
    assert set(item.__dict__.keys()) == {"name", "confidence", "ingredient_id"}
    assert item.name == name
    assert item.confidence == "high"
    assert item.ingredient_id == ing_id
