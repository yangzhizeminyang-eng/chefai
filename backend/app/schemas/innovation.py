"""AI 菜品创新 Schema 模块（模块 O）。

职责：
    定义 /v1/innovation/* 七接口的请求/响应模型：
    - 预检：InnovationPrecheckRequest / InnovationPrecheckResponse（含 issues 四类拦截原因）；
    - 生成：InnovationGenerateRequest / InnovationRecipeOut（201 生成结果，含 basis 依据
      与 nutrition 估算、disclaimer 强制标识）；
    - 状态机与复用：AdoptResponse / IndexResponse / ReuseResponse；
    - 反馈回流：InnovationFeedbackRequest / InnovationFeedbackResponse；
    - 异步任务（M-01）：InnovationJobCreatedResponse / InnovationJobStatusResponse
      （提交即返回 job_id + 轮询终态，LLM 上游慢时不再依赖同步长请求）。

红线：
    所有创新域响应体均携带 is_ai_innovated=true 与 disclaimer 字段（强制标识，
    「AI 创新·未经人工审核」话术口径见 DISCLAIMER_TEXT）。
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

# AI 创新免责声明固定话术（🔴 所有创新域响应强制携带）
DISCLAIMER_TEXT = "AI 创新·未经人工审核，仅供参考，请勿用于特殊人群"

# 拦截原因四类枚举（issues[].type）
IssueType = Literal["high_risk", "allergen", "special_population", "taboo"]


class InnovationPrecheckRequest(BaseModel):
    """创新预检请求体（模型类）。

    属性：
        ingredients：用户选择的目标食材名称列表（≥1，支持库内名称或别名）。
        request_id：幂等键（可缺省，后端自动生成）。
    """

    ingredients: list[str] = Field(min_length=1, max_length=20)
    request_id: str | None = Field(default=None, max_length=40)


class InnovationIssue(BaseModel):
    """预检拦截原因（模型类）。

    属性：
        type：拦截类型（high_risk 高危 / allergen 过敏原 / special_population 特殊人群 /
        taboo 搭配禁忌）。
        message：面向用户的拦截话术。
    """

    type: IssueType
    message: str


class PairingBasisItem(BaseModel):
    """搭配规则依据项（模型类）。

    说明：
        🔴 搭配结论必须查 flavor_pairing_rule 表，LLM 无权决定搭配；rule_id 供
        feedback 回流调整规则权重时定位溯源。

    属性：
        rule_id：flavor_pairing_rule.id。
        ingredient_a / ingredient_b：搭配双方食材名。
        relation：recommend（推荐）/ conflict（风味冲突）/ taboo（禁忌）。
        technique：建议技法（仅白名单内的技法才会透出）。
        rationale：烹饪学表述的搭配理由。
        weight：规则权重（feedback 回流会调整）。
    """

    rule_id: int
    ingredient_a: str
    ingredient_b: str
    relation: str
    technique: str | None = None
    rationale: str = ""
    weight: float = 1.0


class InnovationPrecheckResponse(BaseModel):
    """创新预检响应体（模型类）。

    说明：
        ok 与 blocked 互补：通过检查 ok=true / blocked=false；拦截时 ok=false /
        blocked=true 并给出 issues。pairings 为命中的推荐搭配依据（供前端在生成前
        预览「为什么这样搭」），仅在食材解析成功且未拦截时返回。

    属性：
        ok：是否通过预检（可继续生成）。
        blocked：是否被拦截。
        issues：拦截原因列表（type + message）。
        risk_log_written：本次预检是否写入了 risk_log 留痕行。
        pairings：命中的推荐搭配依据列表（可缺省）。
    """

    ok: bool
    blocked: bool
    issues: list[InnovationIssue] = Field(default_factory=list)
    risk_log_written: bool = False
    pairings: list[PairingBasisItem] | None = None


class InnovationGenerateRequest(BaseModel):
    """创新生成请求体（模型类）。

    属性：
        ingredients：用户选择的目标食材名称列表（≥1）。
        request_id：幂等键（可缺省，后端自动生成，透传 trace 取证）。
    """

    ingredients: list[str] = Field(min_length=1, max_length=20)
    request_id: str | None = Field(default=None, max_length=40)


class InnovationRecipeOut(BaseModel):
    """AI 创新菜响应体（模型类）。

    说明：
        ingredients/steps 为生成层 JSON 结构（amount 100% 量化、steps 含 duration_sec）；
        basis 为创新依据（搭配规则与食材性质引用，可追溯）；nutrition 为按
        ability/nutrition 同口径估算（缺失食材标注 excluded_items）。

    属性：
        id：innovation_recipe.id。
        name：AI 创新菜名。
        ingredients：量化食材列表（[{name, amount, unit}]）。
        steps：步骤列表（[{no, description, duration_sec, tips}]）。
        basis：创新依据（pairings/properties/techniques_whitelist/generated_by；
        generated_by ∈ {"llm", "template"}——llm=LLM 表达成功，template=LLM
        25s 硬超时或失败后的规则模板降级，P1 DEF-01）。
        nutrition：营养估算（total/per_serving/excluded_items/estimate_note）。
        status：状态机（generated / adopted / indexed / removed）。
        is_ai_innovated：🔴 恒 true（模型默认，AI 创新强制标识）。
        visibility：可见性（阶段二恒 private）。
        disclaimer：🔴 强制免责话术。
        rating：用户评分（1~5，未评为 None）。
        created_at：创建时间 ISO 字符串（可缺省）。
    """

    id: int
    name: str
    ingredients: list[dict] = Field(default_factory=list)
    steps: list[dict] = Field(default_factory=list)
    basis: dict = Field(default_factory=dict)
    nutrition: dict = Field(default_factory=dict)
    status: str = "generated"
    is_ai_innovated: bool = True
    visibility: str = "private"
    disclaimer: str = DISCLAIMER_TEXT
    rating: int | None = None
    created_at: str | None = None


class InnovationGenerateResponse(BaseModel):
    """创新生成响应体（模型类）。

    说明：
        201 返回；拦截时由路由层返回 200 拦截语义体（ok=false + issues，复用
        InnovationPrecheckResponse 结构）。

    属性：
        ok：是否生成成功（拦截/失败为 false）。
        recipe：创新菜完整结构（成功时返回）。
        request_id：幂等键回显。
        trace_id：本次编排 trace 标识。
        issues：拦截原因（拦截时返回）。
    """

    ok: bool
    recipe: InnovationRecipeOut | None = None
    request_id: str | None = None
    trace_id: str | None = None
    issues: list[InnovationIssue] | None = None


class InnovationStateActionResponse(BaseModel):
    """创新菜状态机操作响应体（adopt / index 共用，模型类）。

    属性：
        status：流转后的状态（adopted / indexed）。
        embedding_id：向量行 ID（仅 index 返回）。
        is_ai_innovated：🔴 恒 true。
        disclaimer：🔴 强制免责话术。
    """

    status: str
    embedding_id: int | None = None
    is_ai_innovated: bool = True
    disclaimer: str = DISCLAIMER_TEXT


class InnovationReuseResponse(BaseModel):
    """创新菜复用响应体（模型类）。

    说明：
        供前端直接进入分步引导/再编辑（recipe 为完整生成结构）。

    属性：
        recipe：创新菜完整结构（含 disclaimer/is_ai_innovated 恒带）。
    """

    recipe: InnovationRecipeOut


class InnovationFeedbackRequest(BaseModel):
    """创新菜反馈请求体（模型类）。

    属性：
        rating：评分 1~5（≥4 加权、≤2 降权、3 不调整搭配规则权重）。
        comment：可选文字反馈（阶段二表无 comment 列，仅记录日志不落库）。
    """

    rating: int = Field(ge=1, le=5)
    comment: str | None = Field(default=None, max_length=500)


class InnovationFeedbackResponse(BaseModel):
    """创新菜反馈响应体（模型类）。

    属性：
        status：固定 'ok'。
        adjusted_rules：本次回流实际调整权重的搭配规则条数。
        is_ai_innovated：🔴 恒 true。
        disclaimer：🔴 强制免责话术。
    """

    status: str = "ok"
    adjusted_rules: int = 0
    is_ai_innovated: bool = True
    disclaimer: str = DISCLAIMER_TEXT


class InnovationJobCreatedResponse(BaseModel):
    """创新异步生成任务受理响应体（模型类，M-01 异步化）。

    说明：
        POST /v1/innovation/jobs 提交即返回（HTTP 202）：生成在后台线程池执行，
        前端持 job_id 轮询 GET /v1/innovation/jobs/{job_id} 取终态；同步 /generate
        保留向后兼容。

    属性：
        job_id：异步任务 ID（injob_ 前缀 + 12 位 hex）。
        status：受理时任务状态（恒 pending）。
        request_id：幂等键回显（供 trace 取证，可缺省）。
    """

    job_id: str
    status: str = "pending"
    request_id: str | None = None


class InnovationJobStatusResponse(BaseModel):
    """创新异步生成任务状态响应体（模型类，M-01 异步化轮询返回）。

    说明：
        status ∈ pending | running | succeeded | failed | blocked：succeeded 时
        recipe 为完整创新菜结构（🔴 is_ai_innovated=true 与 disclaimer 恒带，
        与同步 /generate 同构）；blocked 时 issues 为拦截原因；failed 时 error
        为面向用户文案。未知/他人 job 统一 404（跨用户隔离，不泄露存在性）。

    属性：
        job_id：异步任务 ID。
        status：任务状态（pending / running / succeeded / failed / blocked）。
        recipe：创新菜完整结构（仅 succeeded 返回）。
        issues：拦截原因列表（仅 blocked 返回，type + message）。
        error：失败文案（仅 failed 返回）。
        request_id：幂等键回显（可缺省）。
    """

    job_id: str
    status: str
    recipe: InnovationRecipeOut | None = None
    issues: list[InnovationIssue] = Field(default_factory=list)
    error: str | None = None
    request_id: str | None = None


__all__ = [
    "DISCLAIMER_TEXT",
    "IssueType",
    "InnovationIssue",
    "PairingBasisItem",
    "InnovationPrecheckRequest",
    "InnovationPrecheckResponse",
    "InnovationGenerateRequest",
    "InnovationRecipeOut",
    "InnovationGenerateResponse",
    "InnovationStateActionResponse",
    "InnovationReuseResponse",
    "InnovationFeedbackRequest",
    "InnovationFeedbackResponse",
    "InnovationJobCreatedResponse",
    "InnovationJobStatusResponse",
]
