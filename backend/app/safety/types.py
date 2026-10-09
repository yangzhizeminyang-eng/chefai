"""风控类型定义模块。

职责：
    定义风控引擎的公共数据类型：RiskVerdict（风控判定结果）、SafetyProfile（用户安全档案）、
    UNKNOWN_VERDICT 常量（风控不可用时的兜底判定）。
    本模块不依赖数据库与网络，供 engine / graph / api 各层统一消费。

设计约定（spec D9 红线）：
    - 风控异常一律返回 status=UNKNOWN（触发保守模式），绝不直连模型；
    - overrides_all 与 block 语义一致：命中阻断规则即一票否决。
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

# 风控判定状态三态：OK=未命中放行 / HIT=命中规则 / UNKNOWN=风控不可用（保守模式）
VerdictStatus = Literal["OK", "HIT", "UNKNOWN"]

# 风控不可用时的兜底判定常量：status=UNKNOWN，业务侧必须转入 safe_mode_handler，
# 绝不允许在 UNKNOWN 状态下继续执行业务链（架构文档 §5 第 3 问）
UNKNOWN_VERDICT = {
    "status": "UNKNOWN",
    "hit": False,
    "block": False,
    "overrides_all": False,
    "rule_code": None,
    "category": None,
    "risk_level": None,
    "message_id": None,
    "evidence_ref": [],
    "latency_ms": None,
}


class RiskVerdict(BaseModel):
    """风控判定结果（模型类）。

    说明：
        由 RiskEngine.scan 产出，双侧闸门（intake_guard / output_guard）各持一份；
        status=UNKNOWN 时其余字段无意义（业务节点必须拒绝执行）。

    属性：
        status：判定状态（OK / HIT / UNKNOWN）。
        hit：是否命中任一规则。
        block：命中的规则是否要求阻断（一票否决）。
        overrides_all：一票否决标记（阶段一与 block 同值，预留未来「部分否决」扩展）。
        rule_code：命中规则编码（如 FS-001），未命中为 None。
        category：命中规则类别（food_safety_high_risk / medical_refusal / pseudoscience 等）。
        risk_level：命中规则风险等级（critical / high / medium）。
        message_id：命中的话术模板 ID（对应 risk_message 表）。
        evidence_ref：取证引用列表（如 ["FS-001@rules-v1.0"]）。
        latency_ms：本次扫描耗时（毫秒），供 trace 面板取证。
    """

    status: VerdictStatus = "OK"
    hit: bool = False
    block: bool = False
    overrides_all: bool = False
    rule_code: str | None = None
    category: str | None = None
    risk_level: str | None = None
    message_id: str | None = None
    evidence_ref: list[str] = Field(default_factory=list)
    latency_ms: float | None = None


class SafetyProfile(BaseModel):
    """用户安全档案（模型类）。

    说明：
        阶段一无家庭档案（spec D8），默认空集合 / 无难度上限；
        硬过滤（hard_filter）以此为准：过敏原/忌口命中即整条排除，绝不做降权。

    属性：
        user_allergen_codes：用户过敏原代码集合（GB 7718 八类 code，如 ["peanut"]）。
        dietary_restrictions：忌口标记集合（对应 recipe.dietary_flags，如 ["vegetarian"]）。
        special_population：特殊人群标记（pregnant / infant / elderly 等，阶段一默认空）。
        difficulty_cap：厨艺难度上限（1~5，None 表示无上限）。
    """

    user_allergen_codes: list[str] = Field(default_factory=list)
    dietary_restrictions: list[str] = Field(default_factory=list)
    special_population: list[str] = Field(default_factory=list)
    difficulty_cap: int | None = None
