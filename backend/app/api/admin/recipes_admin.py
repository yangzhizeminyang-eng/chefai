"""后台菜谱管理路由模块（模块 K）。

职责：
    - GET   /admin/v1/recipes?keyword=&status=&page=&size=：分页列表
      （item 含 quantified 全量化判定）；batch-import 路由先于 {recipe_id} 注册；
    - GET   /admin/v1/recipes/{id}：详情（ingredients + steps 全量）；
    - POST  /admin/v1/recipes：创建（draft）；
    - PUT   /admin/v1/recipes/{id}：基础字段 + ingredients/steps 整卡替换
      （before/after 快照写审计日志）；
    - POST  /admin/v1/recipes/{id}/publish：发布闸门——逐行校验用量量化
      （数值与单位双缺 / "适量/少许/若干" 模糊词 → 422 RECIPE_NOT_QUANTIFIED
      定位违规行），通过置 published + 日志；
    - POST  /admin/v1/recipes/{id}/unpublish：published → draft；
    - POST  /admin/v1/recipes/{id}/rollback {log_id}：按操作日志 before_snapshot
      恢复菜谱内容（基础字段 + 食材/步骤整卡重建）+ 写新日志（简化实现：
      仅恢复快照中存在的字段，不做跨版本 diff 合并）；
    - POST  /admin/v1/recipes/batch-import：multipart（format=json|csv|md），
      成功行写 draft，失败行进 errors → {imported, failed, errors}。
"""

from __future__ import annotations

import csv
import io
import json
import re
from typing import Any

from fastapi import APIRouter, Depends, File, Form, Request, UploadFile
from fastapi.responses import JSONResponse
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.admin import ERR_NOT_FOUND, ERR_VALIDATION, api_error, page_args
from app.core.db import get_db
from app.core.logging import get_logger
from app.core.security import require_writer, write_operation_log
from app.models import Ingredient, OperationLog, Recipe, RecipeIngredient, RecipeStep
from app.schemas.admin import RecipeUpsertRequest

router = APIRouter(prefix="/recipes", tags=["后台-菜谱管理"])

logger = get_logger(__name__)

# 模糊用量词（发布校验红线：调味料不得「适量/少许/若干」）
_VAGUE_AMOUNT_RE = re.compile(r"适量|少许|若干")

# 批量导入日志模块标识
_MODULE = "recipe"

# 导入菜谱默认来源标注
_IMPORT_SOURCE_LABEL = "admin_import"
_IMPORT_SOURCE_LICENSE = "admin_import"


def _recipe_snapshot(recipe: Recipe) -> dict:
    """构造菜谱内容快照（函数，供 before/after 审计与回滚）。

    说明：
        包含基础字段与食材/步骤全量行（不含 id/时间戳等系统列），
        rollback 以本结构整卡恢复。

    参数：
        recipe：菜谱 ORM 实例（需已加载 ingredients/steps）。

    返回值：
        dict：可 JSONB 序列化的快照字典。

    异常：
        无。
    """
    return {
        "title": recipe.title,
        "cuisine": recipe.cuisine,
        "cooking_method": recipe.cooking_method,
        "difficulty": int(recipe.difficulty),
        "time_minutes": recipe.time_minutes,
        "servings": int(recipe.servings),
        "calories_kcal": recipe.calories_kcal,
        "tips": recipe.tips,
        "ingredients": [
            {
                "ingredient_id": int(ri.ingredient_id),
                "amount_value": float(ri.amount_value) if ri.amount_value is not None else None,
                "amount_min": float(ri.amount_min) if ri.amount_min is not None else None,
                "amount_max": float(ri.amount_max) if ri.amount_max is not None else None,
                "amount_unit": ri.amount_unit,
                "amount_note": ri.amount_note,
                "amount_type": ri.amount_type,
                "sort_order": int(ri.sort_order),
            }
            for ri in recipe.ingredients
        ],
        "steps": [
            {
                "step_no": int(s.step_no),
                "description": s.description,
                "duration_seconds": s.duration_seconds,
                "key_point": s.key_point,
                "failure_tips": s.failure_tips,
                "amount_hint": s.amount_hint,
            }
            for s in recipe.steps
        ],
    }


def _load_recipe_or_404(session: Session, recipe_id: int) -> Recipe:
    """加载菜谱或抛 404（函数）。

    参数：
        session：数据库会话。
        recipe_id：菜谱 ID。

    返回值：
        Recipe：菜谱 ORM 实例。

    异常：
        HTTPException 404：菜谱不存在。
    """
    recipe = session.get(Recipe, recipe_id)
    if recipe is None:
        raise api_error(404, ERR_NOT_FOUND, "菜谱不存在", f"recipe_id={recipe_id}")
    return recipe


def _is_row_quantified(ri: RecipeIngredient) -> bool:
    """判定单条食材用量是否量化（函数）。

    参数：
        ri：菜谱食材行 ORM。

    返回值：
        bool：amount_value 或 (amount_min 且 amount_max) 存在即量化。

    异常：
        无。
    """
    return ri.amount_value is not None or (
        ri.amount_min is not None and ri.amount_max is not None
    )


def _validate_quantified(recipe: Recipe) -> list[dict]:
    """发布前用量量化校验（函数）。

    说明：
        逐行检查：(1) 数值与单位双缺（amount_value、amount_min/max 均缺）；
        (2) amount_note / 步骤 amount_hint 含「适量/少许/若干」模糊词。
        返回违规明细（行号 1 起定位），空列表即全部通过。

    参数：
        recipe：菜谱 ORM 实例。

    返回值：
        list[dict]：[{row, field, value, reason}]。

    异常：
        无。
    """
    errors: list[dict] = []
    ordered = sorted(recipe.ingredients, key=lambda r: (r.sort_order, r.id))
    for idx, ri in enumerate(ordered):
        row = idx + 1
        if not _is_row_quantified(ri):
            errors.append({
                "row": row,
                "field": "amount_value",
                "value": ri.amount_note,
                "reason": "用量数值与单位缺失，未量化",
            })
        if ri.amount_note and _VAGUE_AMOUNT_RE.search(ri.amount_note):
            errors.append({
                "row": row,
                "field": "amount_note",
                "value": ri.amount_note,
                "reason": "用量备注含模糊词（适量/少许/若干）",
            })
    for step in recipe.steps:
        if step.amount_hint and _VAGUE_AMOUNT_RE.search(step.amount_hint):
            errors.append({
                "row": int(step.step_no),
                "field": "steps.amount_hint",
                "value": step.amount_hint,
                "reason": "步骤用量提示含模糊词（适量/少许/若干）",
            })
    return errors


def _rebuild_children(
    session: Session, recipe: Recipe, payload: RecipeUpsertRequest
) -> None:
    """整卡替换食材与步骤行（函数）。

    说明：
        clear() 触发 delete-orphan 级联删除旧行，flush 后重建（避免
        uq_step_recipe_no 唯一约束在原地更新时冲突）。

    参数：
        session：数据库会话。
        recipe：目标菜谱。
        payload：更新请求体（ingredients/steps 为 None 时跳过重建）。

    返回值：
        None。

    异常：
        sqlalchemy 异常向上抛出（FK 违规等由全局处理器兜底）。
    """
    if payload.ingredients is not None:
        recipe.ingredients.clear()
        session.flush()
        for i, item in enumerate(payload.ingredients):
            recipe.ingredients.append(
                RecipeIngredient(
                    ingredient_id=item.ingredient_id,
                    amount_value=item.amount_value,
                    amount_min=item.amount_min,
                    amount_max=item.amount_max,
                    amount_unit=item.amount_unit,
                    amount_note=item.amount_note,
                    amount_type=item.amount_type,
                    sort_order=item.sort_order or i,
                )
            )
    if payload.steps is not None:
        recipe.steps.clear()
        session.flush()
        for item in payload.steps:
            recipe.steps.append(
                RecipeStep(
                    step_no=item.step_no,
                    description=item.description,
                    duration_seconds=item.duration_seconds,
                    key_point=item.key_point,
                    failure_tips=item.failure_tips,
                    amount_hint=item.amount_hint,
                )
            )


def _apply_snapshot(session: Session, recipe: Recipe, snap: dict) -> None:
    """按快照恢复菜谱内容（函数，rollback 用）。

    说明：
        基础字段 setattr 后整卡重建 ingredients/steps（与 _rebuild_children
        同一物理路径）；快照缺字段按原值保留。

    参数：
        session：数据库会话。
        recipe：目标菜谱。
        snap：_recipe_snapshot 产出的快照字典。

    返回值：
        None。

    异常：
        KeyError/SQLAlchemy 异常向上抛出（快照结构由本模块生成，正常不缺键）。
    """
    for field in ("title", "cuisine", "cooking_method", "difficulty",
                  "time_minutes", "servings", "calories_kcal", "tips"):
        if field in snap and snap[field] is not None:
            setattr(recipe, field, snap[field])
    holder = RecipeUpsertRequest(
        title=recipe.title,
        ingredients=[
            {k: v for k, v in row.items() if v is not None or k == "ingredient_id"}
            for row in snap.get("ingredients", [])
        ],
        steps=list(snap.get("steps", [])),
    )
    _rebuild_children(session, recipe, holder)


# ---------------------------------------------------------------------------
# 批量导入（先注册，避免被 /{recipe_id} 吞掉路径）
# ---------------------------------------------------------------------------
@router.post("/batch-import", summary="菜谱批量导入（json/csv/md，成功行写 draft）")
async def batch_import(
    request: Request,
    file: UploadFile = File(...),
    format: str = Form(default="json"),
    admin=Depends(require_writer),
    session: Session = Depends(get_db),
) -> dict:
    """批量导入端点（函数）。

    说明：
        三种格式解析：json=菜谱数组；csv=扁平列（name,category,ingredient_name,
        amount,unit,step_no,step_desc 按菜名分组展开）；md=简易标记（# 菜名 /
        - 食材 数量单位 / 1. 步骤）。食材名查 ingredient 表精确匹配，缺失或
        用量解析失败的菜谱整行计入 errors 不落库；成功行写 draft + 日志。

    参数：
        request：FastAPI 请求对象（取 ip）。
        file：上传文件。
        format：json|csv|md（表单字段）。
        admin：当前管理员（require_writer）。
        session：请求级数据库会话。

    返回值：
        dict：{imported, failed, errors:[{row, name, reason}]}。

    异常：
        HTTPException 422：format 非法或文件不可解码；403：readonly。
    """
    if format not in ("json", "csv", "md"):
        raise api_error(422, ERR_VALIDATION, "format 必须为 json/csv/md", format)
    raw = await file.read()
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise api_error(422, ERR_VALIDATION, "文件必须为 UTF-8 编码", str(exc)) from exc

    if format == "json":
        dishes, parse_errors = _parse_json(text)
    elif format == "csv":
        dishes, parse_errors = _parse_csv(text)
    else:
        dishes, parse_errors = _parse_md(text)

    errors: list[dict] = list(parse_errors)
    imported = 0
    # 食材名 → id 预解析（一次查询，避免逐菜谱 N+1）
    needed_names = {ing["name"] for d in dishes for ing in d["ingredients"]}
    name_map: dict[str, int] = {}
    if needed_names:
        rows = session.execute(
            select(Ingredient.id, Ingredient.name).where(Ingredient.name.in_(needed_names))
        ).all()
        name_map = {name: int(ing_id) for ing_id, name in rows}

    for order, dish in enumerate(dishes):
        row_no = order + 1
        bad = next(
            (ing for ing in dish["ingredients"] if ing["name"] not in name_map), None
        )
        if bad is not None:
            errors.append({
                "row": row_no, "name": dish["title"],
                "reason": f"食材不存在: {bad['name']}",
            })
            continue
        recipe = Recipe(
            title=dish["title"],
            cuisine=dish.get("cuisine"),
            difficulty=dish.get("difficulty", 2),
            servings=dish.get("servings", 2),
            source_label=_IMPORT_SOURCE_LABEL,
            source_license=_IMPORT_SOURCE_LICENSE,
            status="draft",
        )
        session.add(recipe)
        session.flush()
        for i, ing in enumerate(dish["ingredients"]):
            session.add(
                RecipeIngredient(
                    recipe_id=int(recipe.id),
                    ingredient_id=name_map[ing["name"]],
                    amount_value=ing["amount_value"],
                    amount_unit=ing.get("amount_unit"),
                    amount_note=ing.get("amount_note"),
                    amount_type=ing.get("amount_type", "main"),
                    sort_order=i,
                )
            )
        for step in dish["steps"]:
            session.add(
                RecipeStep(
                    recipe_id=int(recipe.id),
                    step_no=step["step_no"],
                    description=step["description"],
                )
            )
        session.flush()
        write_operation_log(
            session, admin, _MODULE, "import",
            target_type="recipe", target_id=int(recipe.id),
            before=None, after=_recipe_snapshot(recipe), request=request,
        )
        imported += 1
    session.commit()
    return {"imported": imported, "failed": len(errors), "errors": errors}


def _parse_json(text: str) -> tuple[list[dict], list[dict]]:
    """解析 JSON 导入格式（函数）。

    参数：
        text：文件全文（UTF-8）。

    返回值：
        tuple[list[dict], list[dict]]：(规范化菜谱列表, 解析错误列表)。

    异常：
        不抛出（JSON 非法/条目异常均转为 errors）。
    """
    errors: list[dict] = []
    dishes: list[dict] = []
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        return [], [{"row": 0, "reason": f"JSON 解析失败: {exc}"}]
    if not isinstance(data, list):
        return [], [{"row": 0, "reason": "JSON 顶层必须为数组"}]
    for order, item in enumerate(data):
        row_no = order + 1
        try:
            if not isinstance(item, dict):
                raise ValueError("条目必须为对象")
            title = str(item.get("name") or item.get("title") or "").strip()
            if not title:
                raise ValueError("缺少菜名 name")
            ingredients: list[dict] = []
            for ing in item.get("ingredients") or []:
                amount_value = None if ing.get("amount") is None else float(ing["amount"])
                ingredients.append({
                    "name": str(ing.get("name") or "").strip(),
                    "amount_value": amount_value,
                    "amount_unit": ing.get("unit"),
                    "amount_note": ing.get("note"),
                    "amount_type": ing.get("amount_type", "main"),
                })
            steps = [
                {
                    "step_no": int(s.get("no", idx + 1)) if isinstance(s, dict) else idx + 1,
                    "description": s.get("description") if isinstance(s, dict) else str(s),
                }
                for idx, s in enumerate(item.get("steps") or [])
            ]
            dishes.append({
                "title": title,
                "cuisine": item.get("category") or item.get("cuisine"),
                "difficulty": int(item.get("difficulty", 2)),
                "servings": int(item.get("servings", 2)),
                "ingredients": ingredients,
                "steps": steps,
            })
        except (TypeError, ValueError) as exc:
            errors.append({"row": row_no, "reason": f"条目解析失败: {exc}"})
    return dishes, errors


def _parse_csv(text: str) -> tuple[list[dict], list[dict]]:
    """解析 CSV 导入格式（函数）。

    说明：
        扁平列 name,category,ingredient_name,amount,unit,step_no,step_desc；
        按 name 出现顺序分组展开为多菜谱。

    参数：
        text：文件全文。

    返回值：
        tuple[list[dict], list[dict]]：(规范化菜谱列表, 解析错误列表)。

    异常：
        不抛出。
    """
    errors: list[dict] = []
    grouped: dict[str, dict] = {}
    order_of: list[str] = []
    try:
        reader = csv.DictReader(io.StringIO(text))
        for row_no, row in enumerate(reader, start=2):  # 第 1 行为表头
            try:
                name = str(row.get("name") or "").strip()
                if not name:
                    raise ValueError("缺少菜名 name")
                dish = grouped.get(name)
                if dish is None:
                    dish = {
                        "title": name,
                        "cuisine": (row.get("category") or "").strip() or None,
                        "difficulty": 2,
                        "servings": 2,
                        "ingredients": [],
                        "steps": [],
                    }
                    grouped[name] = dish
                    order_of.append(name)
                ing_name = str(row.get("ingredient_name") or "").strip()
                if ing_name:
                    amount_raw = str(row.get("amount") or "").strip()
                    amount_value = float(amount_raw) if amount_raw else None
                    if amount_value is None:
                        raise ValueError(f"食材 {ing_name} 用量为空（必须量化）")
                    dish["ingredients"].append({
                        "name": ing_name,
                        "amount_value": amount_value,
                        "amount_unit": (row.get("unit") or "").strip() or None,
                    })
                step_desc = str(row.get("step_desc") or "").strip()
                if step_desc:
                    step_no_raw = str(row.get("step_no") or "").strip()
                    dish["steps"].append({
                        "step_no": int(step_no_raw) if step_no_raw else len(dish["steps"]) + 1,
                        "description": step_desc,
                    })
            except (TypeError, ValueError) as exc:
                errors.append({"row": row_no, "reason": f"CSV 行解析失败: {exc}"})
    except csv.Error as exc:
        return [], [{"row": 0, "reason": f"CSV 解析失败: {exc}"}]
    return [grouped[n] for n in order_of], errors


_MD_ING_RE = re.compile(r"^-\s+(?P<name>\S+)(?:\s+(?P<amount>[\d.]+)\s*(?P<unit>\S*))?")


def _parse_md(text: str) -> tuple[list[dict], list[dict]]:
    """解析 Markdown 导入格式（函数）。

    说明：
        `# 菜名` 起新菜谱；`- 食材名 数量 单位` 为食材行（数量必须可解析为
        数值，否则该菜谱计失败——落库需满足 chk_amount_quantified）；
        `1. 描述` 为步骤行。

    参数：
        text：文件全文。

    返回值：
        tuple[list[dict], list[dict]]：(规范化菜谱列表, 解析错误列表)。

    异常：
        不抛出。
    """
    dishes: list[dict] = []
    errors: list[dict] = []
    current: dict | None = None
    for line_no, line in enumerate(text.splitlines(), start=1):
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.startswith("# "):
            current = {
                "title": stripped[2:].strip(),
                "cuisine": None,
                "difficulty": 2,
                "servings": 2,
                "ingredients": [],
                "steps": [],
            }
            dishes.append(current)
            continue
        if current is None:
            errors.append({"row": line_no, "reason": "步骤/食材行出现在首个菜名之前"})
            continue
        step_match = re.match(r"^(\d+)[.、]\s*(.+)$", stripped)
        if step_match:
            current["steps"].append({
                "step_no": int(step_match.group(1)),
                "description": step_match.group(2).strip(),
            })
            continue
        ing_match = _MD_ING_RE.match(stripped)
        if ing_match:
            name = ing_match.group("name")
            amount_raw = ing_match.group("amount")
            try:
                amount_value = float(amount_raw) if amount_raw else None
            except ValueError:
                amount_value = None
            if amount_value is None:
                errors.append({
                    "row": line_no, "name": current["title"],
                    "reason": f"食材 {name} 用量缺失或不可解析（必须量化）",
                })
                continue
            current["ingredients"].append({
                "name": name,
                "amount_value": amount_value,
                "amount_unit": ing_match.group("unit"),
            })
    return dishes, errors


# ---------------------------------------------------------------------------
# 列表与详情
# ---------------------------------------------------------------------------
@router.get("", summary="菜谱分页列表（keyword/status 过滤）")
def list_recipes(
    keyword: str | None = None,
    status: str | None = None,
    session: Session = Depends(get_db),
    offset_limit: tuple[int, int] = Depends(page_args),
) -> dict:
    """菜谱列表端点（函数）。

    说明：
        keyword 模糊匹配菜名；status 精确过滤；item.quantified 为全量化判定
        （所有食材行满足 chk_amount_quantified 语义）。

    参数：
        keyword：菜名关键词（可 None）。
        status：状态过滤（draft/published/offline，可 None）。
        session：请求级数据库会话。
        offset_limit：(offset, limit)。

    返回值：
        dict：{items: [{id, name, status, quantified, updated_at}], total}。

    异常：
        403：readonly 之外的鉴权由依赖层处理（GET 仅要求登录）。
    """
    offset, limit = offset_limit
    stmt = select(Recipe)
    count_stmt = select(func.count(Recipe.id))
    if keyword:
        stmt = stmt.where(Recipe.title.ilike(f"%{keyword}%"))
        count_stmt = count_stmt.where(Recipe.title.ilike(f"%{keyword}%"))
    if status:
        stmt = stmt.where(Recipe.status == status)
        count_stmt = count_stmt.where(Recipe.status == status)
    total = session.execute(count_stmt).scalar_one()
    rows = session.execute(
        stmt.order_by(Recipe.updated_at.desc(), Recipe.id.desc()).offset(offset).limit(limit)
    ).scalars().all()
    items = [
        {
            "id": int(r.id),
            "name": r.title,
            "status": r.status,
            "quantified": all(_is_row_quantified(ri) for ri in r.ingredients),
            "updated_at": r.updated_at.isoformat() if r.updated_at else None,
        }
        for r in rows
    ]
    return {"items": items, "total": int(total)}


@router.get("/{recipe_id}", summary="菜谱详情（含食材与步骤全量）")
def get_recipe(
    recipe_id: int, session: Session = Depends(get_db)
) -> dict:
    """菜谱详情端点（函数）。

    参数：
        recipe_id：菜谱 ID。
        session：请求级数据库会话。

    返回值：
        dict：基础字段 + ingredients + steps 全量行。

    异常：
        HTTPException 404：菜谱不存在。
    """
    recipe = _load_recipe_or_404(session, recipe_id)
    data = _recipe_snapshot(recipe)
    data.update({
        "id": int(recipe.id),
        "status": recipe.status,
        "version": int(recipe.version),
        "source_label": recipe.source_label,
    })
    return data


# ---------------------------------------------------------------------------
# 写端点（require_writer：readonly → 403）
# ---------------------------------------------------------------------------
@router.post("", status_code=201, summary="创建菜谱（draft）")
def create_recipe(
    payload: RecipeUpsertRequest,
    request: Request,
    admin=Depends(require_writer),
    session: Session = Depends(get_db),
) -> dict:
    """创建菜谱端点（函数）。

    说明：
        初始 status=draft；title 必填（422）；ingredients/steps 可选随建。

    参数：
        payload：菜谱请求体。
        request：FastAPI 请求对象（取 ip）。
        admin：当前管理员（require_writer）。
        session：请求级数据库会话。

    返回值：
        dict：{id, status}。

    异常：
        HTTPException 422：title 缺失；403：readonly。
    """
    if not payload.title or not payload.title.strip():
        raise api_error(422, ERR_VALIDATION, "title 必填", None)
    recipe = Recipe(
        title=payload.title.strip(),
        cuisine=payload.cuisine,
        cooking_method=payload.cooking_method,
        difficulty=payload.difficulty,
        time_minutes=payload.time_minutes,
        servings=payload.servings,
        calories_kcal=payload.calories_kcal,
        tips=payload.tips,
        source_label="admin_manual",
        source_license="admin_manual",
        status="draft",
    )
    session.add(recipe)
    session.flush()
    _rebuild_children(session, recipe, payload)
    session.flush()
    write_operation_log(
        session, admin, _MODULE, "create",
        target_type="recipe", target_id=int(recipe.id),
        before=None, after=_recipe_snapshot(recipe), request=request,
    )
    session.commit()
    return {"id": int(recipe.id), "status": recipe.status}


@router.put("/{recipe_id}", summary="更新菜谱（ingredients/steps 整卡替换）")
def update_recipe(
    recipe_id: int,
    payload: RecipeUpsertRequest,
    request: Request,
    admin=Depends(require_writer),
    session: Session = Depends(get_db),
) -> dict:
    """更新菜谱端点（函数）。

    说明：
        before 快照 → 应用基础字段与整卡替换 → after 快照写审计日志；
        ingredients/steps 传 None 时对应部分不重建。

    参数：
        recipe_id：菜谱 ID。
        payload：更新请求体。
        request：FastAPI 请求对象（取 ip）。
        admin：当前管理员（require_writer）。
        session：请求级数据库会话。

    返回值：
        dict：{id, status}。

    异常：
        HTTPException 404：菜谱不存在；403：readonly。
    """
    recipe = _load_recipe_or_404(session, recipe_id)
    before = _recipe_snapshot(recipe)
    if payload.title is not None:
        recipe.title = payload.title.strip()
    if payload.cuisine is not None:
        recipe.cuisine = payload.cuisine
    if payload.cooking_method is not None:
        recipe.cooking_method = payload.cooking_method
    recipe.difficulty = payload.difficulty
    if payload.time_minutes is not None:
        recipe.time_minutes = payload.time_minutes
    recipe.servings = payload.servings
    if payload.calories_kcal is not None:
        recipe.calories_kcal = payload.calories_kcal
    if payload.tips is not None:
        recipe.tips = payload.tips
    _rebuild_children(session, recipe, payload)
    session.flush()
    write_operation_log(
        session, admin, _MODULE, "update",
        target_type="recipe", target_id=recipe_id,
        before=before, after=_recipe_snapshot(recipe), request=request,
    )
    session.commit()
    return {"id": recipe_id, "status": recipe.status}


@router.post("/{recipe_id}/publish", summary="发布菜谱（用量量化闸门）")
def publish_recipe(
    recipe_id: int,
    request: Request,
    admin=Depends(require_writer),
    session: Session = Depends(get_db),
) -> Any:
    """发布菜谱端点（函数）。

    说明：
        逐行校验用量量化（数值与单位双缺 / 模糊词），违规 → 422
        {code:'RECIPE_NOT_QUANTIFIED', errors:[{row,field,value,reason}]}；
        通过置 status=published + 审计日志（已发布重复发布幂等返回 200）。

    参数：
        recipe_id：菜谱 ID。
        request：FastAPI 请求对象（取 ip）。
        admin：当前管理员（require_writer）。
        session：请求级数据库会话。

    返回值：
        JSONResponse | dict：422 校验失败体；200 {id, status:'published'}。

    异常：
        HTTPException 404：菜谱不存在；403：readonly。
    """
    recipe = _load_recipe_or_404(session, recipe_id)
    errors = _validate_quantified(recipe)
    if errors:
        return JSONResponse(
            status_code=422,
            content={
                "code": "RECIPE_NOT_QUANTIFIED",
                "message": "菜谱存在未量化用量，无法发布",
                "errors": errors,
            },
        )
    before = {"status": recipe.status}
    recipe.status = "published"
    write_operation_log(
        session, admin, _MODULE, "publish",
        target_type="recipe", target_id=recipe_id,
        before=before, after={"status": recipe.status}, request=request,
    )
    session.commit()
    return {"id": recipe_id, "status": recipe.status}


@router.post("/{recipe_id}/unpublish", summary="下架菜谱（published → draft）")
def unpublish_recipe(
    recipe_id: int,
    request: Request,
    admin=Depends(require_writer),
    session: Session = Depends(get_db),
) -> dict:
    """下架菜谱端点（函数）。

    参数：
        recipe_id：菜谱 ID。
        request：FastAPI 请求对象（取 ip）。
        admin：当前管理员（require_writer）。
        session：请求级数据库会话。

    返回值：
        dict：{id, status:'draft'}。

    异常：
        HTTPException 404：菜谱不存在；403：readonly。
    """
    recipe = _load_recipe_or_404(session, recipe_id)
    before = {"status": recipe.status}
    recipe.status = "draft"
    write_operation_log(
        session, admin, _MODULE, "unpublish",
        target_type="recipe", target_id=recipe_id,
        before=before, after={"status": "draft"}, request=request,
    )
    session.commit()
    return {"id": recipe_id, "status": recipe.status}


@router.post("/{recipe_id}/rollback", summary="按操作日志回滚菜谱内容")
def rollback_recipe(
    recipe_id: int,
    payload: dict,
    request: Request,
    admin=Depends(require_writer),
    session: Session = Depends(get_db),
) -> dict:
    """菜谱回滚端点（函数）。

    说明：
        取目标操作日志（module='recipe'、target_type='recipe'、target_id 匹配）
        的 before_snapshot 整卡恢复菜谱内容，并写 action='rollback' 新日志。
        简化实现：仅恢复快照中存在的字段，不做跨版本 diff 合并。

    参数：
        recipe_id：菜谱 ID。
        payload：{log_id: int}。
        request：FastAPI 请求对象（取 ip）。
        admin：当前管理员（require_writer）。
        session：请求级数据库会话。

    返回值：
        dict：{id, status, rolled_back_to: log_id}。

    异常：
        HTTPException 404：菜谱/日志不存在；422：log_id 缺失或日志不指向该菜谱；
        403：readonly。
    """
    log_id = payload.get("log_id") if isinstance(payload, dict) else None
    if not isinstance(log_id, int):
        raise api_error(422, ERR_VALIDATION, "log_id 必填（整数）", payload)
    recipe = _load_recipe_or_404(session, recipe_id)
    log = session.get(OperationLog, log_id)
    if (
        log is None
        or log.module != _MODULE
        or log.target_type != "recipe"
        or int(log.target_id or 0) != recipe_id
        or not log.before_snapshot
    ):
        raise api_error(
            404, ERR_NOT_FOUND, "操作日志不存在或不指向该菜谱", f"log_id={log_id}"
        )
    _apply_snapshot(session, recipe, dict(log.before_snapshot))
    session.flush()
    write_operation_log(
        session, admin, _MODULE, "rollback",
        target_type="recipe", target_id=recipe_id,
        before=_recipe_snapshot(recipe), after=dict(log.before_snapshot), request=request,
    )
    session.commit()
    return {"id": recipe_id, "status": recipe.status, "rolled_back_to": log_id}
