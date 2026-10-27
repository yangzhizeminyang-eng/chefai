"""自然语言入口路由模块。

职责：
    POST /v1/ask：输入闸门 → 意图路由 → 受限问答/菜名搜索；命中阻断返回 G-01 数据。
    POST /v1/search：与 /v1/ask 同一 handler 的别名入口（02-V1.1 §9.1 #15 与
    05-V1.1 §12.3 两种口径并存），共用同一幂等逻辑。
    幂等与 /v1/recommend 共用进程内 TTL 缓存；text 空白返回 400 统一错误。
    响应对齐前端 AskResponse：否决体整体嵌套于 blocked 键（前端读取 res.blocked.trace_id）。
    citations（OBS-04 新增可选字段）：结构化回答来源，检索型为 recipe 来源列表、
    降级/保守模式为 degraded 标注、拦截/无结果为空数组；既有字段不动。
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.api.v1.deps import (
    ERR_BAD_REQUEST,
    adapt_risk,
    api_error,
    resolve_existing_user_id,
    resolve_request_id,
)
from app.core.db import get_db
from app.core.idempotency import get_cached_response, store_response
from app.graph.runner import run_ask
from app.schemas.ask import AskRequest

router = APIRouter(tags=["ask"])

# 幂等缓存使用的规范路径（/v1/search 别名路由共用同一缓存命名空间，保证幂等逻辑一致）
_IDEMPOTENT_PATH = "/v1/ask"


# 02-V1.1 §9.1 #15 与 05-V1.1 §12.3 两种口径并存：
#   - POST /v1/ask 为编排主口径（spec build-stage1-fullstack）；
#   - POST /v1/search 为 02-V1.1 §9.1 接口清单 #15 的独立入口别名。
# 两者复用同一 handler 与同一幂等缓存（规范路径固定 /v1/ask），响应结构完全一致。
@router.post("/ask", summary="自然语言入口（闸门→意图路由→受限问答/搜索；命中阻断返回 G-01）")
@router.post("/search", summary="菜名/问答搜索入口（与 /v1/ask 同实现，02-V1.1 §9.1 #15 口径）")
def post_ask(
    payload: AskRequest,
    request: Request,
    session: Session = Depends(get_db),
) -> JSONResponse:
    """自然语言入口端点（函数）。

    说明：
        编排执行由 app.graph.runner.run_ask 完成（intake_guard 先于业务节点）；
        意图映射：否决体→blocked / safe_mode→free_qa（固定话术）/ qa_answer→free_qa /
        results→recipe_search / 其余→recommend。
        recommend 意图时从问句中按最长匹配提取命中食材名（含别名归一，
        ability.retrieval.extract_ingredient_names_from_text）并入推荐检索入参，
        提升类如「土豆和牛肉能一起做什么」问法的召回覆盖；响应契约不变
        （本端点只回 intent=recommend + trace_id，结果由前端再调 /v1/recommend）。

    参数：
        payload：提问请求体（text 与 question 至少其一非空白）。
        request：FastAPI 请求对象。
        session：请求级数据库会话（risk_log 取证查询用）。

    返回值：
        JSONResponse：200 AskResponse 结构（intent 区分四态）。

    异常：
        HTTPException 400：提问文本空白；其余由编排层兜底。
    """
    input_text = payload.effective_text()
    if not input_text:
        raise api_error(400, ERR_BAD_REQUEST, "提问内容不能为空白", "text/question 均为空")

    # 幂等键：显式传入优先，否则复用中间件 request_id / 请求头，最后自动生成
    rid = resolve_request_id(payload.request_id, request)

    # 幂等命中：直接返回首次响应
    cached = get_cached_response("POST", _IDEMPOTENT_PATH, rid)
    if cached is not None:
        return JSONResponse(
            content=cached,
            headers={"X-Idempotent-Replay": "true", "X-Request-Id": rid},
        )

    # R-2 传参：只读解析既有用户 ID（无身份/用户不存在为 None），供 runner 加载家庭档案
    user_id = resolve_existing_user_id(session, payload.anonymous_id, request)
    response = run_ask({"request_id": rid, "text": input_text, "user_id": user_id})

    # 判别意图并组装响应（前端 AskResponse 契约）
    # citations（OBS-04，新增可选字段，既有字段不动）：结构化回答来源——
    #   检索/推荐型为 [{type:"recipe", id, title}, ...]；降级/保守模式为
    #   [{type:"degraded", reason}]；风控拦截与无结果为空数组。缺省兜底空数组。
    if response.get("blocked"):
        blocked_body = {
            "request_id": response.get("request_id") or rid,
            "blocked": True,
            "overrides_all": bool(response.get("overrides_all")),
            "risk": adapt_risk(response.get("risk")),
            "disclaimer_id": response.get("disclaimer_id"),
            "trace_id": response.get("trace_id"),
        }
        body = {
            "request_id": response.get("request_id") or rid,
            "intent": "blocked",
            "blocked": blocked_body,
            "citations": [],  # 风控拦截未生成任何内容来源
            "trace_id": response.get("trace_id"),
            "disclaimer_id": response.get("disclaimer_id"),
        }
    elif response.get("safe_mode"):
        # 保守模式（风控不可用）：以受限问答形态返回固定话术
        body = {
            "request_id": response.get("request_id") or rid,
            "intent": "free_qa",
            "answer": response.get("message") or "安全校验暂不可用，请稍后重试。",
            "citations": response.get("citations") or [{"type": "degraded", "reason": "safe_mode"}],
            "trace_id": response.get("trace_id"),
            "disclaimer_id": response.get("disclaimer_id"),
        }
    elif response.get("qa_answer"):
        body = {
            "request_id": response.get("request_id") or rid,
            "intent": "free_qa",
            "answer": str(response["qa_answer"]),
            "citations": response.get("citations") or [],
            "trace_id": response.get("trace_id"),
            "disclaimer_id": response.get("disclaimer_id"),
        }
    elif response.get("results"):
        # 搜索/推荐意图：契约响应体不含推荐结果列表，前端跳 W-02 走正式推荐链路
        recipe_ids = [int(r.get("recipe_id")) for r in response["results"] if r.get("recipe_id")]
        body = {
            "request_id": response.get("request_id") or rid,
            "intent": "recipe_search",
            "recipe_ids": recipe_ids,
            "citations": response.get("citations") or [],
            "trace_id": response.get("trace_id"),
            "disclaimer_id": response.get("disclaimer_id"),
        }
    else:
        body = {
            "request_id": response.get("request_id") or rid,
            "intent": "recommend",
            "citations": [],
            "trace_id": response.get("trace_id"),
            "disclaimer_id": response.get("disclaimer_id"),
        }

    store_response("POST", _IDEMPOTENT_PATH, rid, body)
    return JSONResponse(content=body, headers={"X-Request-Id": rid})
