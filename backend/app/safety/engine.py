"""风控规则引擎模块（纯规则，不调模型）。

职责：
    实现 RiskEngine：双侧（input/output）确定性规则扫描引擎。
    - 规则来源 risk_rule 表（enabled=true 且 stage_scope 命中），进程内存缓存 + 指纹校验，
      指纹变化即重载（远程热更新语义，不引入 Redis，spec D6）；
    - 匹配 trigger_condition JSONB：keywords 任一包含 / 分组组合（组内任一、组间全中）/ regex 命中，
      全部大小写不敏感；
    - scan() 整体 try/except 全包裹：任何异常返回 UNKNOWN_VERDICT（绝不抛出、绝不放过，spec D9）。

风险等级排序：
    critical > high > medium（降序遍历，首个命中即返回）。
"""

from __future__ import annotations

import re
import threading
import time
from typing import Literal

from sqlalchemy import func, select

from app.core.db import SessionLocal
from app.core.logging import get_logger
from app.models import RiskMessage, RiskRule
from app.safety.types import UNKNOWN_VERDICT, RiskVerdict, SafetyProfile

logger = get_logger(__name__)

# 风险等级 → 数值权重（越大越优先匹配）
_RISK_LEVEL_ORDER = {"critical": 3, "high": 2, "medium": 1}

# 风控阶段限定：input=入口闸门 / output=出口闸门
RiskStage = Literal["input", "output"]

# ---------------------------------------------------------------------------
# 注入拦截内置内存规则（边界 #28 决策，spec D9）
# ---------------------------------------------------------------------------
# 背景：Prompt 注入拦截特征（INJ-001）不属于 risk_rule 表 category 的五类 CHECK 枚举
# （food_safety_high_risk / special_population / medical_refusal / pseudoscience / output_ban），
# 阶段一不改动表结构（不加枚举、不入 seed），改为引擎内置内存规则，在 DB 规则之后追加匹配。
# 语义与 DB 规则完全一致：命中即 block=true（一票否决），走 emit_safety_response 出口；
# message_id=None（risk_message 无对应行，话术由出口节点兜底默认文案）。
# 注入特征（大小写不敏感，覆盖中英文常见越狱话术）：
_INJECTION_PATTERNS: tuple[re.Pattern, ...] = tuple(
    re.compile(pattern, re.IGNORECASE)
    for pattern in (
        r"忽略(之前|以上|上述|前面).{0,6}(指令|提示|规则|内容)",
        r"无视.{0,6}(指令|提示|规则)",
        r"关闭(你的)?风控",
        r"解除.{0,4}限制",
        r"jailbreak",
        r"ignore\s+(all\s+)?(previous|prior|above)",
        r"disregard\s+(all\s+)?(previous|prior|above)",
        r"you\s+are\s+now\s+(a|an|free)",
    )
)

# 注入拦截规则的内置话术（不入库，get_message 之前由出口节点兜底；
# 此处供 get_message 对内置 message_id 直接返回，保证 W-05 拦截页有完整三段话术）
_INJECTION_MESSAGE = {
    "message_id": "MSG-INJ-001",
    "category": "injection",
    "title": "检测到异常指令",
    "body": "你的输入包含试图绕过安全规则的指令，本产品不处理此类请求。",
    "correct_action": "请直接输入正常的烹饪相关问题，例如食材搭配或做法步骤。",
    "after_consumption_advice": None,
    "disclaimer_id": "DISCLAIMER_V1",
}


class RiskEngine:
    """确定性规则风控引擎（模型类）。

    说明：
        纯本地执行：关键词 + 分组组合 + 正则匹配，无网络、无模型调用（无 Prompt 注入面）；
        规则带进程内存缓存与指纹校验，每次 scan 校验指纹，变化即重载（热更新 + 一键回滚语义）。

    属性：
        _cache：{stage: [RuleEntry]} 规则内存缓存。
        _fingerprints：{stage: str} 各阶段规则指纹（COUNT+MAX(updated_at)）。
        _lock：线程锁，保证多线程下缓存重载安全。
    """

    def __init__(self) -> None:
        """初始化引擎实例（函数）。

        说明：
            缓存初始为空，首次 scan 时按指纹加载。

        返回值：
            None。

        异常：
            无。
        """
        self._cache: dict[str, list[dict]] = {}
        self._fingerprints: dict[str, str | None] = {}
        self._lock = threading.Lock()

    # ------------------------------------------------------------------
    # 规则加载与指纹
    # ------------------------------------------------------------------
    def _compute_fingerprint(self, stage: str) -> str | None:
        """计算指定阶段的规则指纹（函数）。

        说明：
            指纹 = "{count}:{max_updated_at}"，任一变化即视为规则集变更。
            查询本身失败时返回 None（调用方会走 UNKNOWN 兜底）。

        参数：
            stage：风控阶段（input / output）。

        返回值：
            str | None：指纹字符串；查询异常时返回 None。

        异常：
            不主动抛出（数据库异常捕获后返回 None）。
        """
        try:
            with SessionLocal() as session:
                stmt = (
                    select(func.count(RiskRule.id), func.max(RiskRule.updated_at))
                    .where(RiskRule.enabled.is_(True))
                    .where(RiskRule.stage_scope.in_([stage, "both"]))
                )
                count, max_updated = session.execute(stmt).one()
                return f"{count}:{max_updated}"
        except Exception as exc:  # noqa: BLE001 —— 指纹查询失败按「规则不可用」处理
            logger.warning("risk rule fingerprint query failed: %s", exc)
            return None

    def _load_rules(self, stage: str) -> list[dict]:
        """加载指定阶段的启用规则（带内存缓存与指纹校验）（函数）。

        说明：
            每次 scan 都会校验指纹：指纹一致直接用缓存；不一致（或无缓存）重载并按
            risk_level 降序排序。多线程下以锁保护，避免缓存踩踏。

        参数：
            stage：风控阶段（input / output）。

        返回值：
            list[dict]：规则字典列表（含 rule_code/category/trigger_condition/block 等）。

        异常：
            数据库异常向上抛出（由 scan 的全捕获兜底转 UNKNOWN）。
        """
        fingerprint = self._compute_fingerprint(stage)
        with self._lock:
            if fingerprint is not None and self._fingerprints.get(stage) == fingerprint:
                cached = self._cache.get(stage)
                if cached is not None:
                    return cached
            # 缓存缺失或指纹变化：重载规则
            with SessionLocal() as session:
                stmt = (
                    select(RiskRule)
                    .where(RiskRule.enabled.is_(True))
                    .where(RiskRule.stage_scope.in_([stage, "both"]))
                )
                rules = session.execute(stmt).scalars().all()
            entries = [
                {
                    "rule_code": r.rule_code,
                    "category": r.category,
                    "stage_scope": r.stage_scope,
                    "trigger_condition": r.trigger_condition or {},
                    "response_message_id": r.response_message_id,
                    "block": bool(r.block),
                    "risk_level": r.risk_level,
                    "evidence_ref": r.evidence_ref,
                    "version": r.version,
                }
                for r in rules
            ]
            # 按 risk_level 降序（critical > high > medium），保证高危规则优先命中
            entries.sort(key=lambda e: _RISK_LEVEL_ORDER.get(e["risk_level"], 0), reverse=True)
            self._cache[stage] = entries
            # 指纹查询失败（None）时仍缓存结果，但记录空指纹，下次再校验
            self._fingerprints[stage] = fingerprint
            return entries

    # ------------------------------------------------------------------
    # 匹配逻辑
    # ------------------------------------------------------------------
    @staticmethod
    def _match_rule(rule: dict, text_lower: str, raw_text: str) -> bool:
        """判断单条规则是否命中（函数）。

        说明：
            trigger_condition JSONB 支持三种形态（可叠加）：
            - {"keywords": [...], "any": true}：任一关键词包含即命中；
            - {..., "mode": "all_groups", "groups": [[...], ...]}：每组内任一命中、组间需全部命中；
            - {"regex": [...]}：任一正则命中（re.IGNORECASE）。

        参数：
            rule：规则字典（_load_rules 产出）。
            text_lower：小写化后的待检文本（用于关键词包含判断）。
            raw_text：原始待检文本（用于正则匹配）。

        返回值：
            bool：命中返回 True。

        异常：
            不主动抛出；非法 trigger_condition 视为不命中。
        """
        cond = rule.get("trigger_condition") or {}
        try:
            # 1) 关键词匹配（大小写不敏感：文本与关键词均已小写化）
            keyword_hit = False
            keywords = [str(k).lower() for k in (cond.get("keywords") or [])]
            if keywords:
                if cond.get("mode") == "all_groups" and cond.get("groups"):
                    # 组合命中：组内任一关键词出现、组间需全部命中
                    keyword_hit = all(
                        any(str(k).lower() in text_lower for k in (group or []))
                        for group in cond["groups"]
                    )
                else:
                    # 任意命中：任一关键词出现即可
                    keyword_hit = any(k in text_lower for k in keywords)
            # 2) 正则匹配（大小写不敏感），与关键词为「或」关系
            patterns = cond.get("regex") or []
            regex_hit = any(re.search(str(p), raw_text, re.IGNORECASE) for p in patterns)
            return keyword_hit or regex_hit
        except Exception:  # noqa: BLE001 —— 非法规则不影响整体扫描
            return False

    # ------------------------------------------------------------------
    # 对外主入口
    # ------------------------------------------------------------------
    def scan(self, stage: RiskStage, text: str, ctx: SafetyProfile | None = None) -> RiskVerdict:
        """扫描文本并返回风控判定（函数）。

        说明：
            整个方法 try/except 全包裹：任何异常（规则加载失败、匹配出错等）一律返回
            UNKNOWN_VERDICT，由业务侧转入保守模式（safe_mode_handler），绝不直连模型。

        参数：
            stage：风控阶段（input / output）。
            text：待扫描文本（输入原文或输出汇总文本）。
            ctx：用户安全档案（阶段一保留参数，预留个性化规则扩展）。

        返回值：
            RiskVerdict：风控判定结果（OK / HIT / UNKNOWN，含耗时）。

        异常：
            不抛出任何异常（全部内部消化为 UNKNOWN）。
        """
        start = time.perf_counter()
        try:
            raw_text = text or ""
            text_lower = raw_text.lower()
            rules = self._load_rules(stage)
            for rule in rules:
                if self._match_rule(rule, text_lower, raw_text):
                    latency = (time.perf_counter() - start) * 1000
                    return RiskVerdict(
                        status="HIT",
                        hit=True,
                        block=bool(rule["block"]),
                        overrides_all=bool(rule["block"]),
                        rule_code=rule["rule_code"],
                        category=rule["category"],
                        risk_level=rule["risk_level"],
                        message_id=rule["response_message_id"],
                        evidence_ref=[f"{rule['rule_code']}@{rule['version']}"],
                        latency_ms=round(latency, 2),
                    )
            # 内置内存规则：DB 规则之后追加注入拦截检测（边界 #28，见模块头注释）
            # 仅在 input 阶段检测（注入针对输入侧；output 汇总文本含用户原文会误伤）
            if stage == "input":
                for pattern in _INJECTION_PATTERNS:
                    if pattern.search(raw_text):
                        latency = (time.perf_counter() - start) * 1000
                        return RiskVerdict(
                            status="HIT",
                            hit=True,
                            block=True,
                            overrides_all=True,
                            rule_code="INJ-001",
                            category="injection",
                            risk_level="critical",
                            message_id=_INJECTION_MESSAGE["message_id"],
                            evidence_ref=["INJ-001@builtin-v1.0"],
                            latency_ms=round(latency, 2),
                        )
            latency = (time.perf_counter() - start) * 1000
            return RiskVerdict(status="OK", hit=False, latency_ms=round(latency, 2))
        except Exception as exc:  # noqa: BLE001 —— 🔴 永不放过，只降级（UNKNOWN → 保守模式）
            logger.error("risk engine scan error (stage=%s): %s", stage, exc)
            fallback = dict(UNKNOWN_VERDICT)
            fallback["latency_ms"] = round((time.perf_counter() - start) * 1000, 2)
            return RiskVerdict(**fallback)

    def get_message(self, message_id: str | None) -> dict | None:
        """按 message_id 查询话术模板（函数）。

        说明：
            话术全部来自 risk_message 表（RL-1：不由模型生成）；
            查询失败/不存在时返回 None，调用方需兜底默认文案。

        参数：
            message_id：话术模板 ID（如 "MSG-FS-001"）。

        返回值：
            dict | None：话术字段字典（message_id/category/title/body/correct_action/
            after_consumption_advice/disclaimer_id）；未命中或异常返回 None。

        异常：
            不抛出（数据库异常内部消化）。
        """
        if not message_id:
            return None
        # 内置内存规则话术（注入拦截 MSG-INJ-001 不入 risk_message 表，边界 #28）
        if message_id == _INJECTION_MESSAGE["message_id"]:
            return dict(_INJECTION_MESSAGE)
        try:
            with SessionLocal() as session:
                msg = session.execute(
                    select(RiskMessage).where(RiskMessage.message_id == message_id)
                ).scalar_one_or_none()
                if msg is None:
                    return None
                return {
                    "message_id": msg.message_id,
                    "category": msg.category,
                    "title": msg.title,
                    "body": msg.body,
                    "correct_action": msg.correct_action,
                    "after_consumption_advice": msg.after_consumption_advice,
                    "disclaimer_id": msg.disclaimer_id,
                }
        except Exception as exc:  # noqa: BLE001 —— 话术查询失败不阻断响应组装
            logger.error("risk message query failed (%s): %s", message_id, exc)
            return None


# 进程级单例（风控引擎无状态缓存线程安全，全局复用）
_engine: RiskEngine | None = None
_engine_lock = threading.Lock()


def get_risk_engine() -> RiskEngine:
    """获取 RiskEngine 进程级单例（函数）。

    返回值：
        RiskEngine：全局唯一引擎实例。

    异常：
        无。
    """
    global _engine
    if _engine is None:
        with _engine_lock:
            if _engine is None:
                _engine = RiskEngine()
    return _engine
