"""识别与语音 Schema 模块。

职责：
    模块 D（vision / speech）与推荐补全（E.8 filtered 重放 / E.11 空结果建议）的
    请求/响应模型。字段对齐 spec Task 5：
    - VisionRecognizeResponse：识别结果 + 降级标注 + 识别额度（quota 三元组）；
    - VisionConfirmRequest/Response：确认识别结果时的食材存在性校验；
    - SpeechAsrResponse：语音转写文本 + 降级标注；
    - FilteredResponse：布尔硬过滤重放结果（被过滤菜谱 + 过滤原因）；
    - EmptyResultSuggestions：推荐空结果时的放宽建议（E.11）。
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class RecognizedItemOut(BaseModel):
    """单个识别结果项（模型类）。

    属性：
        name：食材名（库内真实存在的名字）。
        confidence：置信度档位（high / low）。
        ingredient_id：食材 ID（对齐库内记录时非空）。
    """

    name: str
    confidence: str
    ingredient_id: int | None = None


class VisionRecognizeResponse(BaseModel):
    """拍照识别响应体（模型类）。

    说明：
        provider 异常时 degraded=true、recognized 为空、不扣额度；
        全低置信（无 high 项）时同样不扣额度但 degraded=false。

    属性：
        recognized：识别出的食材项列表（降级时为空列表）。
        degraded：provider 是否异常降级。
        message：附加提示文案（降级 / 全低置信时非空，可缺省）。
        quota：识别额度 {used, limit, remaining}。
    """

    recognized: list[RecognizedItemOut] = Field(default_factory=list)
    degraded: bool = False
    message: str | None = None
    quota: dict = Field(default_factory=dict)


class VisionConfirmRequest(BaseModel):
    """确认识别结果请求体（模型类）。

    属性：
        names：待确认的食材名列表（≥1；后端逐个校验 ingredient/alias 表存在性）。
    """

    names: list[str] = Field(min_length=1, max_length=50)


class VisionConfirmResponse(BaseModel):
    """确认识别结果响应体（模型类）。

    说明：
        added 为校验通过的食材数（前端据此加入已选集合，后端不入库）；
        skipped 为未通过校验（ingredient/alias 均未命中）被跳过的名字。

    属性：
        added：校验通过的食材数量。
        skipped：校验未通过被跳过的食材名列表。
    """

    added: int
    skipped: list[str] = Field(default_factory=list)


class SpeechAsrResponse(BaseModel):
    """语音转写响应体（模型类）。

    属性：
        text：转写文本（降级时为空串）。
        degraded：provider 是否异常降级。
        message：附加提示文案（降级时非空，可缺省）。
    """

    text: str
    degraded: bool = False
    message: str | None = None


class FilteredReason(BaseModel):
    """单条过滤原因（模型类）。

    说明：
        设备维度新增（缺陷 M2/P6/S8 修复）：被过滤条目的 reasons 数组元素结构，
        沿用既有原因类型码并扩展 equipment；detail 为中文明细（如「缺少设备：燃气灶」）。

    属性：
        type：原因类型码（allergen 致敏原 / taboo 忌口 / difficulty 难度超限 /
            equipment 缺少设备）。
        detail：中文明细说明（设备维度形如「缺少设备：燃气灶」）。
    """

    type: str
    detail: str


class FilteredItem(BaseModel):
    """被过滤菜谱条目（模型类）。

    属性：
        recipe_id：菜谱 ID。
        recipe_name：菜名。
        reason：主过滤原因类型码（allergen / taboo / difficulty / equipment；
            多原因并存时按优先级取首项，兼容既有前端契约保留）。
        reasons：全部过滤原因列表（{type, detail} 结构，设备维度 detail 形如
            「缺少设备：燃气灶」；缺省空列表向后兼容）。
    """

    recipe_id: int
    recipe_name: str
    reason: str
    reasons: list[FilteredReason] = Field(default_factory=list)


class FilteredResponse(BaseModel):
    """硬过滤重放响应体（模型类）。

    说明：
        W-02「显示被我过滤掉的菜」：filtered 为会被布尔硬过滤移除的菜谱列表。

    属性：
        filtered：被过滤菜谱列表（含过滤原因）。
        total_filtered：被过滤菜谱总数。
    """

    filtered: list[FilteredItem] = Field(default_factory=list)
    total_filtered: int = 0


class EmptyResultSuggestions(BaseModel):
    """推荐空结果建议（E.11，模型类）。

    属性：
        message：空结果说明文案。
        relax_options：可选放宽动作列表（如「放宽到差 1-2 样」）。
        followup_question：追问话术（引导补充食材）。
    """

    message: str
    relax_options: list[str] = Field(default_factory=list)
    followup_question: str


__all__ = [
    "RecognizedItemOut",
    "VisionRecognizeResponse",
    "VisionConfirmRequest",
    "VisionConfirmResponse",
    "SpeechAsrResponse",
    "FilteredItem",
    "FilteredReason",
    "FilteredResponse",
    "EmptyResultSuggestions",
]
