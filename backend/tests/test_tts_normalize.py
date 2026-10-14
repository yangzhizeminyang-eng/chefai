"""TTS 文本中文归一化测试（用户要求：所有语音输出必须是中文）。

覆盖：
    normalize_tts_text：烹饪单位替换（cm/cm³/g/ml/kg/min/℃）、数字区间
    读法（2-10 → 2到10）、剩余拉丁字母兜底剔除、纯中文透传、空串透传。
"""

from __future__ import annotations

from app.ability.providers import normalize_tts_text


def test_units_to_chinese() -> None:
    """烹饪单位替换为中文读法（函数）。"""
    assert normalize_tts_text("切2-10cm小段") == "切2到10厘米小段"
    assert normalize_tts_text("土豆切1cm³小块") == "土豆切1立方厘米小块"
    assert normalize_tts_text("鸡丁加盐2g") == "鸡丁加盐2克"
    assert normalize_tts_text("生抽6ml") == "生抽6毫升"
    assert normalize_tts_text("腌10min") == "腌10分钟"
    assert normalize_tts_text("米饭500Kg") == "米饭500千克"
    assert normalize_tts_text("水温100℃") == "水温100摄氏度"


def test_latin_fallback_stripped() -> None:
    """剩余拉丁字母兜底剔除，保证无英文读音（函数）。"""
    assert normalize_tts_text("参考W-04步骤") == "参考-04步骤"
    assert normalize_tts_text("add some salt").strip() == ""


def test_chinese_passthrough_and_empty() -> None:
    """纯中文与空串透传（函数）。"""
    assert normalize_tts_text("葱切花，蒜切沫，备用。") == "葱切花，蒜切沫，备用。"
    assert normalize_tts_text("") == ""
    assert normalize_tts_text("第 1 步：腌 10 分钟。") == "第 1 步：腌 10 分钟。"
