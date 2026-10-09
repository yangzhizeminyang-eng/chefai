"""远程开关路由模块。

职责：
    GET /v1/config/switches：读 remote_config 的 switch.* 五键
    （recommend / vision / qa / payment / innovation，05-V1.1 §4.4），缺省 True
    （默认开，60s 内生效语义由每请求直查保证，阶段一不引入 Redis，spec D6）。
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.models import RemoteConfig
from app.schemas.trace import SwitchesResponse

router = APIRouter(prefix="/config", tags=["config"])

# switch.* 键 → 响应字段映射（05-V1.1 §4.4 五个远程开关）
_SWITCH_KEYS = {
    "switch.recommend": "recommend",
    "switch.vision": "vision",
    "switch.qa": "qa",
    "switch.payment": "payment",
    # 模块 O（AI 菜品创新）属阶段二，阶段一仅下发配置
    "switch.innovation": "innovation",
}


@router.get("/switches", response_model=SwitchesResponse, summary="拉取远程模块开关（5 模块）")
def get_switches(session: Session = Depends(get_db)) -> SwitchesResponse:
    """拉取远程模块开关（函数）。

    说明：
        每请求直查 remote_config（行数极少，无缓存必要）；查询异常回退全开
        （开关只做「置灰入口」展示，回退全开不影响业务正确性）。

    参数：
        session：请求级数据库会话。

    返回值：
        SwitchesResponse：五模块开关状态（缺省 True）。

    异常：
        数据库异常内部捕获回退默认值，不向外抛出。
    """
    result = SwitchesResponse()
    try:
        rows = session.execute(
            select(RemoteConfig.config_key, RemoteConfig.value).where(
                RemoteConfig.config_key.in_(_SWITCH_KEYS.keys())
            )
        ).all()
        for config_key, value in rows:
            field = _SWITCH_KEYS.get(config_key)
            if field is not None:
                # JSONB 布尔值直读；非法值视为开启（开关只影响入口置灰）
                setattr(result, field, bool(value) if isinstance(value, bool) else True)
    except Exception:  # noqa: BLE001 —— 开关读取失败回退全开
        return SwitchesResponse()
    return result
