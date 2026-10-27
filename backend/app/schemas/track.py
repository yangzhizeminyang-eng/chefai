"""埋点接口 Pydantic 模型。

职责：
    定义 POST /v1/track/events 请求体结构，字段口径与
    web-mini/src/api/endpoints.ts 的 TrackEventPayload 逐字对齐：
    {name, props?, ts, request_id}。
"""

from pydantic import BaseModel, Field


class TrackEventIn(BaseModel):
    """单条埋点事件负载（模型类）。

    说明：
        props 由调用方传入任意 JSON 对象（服务端写入前剥离敏感键值并校验
        字节数上限）；ts 为客户端本地毫秒时间戳（可缺省，服务端不校验时钟）；
        request_id 为客户端生成事件时的幂等键（可缺省）。

    属性：
        name：事件名（白名单校验在 API 层完成，这里仅约束非空与长度）。
        props：事件属性（可 None）。
        ts：事件发生时间（毫秒时间戳，可 None）。
        request_id：关联请求标识（可 None）。

    异常：
        ValidationError：name 缺失/超长或 request_id 超长时由 FastAPI 转 422。
    """

    name: str = Field(..., min_length=1, max_length=64)
    props: dict | None = None
    ts: int | None = None
    request_id: str | None = Field(None, max_length=64)


class TrackBatchRequest(BaseModel):
    """批量埋点请求体（模型类）。

    说明：
        events 批量条数上限由 API 层按 settings.TRACK_BATCH_MAX 校验
        （超出 422），不在 Pydantic 字段约束中写死以便配置生效。

    属性：
        events：事件数组（客户端缓冲整批提交）。

    异常：
        ValidationError：events 缺失或元素结构非法时由 FastAPI 转 422。
    """

    events: list[TrackEventIn] = Field(default_factory=list)
