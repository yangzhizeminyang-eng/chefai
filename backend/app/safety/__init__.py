"""safety 包：风控引擎（纯规则，不调模型）。

公共导出：
    RiskEngine / get_risk_engine：规则引擎与单例；
    RiskVerdict / SafetyProfile / UNKNOWN_VERDICT：类型与兜底常量；
    sanitize：输出侧敏感词二级替换；
    write_risk_log：风控日志落库。
"""

from app.safety.engine import RiskEngine, get_risk_engine
from app.safety.logger import sanitize_digest, write_risk_log
from app.safety.sensitive_words import sanitize
from app.safety.types import UNKNOWN_VERDICT, RiskVerdict, SafetyProfile

__all__ = [
    "RiskEngine",
    "get_risk_engine",
    "RiskVerdict",
    "SafetyProfile",
    "UNKNOWN_VERDICT",
    "sanitize",
    "sanitize_digest",
    "write_risk_log",
]
