"""结构化日志模块。

职责：
    提供 JSON 结构化日志输出与 request_id 贯穿能力：
    - ContextVar 保存当前请求的 request_id（中间件设置，异步安全）；
    - JsonFormatter 将日志记录序列化为单行 JSON（含时间/级别/模块/request_id）；
    - configure_logging() 在应用启动时装配根日志；get_logger(name) 供各模块取 logger。
"""

import contextvars
import json
import logging
import sys
import uuid
from datetime import UTC, datetime

# 请求级 request_id 上下文（默认 "-"，日志与响应头贯穿同一请求）
request_id_var: contextvars.ContextVar[str] = contextvars.ContextVar("request_id", default="-")

# 日志输出格式保留的字段集合
_RESERVED = logging.LogRecord("x", 0, "x", 0, "x", None, None).__dict__.keys()


class JsonFormatter(logging.Formatter):
    """JSON 结构化日志格式器（模型类）。

    说明：
        将 LogRecord 序列化为单行 JSON，附带 request_id，便于日志采集与检索。
    """

    def format(self, record: logging.LogRecord) -> str:
        """格式化一条日志记录。

        参数：
            record：logging.LogRecord 日志记录对象。

        返回值：
            str：单行 JSON 字符串（含 timestamp/level/logger/message/request_id）。

        异常：
            不主动抛出；字段序列化失败时回退为字符串表示。
        """
        payload = {
            "timestamp": datetime.now(UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "request_id": request_id_var.get(),
        }
        # 附加调用位置，便于定位问题
        payload["location"] = f"{record.pathname}:{record.lineno}"
        # extra 字段合并（跳过 LogRecord 保留字段）
        for key, value in record.__dict__.items():
            if key not in _RESERVED and key not in payload:
                try:
                    json.dumps(value)
                    payload[key] = value
                except (TypeError, ValueError):
                    payload[key] = repr(value)
        return json.dumps(payload, ensure_ascii=False)


def configure_logging(level: int = logging.INFO) -> None:
    """装配根日志：清空默认 handler 后挂载 JSON stdout handler。

    参数：
        level：全局日志级别，默认 INFO。

    返回值：
        None。

    异常：
        无。
    """
    root = logging.getLogger()
    root.setLevel(level)
    # 清空重复 handler，避免 uvicorn/脚本重复执行时日志翻倍
    for handler in list(root.handlers):
        root.removeHandler(handler)
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())
    root.addHandler(handler)


def get_logger(name: str) -> logging.Logger:
    """获取指定名称的 logger。

    参数：
        name：logger 名称，惯例传模块名 __name__。

    返回值：
        logging.Logger：可写结构化日志的 logger 实例。

    异常：
        无。
    """
    return logging.getLogger(name)


def new_request_id() -> str:
    """生成新的 request_id（32 位十六进制，去连字符的 uuid4）。

    返回值：
        str：请求唯一标识。

    异常：
        无。
    """
    return uuid.uuid4().hex
