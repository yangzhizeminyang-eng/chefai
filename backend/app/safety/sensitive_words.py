"""输出侧敏感词兜底过滤模块。

职责：
    与 DB 中的 OB-001~OB-005 输出侧规则互补（DB 命中即整体阻断），本模块作为二级保险：
    对出口文本做正则禁令匹配与替换（sanitize），覆盖六类禁令——
    法定营养声称 / 绝对化用语 / 安全承诺 / 医疗宣称 / 功效宣称 / 食物相克。
    纯本地正则，不调模型（spec D9 红线）。

说明：
    替换目标是把违规表述改写为合规中性表述并记录 violations 供 trace 取证；
    DB 规则命中在先（阻断），本模块兜底处理 DB 词表未覆盖的变体表述。
"""

from __future__ import annotations

import re
import threading
import time
from dataclasses import dataclass, field

from sqlalchemy import select

from app.core.db import SessionLocal
from app.models import RemoteConfig

# 禁令类别常量
BAN_NUTRITION_CLAIM = "nutrition_claim"   # 法定营养声称（低脂/无糖/高蛋白…）
BAN_ABSOLUTE = "absolute"                 # 绝对化用语（最好的/第一/唯一…）
BAN_SAFETY_PROMISE = "safety_promise"     # 安全承诺（绝对安全/保证不过敏…）
BAN_MEDICAL = "medical_claim"             # 医疗宣称（治疗/治愈/根治…）
BAN_EFFECT = "effect_claim"               # 功效宣称（减肥/瘦身/月瘦X斤…）
BAN_FOOD_CLASH = "food_clash"             # 食物相克伪科学

# 禁令正则表：[(类别, 编译后正则, 替换文本)]；顺序即替换优先级
# 注意：替换文本必须为合规中性表述，不得引入新的违规词
_BAN_RULES: list[tuple[str, re.Pattern, str]] = [
    # ---- 法定营养声称（对应 OB-001 / PRD RL-9）----
    (BAN_NUTRITION_CLAIM, re.compile(r"零脂肪|0脂肪|零糖|0糖|无糖|低脂|低糖", re.IGNORECASE), "营养构成适中"),
    (BAN_NUTRITION_CLAIM, re.compile(r"高蛋白|富含蛋白|高膳食纤维|富含膳食纤维|高纤", re.IGNORECASE), "含有一定蛋白质或膳食纤维"),
    # ---- 安全承诺（对应 OB-003 / PRD RL-2）----
    (BAN_SAFETY_PROMISE, re.compile(r"绝对安全|百分百安全|100%安全|肯定不过敏|保证不过敏|绝不会过敏", re.IGNORECASE), "请注意核实自身过敏情况"),
    (BAN_SAFETY_PROMISE, re.compile(r"放心吃|放心食用|尽管吃", re.IGNORECASE), "请确认食材新鲜并彻底加热后食用"),
    # ---- 医疗宣称（对应 OB-002 / PRD RL-7）----
    (BAN_MEDICAL, re.compile(r"药到病除|根治|痊愈|治好|治愈", re.IGNORECASE), "有助于日常饮食调整"),
    (BAN_MEDICAL, re.compile(r"治疗|疗效|消炎|降三高", re.IGNORECASE), "辅助日常饮食管理"),
    # ---- 功效宣称（对应 OB-005 / PRD RL-11）----
    (BAN_EFFECT, re.compile(r"月瘦\d+斤|减脂掉秤|瘦\d+斤|越吃越瘦", re.IGNORECASE), "循序渐进控制饮食"),
    (BAN_EFFECT, re.compile(r"减肥|瘦身|燃脂|刮油", re.IGNORECASE), "体重管理"),
    # ---- 绝对化用语（对应 OB-004 / PRD RL-8，广告法口径）----
    (BAN_ABSOLUTE, re.compile(r"最好的|最健康的|最有效|最营养|第一名|排名第一|顶级|极品|唯一", re.IGNORECASE), "较为合适的"),
    (BAN_ABSOLUTE, re.compile(r"第一|唯一|绝无仅有", re.IGNORECASE), "少见的"),
    # ---- 食物相克伪科学（与 PS-001 澄清口径一致）----
    (BAN_FOOD_CLASH, re.compile(r"相克|相冲|同食中毒|一起吃会中毒|克死", re.IGNORECASE), "所谓「食物相克」缺乏科学依据"),
]


# ---------------------------------------------------------------------------
# remote_config 覆盖支持（后台管理端 /admin/v1/sensitive-words CRUD 消费）
# ---------------------------------------------------------------------------
# 存储：remote_config 表 config_key='output_sensitive_words'，value 为 JSONB 数组
# [{"word": "违规词", "replacement": "合规替换文本", "category": "custom"}, ...]。
# 消费语义（模块 K 决策）：sanitize() 优先使用自定义词表（逐词 re.escape 构建
# 忽略大小写正则）；配置缺失 / 为空数组 / 加载异常时回退代码内置 _BAN_RULES。
# 缓存：进程内 TTL 缓存 30s（与风控规则指纹热更新对齐的轮询节奏语义，不引入
# Redis，spec D6）；管理端写入后最迟 30s 生效，DB 不可用时静默回退内置表。
_CUSTOM_CONFIG_KEY = "output_sensitive_words"

# 自定义词表 TTL（秒）：30s 内复用进程缓存，超时重新查库
_CUSTOM_TTL_SECONDS = 30.0

# 缓存未加载哨兵（区分「已加载且为空」与「从未加载」，避免空表反复击穿缓存）
_UNSET = object()

_custom_lock = threading.Lock()
_custom_cache: dict = {"loaded_at": 0.0, "rules": _UNSET}


def _build_custom_rules(value: object) -> list[tuple[str, re.Pattern, str]]:
    """将 remote_config JSONB 值构建为替换规则表（函数）。

    参数：
        value：remote_config.value（期望为 [{word, replacement, category?}] 数组）。

    返回值：
        list[tuple[str, re.Pattern, str]]：(类别, 编译正则, 替换文本) 列表；
        value 非法或为空返回空列表（空列表即回退内置表语义）。

    异常：
        不抛出（条目非法逐条跳过，保证出口链路不中断）。
    """
    rules: list[tuple[str, re.Pattern, str]] = []
    if not isinstance(value, list):
        return rules
    for item in value:
        try:
            if not isinstance(item, dict):
                continue
            word = str(item.get("word") or "").strip()
            replacement = str(item.get("replacement") or "").strip()
            if not word or not replacement:
                continue
            category = str(item.get("category") or "custom")
            rules.append(
                (category, re.compile(re.escape(word), re.IGNORECASE), replacement)
            )
        except Exception:  # noqa: BLE001 —— 单条非法不影响其余条目
            continue
    return rules


def _load_custom_rules() -> list[tuple[str, re.Pattern, str]] | None:
    """读取自定义敏感词表（带 30s TTL 进程缓存）（函数）。

    说明：
        首次调用查 remote_config；TTL 内复用缓存；DB 异常按「无自定义」处理
        （回退内置表）并同样计入缓存周期，避免出口链路每请求击穿数据库。

    返回值：
        list[tuple[str, re.Pattern, str]] | None：自定义规则表；
        空列表（含配置缺失/为空/异常）返回 None 表示回退内置表。

    异常：
        不抛出（数据库异常内部消化）。
    """
    now = time.monotonic()
    with _custom_lock:
        if (
            _custom_cache["rules"] is not _UNSET
            and now - _custom_cache["loaded_at"] < _CUSTOM_TTL_SECONDS
        ):
            cached = _custom_cache["rules"]
            return cached or None
    try:
        with SessionLocal() as session:
            row = session.execute(
                select(RemoteConfig).where(RemoteConfig.config_key == _CUSTOM_CONFIG_KEY)
            ).scalar_one_or_none()
        rules = _build_custom_rules(row.value if row is not None else None)
    except Exception:  # noqa: BLE001 —— DB 不可用回退内置表，不阻断出口
        rules = []
    with _custom_lock:
        _custom_cache["loaded_at"] = now
        _custom_cache["rules"] = rules
    return rules or None


def invalidate_custom_rules_cache() -> None:
    """清空自定义词表进程缓存（函数）。

    说明：
        供管理端写端点在变更后调用，使 /admin/v1/sensitive-words 的改动
        即时生效（不必等 30s TTL 过期）。

    参数：
        无。

    返回值：
        None。

    异常：
        无。
    """
    with _custom_lock:
        _custom_cache["loaded_at"] = 0.0
        _custom_cache["rules"] = _UNSET


@dataclass
class SanitizeResult:
    """敏感词替换结果（模型类）。

    属性：
        clean_text：替换后的文本（无违规时与原文一致）。
        violations：违规明细列表，每项 {"category": 类别, "matched": 命中词}。
    """

    clean_text: str
    violations: list[dict] = field(default_factory=list)


def sanitize(text: str) -> tuple[str, list[dict]]:
    """对输出文本执行敏感词禁令替换（函数）。

    说明：
        词表优先级：remote_config 'output_sensitive_words' 自定义词表（后台
        /admin/v1/sensitive-words 维护，30s TTL 缓存）优先；配置缺失/为空时
        回退代码内置 _BAN_RULES。遍历生效词表逐条替换；同一类别多次命中均
        记录；替换后的文本不再二次校验（替换文本为合规中性表述）。
        函数签名与既有调用方（出口节点）保持不变。

    参数：
        text：出口汇总文本（菜名 + rank_reasons + qa_answer 等）。

    返回值：
        tuple[str, list[dict]]：(替换后文本, 违规明细列表)；输入为空返回 ("", [])。

    异常：
        不抛出（正则异常按原文本返回，保证出口链路不中断）。
    """
    if not text:
        return "", []
    custom = _load_custom_rules()
    ban_rules = custom if custom else _BAN_RULES
    clean = text
    violations: list[dict] = []
    try:
        for category, pattern, replacement in ban_rules:
            hits = pattern.findall(clean)
            if hits:
                violations.append({"category": category, "matched": hits[0]})
                clean = pattern.sub(replacement, clean)
        return clean, violations
    except Exception:  # noqa: BLE001 —— 兜底过滤失败不阻断出口，返回原文
        return text, violations
