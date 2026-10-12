"""视觉识别路由模块（spec 模块 D，tag=识别与语音）。

职责：
    POST /v1/vision/recognize：拍照识别食材（multipart 字段 file）；
    POST /v1/vision/confirm：确认识别结果（校验食材在 ingredient/alias 表存在性）。

关键约定：
    - 开关：remote_config switch.vision=false → 403（识别入口置灰）；
    - 额度：免费 3 次/日、会员（存在 status='paid' 订单）10 次/日；用量持久化在
      user.preferences JSONB（vision_usage: {date, used}），与 T4 会员口径一致
      （⚠️ 为避免与并行代理 T4 阻塞，额度函数在本文件内私有实现（_get_quota /
      _consume_quota），未 import app.ability.member；T4 完成后可直接切换 import）；
    - 降级红线：provider 异常 / 全低置信（无 high 项）一律【不扣额度】；
    - 图片落盘：仅在有 high 置信项时保存到 backend/uploads/{yyyymmdd}/{uuid}.jpg；
    - 每次调用顺手清理 uploads 中超过 24h 的过期文件（ability.uploads）。
"""

from __future__ import annotations

import uuid
from datetime import date
from pathlib import Path

from fastapi import APIRouter, Depends, File, Request, UploadFile
from fastapi.responses import JSONResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ability.providers import get_vision_provider
from app.ability.uploads import cleanup_uploads
from app.api.v1.deps import (
    ERR_VALIDATION,
    api_error,
    get_or_create_user,
    resolve_anonymous_id,
)
from app.core.db import get_db
from app.core.logging import get_logger
from app.models import Ingredient, IngredientAlias, Order, RemoteConfig, User
from app.schemas.vision import (
    VisionConfirmRequest,
    VisionConfirmResponse,
    VisionRecognizeResponse,
)

router = APIRouter(prefix="/vision", tags=["识别与语音"])

logger = get_logger(__name__)

# 远程开关键（与 app/api/v1/config.py 的 _SWITCH_KEYS 口径一致）
_VISION_SWITCH_KEY = "switch.vision"

# 识别额度（spec：免费 3 次/日、会员 10 次/日；会员判定与 T4 会员接口同口径）
FREE_DAILY_LIMIT = 3
MEMBER_DAILY_LIMIT = 10

# 用量在 user.preferences 中的持久化键
_VISION_USAGE_KEY = "vision_usage"

# 图片落盘根目录（backend/uploads；本文件位于 backend/app/api/v1/，向上四级为 backend/）
_UPLOAD_BASE_DIR = Path(__file__).resolve().parents[3] / "uploads"


def _is_member(session: Session, user_id: int) -> bool:
    """判定用户是否会员（函数）。

    说明：
        简化口径：order 表存在 status='paid' 的订单即会员（与 T4 会员 me 接口
        口径一致，便于后续对齐）；查询异常按免费档降级。

    参数：
        session：数据库会话。
        user_id：用户 ID。

    返回值：
        bool：True 会员（额度 10）/ False 免费档（额度 3）。

    异常：
        不抛出（查询异常按免费档降级）。
    """
    try:
        row = session.execute(
            select(Order.id).where(Order.user_id == user_id, Order.status == "paid").limit(1)
        ).first()
        return row is not None
    except Exception as exc:  # noqa: BLE001 —— 会员判定失败按免费档降级
        logger.warning("vision member check failed: %s", exc)
        return False


def _get_quota(session: Session, user: User) -> dict:
    """读取用户当日识别额度（函数）。

    说明：
        用量持久化在 user.preferences JSONB 的 vision_usage 键
        （{"date": "YYYY-MM-DD", "used": n}），非当日用量视为 0。

    参数：
        session：数据库会话。
        user：用户 ORM 实例。

    返回值：
        dict：{used: int, limit: int, remaining: int}。

    异常：
        不抛出（preferences 结构异常按 0 用量处理）。
    """
    limit = MEMBER_DAILY_LIMIT if _is_member(session, int(user.id)) else FREE_DAILY_LIMIT
    used = 0
    try:
        usage = (user.preferences or {}).get(_VISION_USAGE_KEY) or {}
        if isinstance(usage, dict) and usage.get("date") == date.today().isoformat():
            used = int(usage.get("used") or 0)
    except (TypeError, ValueError) as exc:
        logger.warning("vision quota parse failed: %s", exc)
        used = 0
    return {"used": used, "limit": limit, "remaining": max(0, limit - used)}


def _consume_quota(session: Session, user: User, n: int = 1) -> bool:
    """扣减用户当日识别额度（函数）。

    说明：
        先校验剩余额度，足够则用量 +n 并提交（user.preferences 重新赋值触发
        JSONB 变更跟踪）；额度不足返回 False 不扣减。

    参数：
        session：数据库会话。
        user：用户 ORM 实例。
        n：扣减次数（默认 1）。

    返回值：
        bool：True 扣减成功 / False 额度不足。

    异常：
        数据库异常向上抛出（由全局异常处理器兜底）。
    """
    quota = _get_quota(session, user)
    if quota["remaining"] < n:
        return False
    today = date.today().isoformat()
    prefs = dict(user.preferences or {})
    usage = prefs.get(_VISION_USAGE_KEY) or {}
    used = int(usage.get("used") or 0) if isinstance(usage, dict) and usage.get("date") == today else 0
    prefs[_VISION_USAGE_KEY] = {"date": today, "used": used + n}
    user.preferences = prefs  # 整体重赋值，确保 JSONB 变更被跟踪
    session.commit()
    return True


def _is_vision_enabled(session: Session) -> bool:
    """读取 remote_config 的 switch.vision 开关（函数）。

    说明：
        与 config.py 口径一致：读取失败/非法值按开启处理（开关只做入口置灰）。

    参数：
        session：数据库会话。

    返回值：
        bool：开关状态（缺省 True）。

    异常：
        不抛出（查询异常按开启降级）。
    """
    try:
        value = session.execute(
            select(RemoteConfig.value).where(RemoteConfig.config_key == _VISION_SWITCH_KEY)
        ).scalar_one_or_none()
        if isinstance(value, bool):
            return value
    except Exception as exc:  # noqa: BLE001 —— 开关读取失败按开启降级
        logger.warning("read switch.vision failed: %s", exc)
    return True


def _save_image(image_bytes: bytes) -> str | None:
    """将识别图片保存到 uploads/{yyyymmdd}/{uuid}.jpg（函数）。

    说明：
        仅在有 high 置信识别项（已扣额度）时调用；保存失败吞掉打日志，
        不影响响应。

    参数：
        image_bytes：图片原始字节。

    返回值：
        str | None：保存路径；失败返回 None。

    异常：
        不抛出（IO 异常吞掉打日志）。
    """
    day_dir = _UPLOAD_BASE_DIR / date.today().strftime("%Y%m%d")
    try:
        day_dir.mkdir(parents=True, exist_ok=True)
        path = day_dir / f"{uuid.uuid4().hex}.jpg"
        path.write_bytes(image_bytes)
        return str(path)
    except Exception as exc:  # noqa: BLE001 —— 留档失败不影响识别响应
        logger.warning("save upload image failed: %s", exc)
        return None


@router.post(
    "/recognize",
    response_model=VisionRecognizeResponse,
    summary="拍照识别食材（阶段一 mock 视觉适配器，额度 3/日·会员 10/日）",
)
def post_vision_recognize(
    request: Request,
    file: UploadFile = File(..., description="图片文件（jpg/png 等）"),
    session: Session = Depends(get_db),
):
    """拍照识别食材端点（函数）。

    说明：
        流程：开关校验（false→403）→ 用户解析（X-Anonymous-Id 惯例）→ 额度校验
        （不足→429）→ provider 识别（异常→200 degraded 不扣额度）→ 全低置信不扣
        额度 → 有 high 项扣 1 次额度并留档图片。每次调用顺手清理 24h 前的
        过期上传文件。

    参数：
        request：FastAPI 请求对象（解析 X-Anonymous-Id）。
        file：上传图片文件（multipart 字段名 file）。
        session：请求级数据库会话。

    返回值：
        dict / JSONResponse：200 识别结果（recognized/degraded/message/quota）、
        403 开关关闭、429 额度不足（含 quota）。quota 结构
        {used, limit, remaining}：limit 免费档 3 次/日（FREE_DAILY_LIMIT）、
        会员 10 次/日（MEMBER_DAILY_LIMIT，存在 status='paid' 订单即会员）。

    异常：
        HTTPException 422：上传文件为空；其余异常由全局处理器兜底。
    """
    # ① 远程开关：识别入口置灰
    if not _is_vision_enabled(session):
        raise api_error(403, "FORBIDDEN", "识别功能暂未开放，请手动选择食材")

    # ② 用户解析（X-Anonymous-Id → user 现有惯例；缺省自动建匿名用户）
    anonymous_id = resolve_anonymous_id(None, request)
    user = get_or_create_user(session, anonymous_id)

    # ③ 读取图片字节（同步读取 UploadFile 内存缓冲，不额外落盘）
    image_bytes = file.file.read() or b""
    if not image_bytes:
        raise api_error(422, ERR_VALIDATION, "请上传图片文件")

    # ④ 旁路清理：每次调用顺手清理 uploads 中 >24h 的过期文件
    cleanup_uploads(_UPLOAD_BASE_DIR, max_age_hours=24)

    # ⑤ 额度校验：不足直接 429（响应体携带 quota 供前端展示）
    quota = _get_quota(session, user)
    if quota["remaining"] <= 0:
        return JSONResponse(
            status_code=429,
            content={"code": "QUOTA_EXCEEDED", "message": "今日识别次数已用完", "quota": quota},
        )

    # ⑥ 调用 provider：异常降级为手动选食材，🔴 不扣额度
    try:
        items = get_vision_provider().recognize(image_bytes)
    except Exception as exc:  # noqa: BLE001 —— provider 失败降级，不扣额度
        logger.warning("vision provider failed: %s", exc)
        return {
            "recognized": [],
            "degraded": True,
            "message": "识别暂时不可用，请手动选择食材",
            "quota": quota,
        }

    serialized = [
        {"name": item.name, "confidence": item.confidence, "ingredient_id": item.ingredient_id}
        for item in items
    ]

    # ⑦ 全低置信（无 high 项）：同样 🔴 不扣额度
    if not any(item.confidence == "high" for item in items):
        return {
            "recognized": serialized,
            "degraded": False,
            "message": "未能准确识别食材，请手动选择或重拍",
            "quota": quota,
        }

    # ⑧ 有 high 置信项：扣 1 次额度（并发竞态时可能扣减失败 → 429）
    if not _consume_quota(session, user, 1):
        fresh = _get_quota(session, user)
        return JSONResponse(
            status_code=429,
            content={"code": "QUOTA_EXCEEDED", "message": "今日识别次数已用完", "quota": fresh},
        )

    # ⑨ 留档图片（仅成功识别场景；失败不影响响应）并返回扣减后的额度
    _save_image(image_bytes)
    quota_after = _get_quota(session, user)
    return {
        "recognized": serialized,
        "degraded": False,
        "quota": quota_after,
    }


@router.post(
    "/confirm",
    response_model=VisionConfirmResponse,
    summary="确认识别结果（校验食材存在性，伪食材跳过）",
)
def post_vision_confirm(
    payload: VisionConfirmRequest,
    session: Session = Depends(get_db),
) -> dict:
    """确认识别结果端点（函数）。

    说明：
        逐个校验 names 在 ingredient 表（名称或别名）是否存在：存在计入 added
        （前端加入已选集合，后端不入库），不存在列入 skipped 跳过。

    参数：
        payload：确认请求体（names 待校验食材名列表）。
        session：请求级数据库会话。

    返回值：
        dict：{added: int, skipped: list[str]}。

    异常：
        查询异常时按全部跳过降级（added=0，skipped=全部名字），不阻断前端。
    """
    # 去重保序（重复名只校验一次）
    names: list[str] = []
    for raw in payload.names:
        name = str(raw or "").strip()
        if name and name not in names:
            names.append(name)
    if not names:
        return {"added": 0, "skipped": []}

    try:
        existing = {
            str(name)
            for (name,) in session.execute(select(Ingredient.name).where(Ingredient.name.in_(names))).all()
        }
        missing = [n for n in names if n not in existing]
        if missing:
            # 别名二次校验（如「西红柿」→ 番茄）
            alias_rows = session.execute(
                select(IngredientAlias.alias).where(IngredientAlias.alias.in_(missing))
            ).all()
            existing |= {str(alias) for (alias,) in alias_rows}
    except Exception as exc:  # noqa: BLE001 —— 校验失败按全部跳过降级
        logger.warning("vision confirm lookup failed: %s", exc)
        return {"added": 0, "skipped": names}

    skipped = [n for n in names if n not in existing]
    return {"added": len(names) - len(skipped), "skipped": skipped}
