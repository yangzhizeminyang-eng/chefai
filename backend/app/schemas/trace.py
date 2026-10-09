"""调度可视化与远程开关 Schema 模块。

职责：
    GET /v1/trace/{request_id}、GET /v1/trace、GET /v1/config/switches 的响应模型。
    字段对齐前端 types.ts：TraceDetail.veto 为对象（W-06 以 veto.veto 判断高亮）、
    列表项 veto 为布尔（下拉标签直接消费）、列表响应体为数组。
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from app.schemas.common import RiskDetailOut


class TraceSpanOut(BaseModel):
    """Agent 调度单个节点 span（模型类）。

    说明：
        对齐前端 TraceSpan；纯规则节点 model_name 为 None、token/成本为 0。

    属性：
        node_name：节点名（如 intake_guard / supervisor / recipe_rank）。
        status：节点状态（七态）。
        duration_ms：耗时（毫秒，未执行为 0）。
        model_name：调用的模型名（纯规则节点为 None）。
        prompt_tokens：prompt token 数。
        completion_tokens：completion token 数。
        cost_cents：成本（分）。
        rule_hit：命中的风控规则编码（未命中为 None）。
    """

    node_name: str
    status: str
    duration_ms: int = 0
    model_name: str | None = None
    prompt_tokens: int = 0
    completion_tokens: int = 0
    cost_cents: float = 0.0
    rule_hit: str | None = None


class TraceVetoOut(BaseModel):
    """一票否决判定（模型类）。

    说明：
        前端 TraceDetail.veto 为对象结构（veto.veto === true 触发高亮横幅）。

    属性：
        veto：是否触发一票否决。
        reason：触发原因说明（可缺省）。
    """

    veto: bool
    reason: str | None = None


class TraceTotalsOut(BaseModel):
    """trace 汇总（模型类）。

    说明：
        双口径并存：前端消费 prompt_tokens/completion_tokens/cost_cents，
        任务口径字段 total_* 同值附加（多余字段无害）。

    属性：
        prompt_tokens：总 prompt token 数。
        completion_tokens：总 completion token 数。
        cost_cents：总成本（分）。
        total_duration_ms：总耗时（毫秒）。
        total_prompt_tokens：总 prompt token 数（任务口径字段名）。
        total_completion_tokens：总 completion token 数（任务口径字段名）。
        total_cost_cents：总成本（分，任务口径字段名）。
    """

    prompt_tokens: int = 0
    completion_tokens: int = 0
    cost_cents: float = 0.0
    total_duration_ms: int = 0
    total_prompt_tokens: int = 0
    total_completion_tokens: int = 0
    total_cost_cents: float = 0.0


class TraceDetailResponse(BaseModel):
    """trace 详情响应体（模型类）。

    说明：
        risk 为对象（非 null）：hit=false 表示未命中放行（前端类型要求 hit 字段恒存在）。

    属性：
        request_id：幂等键。
        veto：一票否决判定对象。
        risk：风控判定（含话术全文，hit=false 时其余字段为 None）。
        nodes：节点执行列表。
        totals：token 与成本汇总。
        created_at：首个节点落库时间（ISO 8601）。
    """

    request_id: str
    veto: TraceVetoOut
    risk: RiskDetailOut
    nodes: list[TraceSpanOut] = Field(default_factory=list)
    totals: TraceTotalsOut = Field(default_factory=TraceTotalsOut)
    created_at: str | None = None


class TraceListItem(BaseModel):
    """trace 列表项（模型类）。

    说明：
        GET /v1/trace 响应体为本模型的数组（前端 listTraces 消费 Promise<TraceListItem[]>）；
        veto 为布尔（列表项口径，与详情对象口径不同）。

    属性：
        request_id：幂等键。
        created_at：最近落库时间（ISO 8601）。
        veto：是否一票否决。
        risk：风控判定摘要。
        node_count：节点 span 总数。
        total_duration_ms：节点耗时合计（毫秒）。
    """

    request_id: str
    created_at: str | None = None
    veto: bool = False
    risk: RiskDetailOut = Field(default_factory=RiskDetailOut)
    node_count: int = 0
    total_duration_ms: int = 0


class SwitchesResponse(BaseModel):
    """远程开关响应体（模型类）。

    说明：
        读 remote_config switch.* 五键（05-V1.1 §4.4），缺省 True（默认开）。

    属性：
        recommend：推荐模块开关。
        vision：识别模块开关（阶段一预留）。
        qa：问答模块开关。
        payment：支付模块开关（阶段一预留）。
        innovation：AI 菜品创新开关（模块 O 属阶段二，阶段一仅下发配置）。
    """

    recommend: bool = True
    vision: bool = True
    qa: bool = True
    payment: bool = True
    innovation: bool = True
