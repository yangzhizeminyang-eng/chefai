"""风控日志落库模块。

职责：
    将每次风控扫描结果写入 risk_log 表（规则 ID / 输入摘要脱敏 / 处置 / 时间），
    供后台复核与验收取证（架构文档 §5 第 8 问）。
    写入失败仅记录日志、绝不阻断主链路响应。
"""

from __future__ import annotations

import re

from sqlalchemy.orm import Session

from app.core.logging import get_logger
from app.models import RiskLog
from app.safety.types import RiskVerdict

logger = get_logger(__name__)

# 脱敏正则：中国大陆手机号 / 18 位身份证（含尾号 X）/ 15 位旧身份证
_PHONE_RE = re.compile(r"1[3-9]\d{9}")
_ID_CARD_RE = re.compile(r"\d{17}[\dXx]|\d{15}")

# 摘要最大保留长度（字符）
_DIGEST_MAX_LEN = 60


def sanitize_digest(text: str) -> str:
    """生成脱敏输入摘要（函数）。

    说明：
        先替换手机号/身份证号为 *，再截取前 60 字符；
        脱敏在先、截取在后，避免敏感信息因截取边界漏出。

    参数：
        text：原始输入文本。

    返回值：
        str：脱敏后的摘要（最长 60 字符）。

    异常：
        不抛出（输入为 None 等异常时返回空串）。
    """
    if not text:
        return ""
    try:
        masked = _PHONE_RE.sub("*" * 11, text)
        masked = _ID_CARD_RE.sub("*" * 18, masked)
        return masked[:_DIGEST_MAX_LEN]
    except Exception:  # noqa: BLE001 —— 脱敏失败直接不落原文
        return "[digest_error]"


def write_risk_log(
    session: Session,
    request_id: str,
    stage: str,
    verdict: RiskVerdict | dict,
    input_text: str,
    action: str,
) -> bool:
    """写入一条风控日志（函数）。

    说明：
        verdict 兼容 RiskVerdict 对象与 dict（graph 节点内存的是 dict 形态）；
        写入失败（数据库异常等）仅告警日志，返回 False，绝不向调用方抛异常。

    参数：
        session：调用方提供的 SQLAlchemy 会话（提交与关闭由调用方负责）。
        request_id：请求唯一标识。
        stage：扫描阶段（input / output）。
        verdict：风控判定结果（RiskVerdict 或其 model_dump() 字典）。
        input_text：原始输入文本（内部自动脱敏）。
        action：处置动作（blocked / safe_mode / passed）。

    返回值：
        bool：写入成功返回 True，失败返回 False。

    异常：
        不抛出（内部捕获所有异常）。
    """
    try:
        # 兼容对象与 dict 两种形态，统一按字段取值
        get = verdict.get if isinstance(verdict, dict) else lambda k, d=None: getattr(verdict, k, d)
        row = RiskLog(
            request_id=request_id,
            stage=stage,
            rule_code=get("rule_code"),
            category=get("category"),
            risk_level=get("risk_level"),
            input_digest=sanitize_digest(input_text),
            action=action,
            message_id=get("message_id"),
        )
        session.add(row)
        session.commit()
        return True
    except Exception as exc:  # noqa: BLE001 —— 日志留痕失败绝不阻断主链路
        logger.error("write risk_log failed (request_id=%s): %s", request_id, exc)
        try:
            session.rollback()
        except Exception:  # noqa: BLE001
            pass
        return False
