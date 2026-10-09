"""认证与同意 Schema 模块。

职责：
    POST /v1/auth/anonymous 与 POST /v1/consent/disclaimer 的请求/响应模型。
    兼容两种请求字段：agreement_version（spec 口径）与 disclaimer_version（前端实际发送）。
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class AnonymousRequest(BaseModel):
    """匿名会话请求体（模型类）。

    说明：
        前端仅发送 client_type（types.ts AnonymousResponse 只消费 anonymous_id）；
        anonymous_id 可选传入以复用既有匿名用户（upsert 语义）。

    属性：
        anonymous_id：客户端已持有的匿名 ID（传入则复用，缺省由后端生成 anon_ 前缀新 ID）。
        client_type：客户端类型标识（如 web_stage1，仅记录用途）。
    """

    anonymous_id: str | None = Field(default=None, max_length=64)
    client_type: str | None = Field(default=None, max_length=30)


class AnonymousResponse(BaseModel):
    """匿名会话响应体（模型类）。

    属性：
        user_id：用户表主键（阶段一无登录语义，供关联写库用）。
        anonymous_id：匿名会话 ID（前端持久化 localStorage 并随请求头携带）。
    """

    user_id: int
    anonymous_id: str


class ConsentRequest(BaseModel):
    """免责同意请求体（模型类）。

    说明：
        版本字段双兼容：agreement_version（spec/tasks 口径）与 disclaimer_version
        （前端 endpoints.ts 实际发送），两者均缺省时按 DISCLAIMER_V1 处理；
        anonymous_id 可由请求体或 X-Anonymous-Id 请求头提供，均缺省时后端先建匿名用户。

    属性：
        anonymous_id：匿名会话 ID（可选，缺省读请求头或新建用户）。
        agreement_version：同意的免责声明版本（spec 口径字段）。
        disclaimer_version：同意的免责声明版本（前端口径字段）。
    """

    anonymous_id: str | None = Field(default=None, max_length=64)
    agreement_version: str | None = Field(default=None, max_length=20)
    disclaimer_version: str | None = Field(default=None, max_length=20)

    def effective_version(self) -> str:
        """取生效的免责声明版本（函数）。

        返回值：
            str：agreement_version 优先，其次 disclaimer_version，均空则 DISCLAIMER_V1。

        异常：
            无。
        """
        return self.agreement_version or self.disclaimer_version or "DISCLAIMER_V1"


class ConsentResponse(BaseModel):
    """免责同意响应体（模型类）。

    属性：
        ok：是否记录成功（幂等重复同意同样返回 true）。
    """

    ok: bool
