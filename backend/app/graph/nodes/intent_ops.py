"""专用意图节点模块（M.4/M.5）。

职责：
    三个轻量专用意图节点（替换原统一落 node_free_qa 的处理升级，纯模板拼接、
    不调 LLM，输出经 compose/output_guard 既有链路复核）：

    - node_inventory_op：查该用户库存最近 5 条在库食材 + 临期 3 条，返回结构化
      引导文案（「您库存中有 X 种食材，其中 Y 临近到期…可以把食材加入推荐」）；
    - node_nutrition_query：查 meal_record 今日汇总，返回「今日已记录 N 餐，
      热量约 X kcal（估算值）」模板；无数据 → 补录引导；
    - node_cooking_help：查该用户进行中烹饪会话，返回「检测到进行中的烹饪：
      菜名第 N/M 步…」模板；无会话 → 引导开始新烹饪。

降级口径（M.5 部分输出）：
    state 无数字 user_id（runner 未注入）或查库异常 → 降级为固定引导话术，
    trace span 标 degraded；节点内部全捕获异常，绝不中断主图编排。
"""

from __future__ import annotations

from datetime import date

from sqlalchemy import func, select

from app.core.db import SessionLocal
from app.core.logging import get_logger
from app.graph.nodes.common import make_span, now_ms
from app.graph.registry import register
from app.models import CookingSession, Ingredient, InventoryItem, MealRecord, Recipe, RecipeStep

logger = get_logger(__name__)

# ---- 库存节点话术模板（纯模板拼接，RL-1：话术不由模型生成）----
INV_DEGRADED_TEXT = (
    "暂时无法读取你的库存信息。你可以在「我的库存」页查看和添加食材，"
    "也可以直接选择食材让我为你推荐菜谱。"
)
INV_EMPTY_TEXT = (
    "库存里暂时没有在库食材记录。可以在「我的库存」添加食材，"
    "添加后我可以结合库存帮你推荐菜谱。"
)

# ---- 营养查询节点话术模板 ----
NUT_DEGRADED_TEXT = (
    "暂时无法读取你的饮食记录。你可以在个人中心查看今日营养汇总，"
    "或在「饮食记录」页补录外食。"
)
NUT_EMPTY_TEXT = "今日暂无饮食记录，可在个人中心补录外食。"

# ---- 烹饪求助节点话术模板 ----
HELP_DEGRADED_TEXT = (
    "暂时无法读取烹饪进度。你可以在烹饪会话页查看当前步骤，"
    "或重新选择菜谱开始烹饪，我会逐步引导你完成。"
)
HELP_EMPTY_TEXT = (
    "当前没有进行中的烹饪会话。可以从推荐结果选一道菜开始，"
    "烹饪中遇到糊锅/太咸等问题随时告诉我。"
)


def _coerce_user_id(state: dict) -> int | None:
    """从编排状态解析数字 user_id（函数）。

    说明：
        阶段一 runner._init_state 仅注入 user_id_hash（脱敏哈希），不注入数字
        user_id——本函数对缺失/非数字形态统一返回 None，由节点走降级话术；
        后续 runner 注入数字 user_id 后各专用节点查库路径自动生效（零改动）。

    参数：
        state：编排状态。

    返回值：
        int | None：数字 user_id；缺失或不可转 int 时返回 None。

    异常：
        不抛出（TypeError/ValueError 内部消化）。
    """
    raw = state.get("user_id")
    if raw is None:
        return None
    try:
        return int(raw)
    except (TypeError, ValueError):
        return None


def make_node_inventory_op():
    """库存查询专用节点工厂（函数）。

    返回值：
        Callable：节点函数。

    异常：
        无。
    """

    def node_inventory_op(state: dict) -> dict:
        """库存查询节点：最近 5 条在库 + 临期 3 条（函数）。

        说明：
            - 有数字 user_id → 查 inventory_item（status IN normal/expiring，
              最近 5 条）与临期条目（status=expiring，按到期日升序前 3 条），
              模板拼接「您库存中有 X 种食材，其中 Y 临近到期…可以把食材加入推荐」；
            - 无库存记录 → 空库存引导话术；
            - 无 user_id 或查库异常 → 固定引导话术（M.5 部分输出，span 标 degraded）。

        参数：
            state：编排状态（user_id 可缺省）。

        返回值：
            dict：{"qa_answer": 引导文案, "trace": [span]}。

        异常：
            不抛出（查库异常转降级话术）。
        """
        start = now_ms()
        uid = _coerce_user_id(state)
        answer = INV_DEGRADED_TEXT
        status = "degraded"
        if uid is not None:
            try:
                with SessionLocal() as session:
                    rows = session.execute(
                        select(Ingredient.name, InventoryItem.status)
                        .join(Ingredient, Ingredient.id == InventoryItem.ingredient_id)
                        .where(InventoryItem.user_id == uid)
                        .where(InventoryItem.status.in_(("normal", "expiring")))
                        .order_by(InventoryItem.created_at.desc(), InventoryItem.id.desc())
                        .limit(5)
                    ).all()
                    expiring_rows = session.execute(
                        select(Ingredient.name)
                        .join(Ingredient, Ingredient.id == InventoryItem.ingredient_id)
                        .where(InventoryItem.user_id == uid)
                        .where(InventoryItem.status == "expiring")
                        .order_by(InventoryItem.expiry_date.asc().nullslast(), InventoryItem.id.asc())
                        .limit(3)
                    ).all()
                if not rows:
                    answer = INV_EMPTY_TEXT
                    status = "ok"
                else:
                    names = [str(r[0]) for r in rows]
                    expiring_names = [str(r[0]) for r in expiring_rows]
                    expiring_part = (
                        f"其中 {len(expiring_names)} 件临近到期（{'、'.join(expiring_names)}），"
                        if expiring_names
                        else ""
                    )
                    answer = (
                        f"您库存中有 {len(names)} 种食材（{'、'.join(names)}），"
                        f"{expiring_part}建议优先消耗临期食材。可以把这些食材加入推荐，"
                        f"我来帮你安排菜谱。"
                    )
                    status = "ok"
            except Exception as exc:  # noqa: BLE001 —— 查库异常降级固定引导话术
                logger.warning("node_inventory_op degraded: %s", exc)
                answer = INV_DEGRADED_TEXT
                status = "degraded"
        span = make_span("node_inventory_op", status, now_ms() - start)
        return {"qa_answer": answer, "trace": [span]}

    return node_inventory_op


def make_node_nutrition_query():
    """营养查询专用节点工厂（函数）。

    返回值：
        Callable：节点函数。

    异常：
        无。
    """

    def node_nutrition_query(state: dict) -> dict:
        """饮食记录今日汇总节点（函数）。

        说明：
            - 有数字 user_id → 查 meal_record 当日（服务器本地日期）记录数与
              热量合计，返回「今日已记录 N 餐，热量约 X kcal（估算值）」；
            - 无记录 → 「今日暂无饮食记录，可在个人中心补录外食」；
            - 无 user_id 或查库异常 → 固定引导话术（span 标 degraded）。

        参数：
            state：编排状态（user_id 可缺省）。

        返回值：
            dict：{"qa_answer": 汇总/引导文案, "trace": [span]}。

        异常：
            不抛出（查库异常转降级话术）。
        """
        start = now_ms()
        uid = _coerce_user_id(state)
        answer = NUT_DEGRADED_TEXT
        status = "degraded"
        if uid is not None:
            try:
                with SessionLocal() as session:
                    rows = session.execute(
                        select(MealRecord.kcal)
                        .where(MealRecord.user_id == uid)
                        .where(MealRecord.recorded_date == date.today())
                    ).all()
                if not rows:
                    answer = NUT_EMPTY_TEXT
                else:
                    total_kcal = sum(float(r[0] or 0) for r in rows)
                    answer = (
                        f"今日已记录 {len(rows)} 餐，热量约 {round(total_kcal)} kcal"
                        f"（估算值，仅供参考）。"
                    )
                status = "ok"
            except Exception as exc:  # noqa: BLE001 —— 查库异常降级固定引导话术
                logger.warning("node_nutrition_query degraded: %s", exc)
                answer = NUT_DEGRADED_TEXT
                status = "degraded"
        span = make_span("node_nutrition_query", status, now_ms() - start)
        return {"qa_answer": answer, "trace": [span]}

    return node_nutrition_query


def make_node_cooking_help():
    """烹饪求助专用节点工厂（函数）。

    返回值：
        Callable：节点函数。

    异常：
        无。
    """

    def node_cooking_help(state: dict) -> dict:
        """进行中烹饪会话查询节点（函数）。

        说明：
            - 有数字 user_id → 查 cooking_session 最近一条 status='ongoing' 会话
              （联 recipe 取菜名、同会话统计 recipe_step 总步数），返回
              「检测到进行中的烹饪：菜名第 N/M 步…」；
            - 无进行中会话 → 引导开始新烹饪话术；
            - 无 user_id 或查库异常 → 固定引导话术（span 标 degraded）。

        参数：
            state：编排状态（user_id 可缺省）。

        返回值：
            dict：{"qa_answer": 进度/引导文案, "trace": [span]}。

        异常：
            不抛出（查库异常转降级话术）。
        """
        start = now_ms()
        uid = _coerce_user_id(state)
        answer = HELP_DEGRADED_TEXT
        status = "degraded"
        if uid is not None:
            try:
                with SessionLocal() as session:
                    row = session.execute(
                        select(
                            CookingSession.current_step_no,
                            CookingSession.recipe_id,
                            Recipe.title,
                        )
                        .join(Recipe, Recipe.id == CookingSession.recipe_id)
                        .where(CookingSession.user_id == uid)
                        .where(CookingSession.status == "ongoing")
                        .order_by(CookingSession.created_at.desc(), CookingSession.id.desc())
                        .limit(1)
                    ).first()
                    if row is None:
                        answer = HELP_EMPTY_TEXT
                    else:
                        current_step = int(row[0] or 1)
                        recipe_id = int(row[1])
                        title = str(row[2])
                        total = int(
                            session.execute(
                                select(func.count(RecipeStep.id)).where(
                                    RecipeStep.recipe_id == recipe_id
                                )
                            ).scalar_one()
                        )
                        answer = (
                            f"检测到进行中的烹饪：《{title}》当前第 {current_step}/{total} 步。"
                            f"遇到糊锅、太咸等问题可以直接描述情况，我会给你应急建议。"
                        )
                status = "ok"
            except Exception as exc:  # noqa: BLE001 —— 查库异常降级固定引导话术
                logger.warning("node_cooking_help degraded: %s", exc)
                answer = HELP_DEGRADED_TEXT
                status = "degraded"
        span = make_span("node_cooking_help", status, now_ms() - start)
        return {"qa_answer": answer, "trace": [span]}

    return node_cooking_help


# ---- 注册（主图按注册表动态装配；节点位于 supervisor 之后、compose 之前）----
register(
    "node_inventory_op",
    make_node_inventory_op,
    forms="rule",
    timeout_ms=1000,
    description="库存查询专用节点：在库 5 条 + 临期 3 条模板应答（无 user_id/异常降级）",
)
register(
    "node_nutrition_query",
    make_node_nutrition_query,
    forms="rule",
    timeout_ms=1000,
    description="营养查询专用节点：meal_record 今日汇总模板应答（无 user_id/异常降级）",
)
register(
    "node_cooking_help",
    make_node_cooking_help,
    forms="rule",
    timeout_ms=1000,
    description="烹饪求助专用节点：进行中会话进度模板应答（无 user_id/异常降级）",
)
