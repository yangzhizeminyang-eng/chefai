"""自然语言入口 Schema 模块。

职责：
    POST /v1/ask 的请求/响应模型。请求双兼容：text（spec/tasks 口径）与
    question（前端 endpoints.ts 实际发送）；响应对齐前端 types.ts AskResponse——
    一票否决时把否决体整体嵌套于 blocked 键（前端读取 res.blocked.trace_id）。
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from app.schemas.common import RiskDetailOut


class AskRequest(BaseModel):
    """自然语言提问请求体（模型类）。

    说明：
        text 与 question 至少其一非空白（路由层校验，空白返回 400）；
        request_id 由前端 axios 拦截器自动注入（幂等键）。

    属性：
        request_id：幂等键（可缺省，后端自动生成）。
        text：提问文本（spec 口径字段）。
        question：提问文本（前端口径字段）。
        anonymous_id：匿名会话 ID（可缺省，风控上下文预留）。
    """

    request_id: str | None = Field(default=None, max_length=40)
    text: str | None = Field(default=None, max_length=500)
    question: str | None = Field(default=None, max_length=500)
    anonymous_id: str | None = Field(default=None, max_length=64)

    def effective_text(self) -> str:
        """取生效的提问文本（函数）。

        返回值：
            str：text 优先，其次 question，均空返回空串。

        异常：
            无。
        """
        return (self.text or self.question or "").strip()


class BlockedResponse(BaseModel):
    """一票否决短路响应体（模型类）。

    说明：
        🔴 D9 红线：本模型不声明 results/candidates/nutrition 字段——
        短路返回体在结构上不承载任何业务内容。

    属性：
        request_id：幂等键回显。
        blocked：是否被阻断（命中阻断规则时恒为 true）。
        overrides_all：一票否决标记（覆盖所有业务输出）。
        risk：风险详情（W-05 三块卡片数据源）。
        disclaimer_id：附着的免责声明 ID。
        trace_id：Agent 调度 trace ID。
    """

    request_id: str | None = None
    blocked: bool
    overrides_all: bool
    risk: RiskDetailOut
    disclaimer_id: str | None = None
    trace_id: str | None = None


class AskResponse(BaseModel):
    """自然语言提问响应体（模型类）。

    说明：
        intent 四态：blocked（命中阻断，blocked 键携带否决体）/ free_qa（受限问答，
        answer 键携带回答）/ recipe_search（菜名搜索，recipe_ids 键携带命中列表）/
        recommend（建议走正式推荐链路）。

    属性：
        request_id：幂等键回显。
        intent：识别的意图。
        answer：受限问答的回答文本（free_qa 时非空）。
        recipe_ids：命中菜谱 ID 列表（recipe_search 时非空）。
        blocked：一票否决短路响应体（blocked 时非空）。
        trace_id：Agent 调度 trace ID。
        disclaimer_id：附着的免责声明 ID。
    """

    request_id: str | None = None
    intent: str
    answer: str | None = None
    recipe_ids: list[int] | None = None
    blocked: BlockedResponse | None = None
    trace_id: str | None = None
    disclaimer_id: str | None = None
