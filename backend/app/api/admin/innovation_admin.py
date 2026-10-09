"""后台创新规则库与巡检路由模块（模块 K，content_ops+）。

职责：
    - GET/POST/PUT/DELETE /admin/v1/innovation/rules：FlavorPairingRule CRUD
      （signed_by_expert 标记透出）；
    - GET /admin/v1/innovation/recipes?status=：AI 创新菜列表；
    - POST /admin/v1/innovation/recipes/{id}/inspect：巡检（用量量化 / 步骤存在 /
      is_ai_innovated 恒真 → {ok, issues[]}，只报告不升格——Q13 口径巡检不自动
      adopt/index）；
    - POST /admin/v1/innovation/recipes/{id}/remove：status → removed + 日志。
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.admin import ERR_NOT_FOUND, api_error, page_args
from app.core.db import get_db
from app.core.security import require_writer, write_operation_log
from app.models import FlavorPairingRule, InnovationRecipe
from app.schemas.admin import PairingRuleCreate, PairingRuleUpdate

router = APIRouter(prefix="/innovation", tags=["后台-创新规则库"])

_MODULE_RULE = "pairing_rule"
_MODULE_RECIPE = "innovation_recipe"


def _rule_snapshot(rule: FlavorPairingRule) -> dict:
    """搭配规则审计快照（函数）。

    参数：
        rule：规则 ORM 实例。

    返回值：
        dict：关键字段字典。

    异常：
        无。
    """
    return {
        "ingredient_a_id": int(rule.ingredient_a_id),
        "ingredient_b_id": int(rule.ingredient_b_id),
        "relation": rule.relation,
        "technique_suggestion": rule.technique_suggestion,
        "rationale": rule.rationale,
        "weight": float(rule.weight),
        "signed_by_expert": bool(rule.signed_by_expert),
    }


def _load_rule_or_404(session: Session, rule_id: int) -> FlavorPairingRule:
    """加载搭配规则或抛 404（函数）。

    参数：
        session：数据库会话。
        rule_id：规则 ID。

    返回值：
        FlavorPairingRule：规则 ORM 实例。

    异常：
        HTTPException 404：规则不存在。
    """
    rule = session.get(FlavorPairingRule, rule_id)
    if rule is None:
        raise api_error(404, ERR_NOT_FOUND, "搭配规则不存在", f"rule_id={rule_id}")
    return rule


@router.get("/rules", summary="风味搭配规则列表")
def list_rules(
    session: Session = Depends(get_db),
    offset_limit: tuple[int, int] = Depends(page_args),
) -> dict:
    """规则列表端点（函数）。

    参数：
        session：请求级数据库会话。
        offset_limit：(offset, limit)。

    返回值：
        dict：{items, total}。

    异常：
        无。
    """
    offset, limit = offset_limit
    total = session.execute(select(func.count(FlavorPairingRule.id))).scalar_one()
    rows = session.execute(
        select(FlavorPairingRule).order_by(FlavorPairingRule.id).offset(offset).limit(limit)
    ).scalars().all()
    return {
        "items": [_rule_snapshot(r) | {"id": int(r.id)} for r in rows],
        "total": int(total),
    }


@router.post("/rules", status_code=201, summary="创建搭配规则")
def create_rule(
    payload: PairingRuleCreate,
    request: Request,
    admin=Depends(require_writer),
    session: Session = Depends(get_db),
) -> dict:
    """创建规则端点（函数）。

    说明：
        UNIQUE(a, b, relation) 冲突 → 409；a/b 食材存在性由 FK 校验兜底。

    参数：
        payload：规则请求体。
        request：FastAPI 请求对象（取 ip）。
        admin：当前管理员（require_writer）。
        session：请求级数据库会话。

    返回值：
        dict：{id} + 规则快照。

    异常：
        HTTPException 409：组合已存在；422：参数非法；403：readonly。
    """
    exists = session.execute(
        select(FlavorPairingRule.id).where(
            FlavorPairingRule.ingredient_a_id == payload.ingredient_a_id,
            FlavorPairingRule.ingredient_b_id == payload.ingredient_b_id,
            FlavorPairingRule.relation == payload.relation,
        )
    ).scalar_one_or_none()
    if exists is not None:
        raise api_error(409, "STATE_CONFLICT", "同食材对同关系规则已存在", None)
    rule = FlavorPairingRule(
        ingredient_a_id=payload.ingredient_a_id,
        ingredient_b_id=payload.ingredient_b_id,
        relation=payload.relation,
        technique_suggestion=payload.technique_suggestion,
        rationale=payload.rationale,
        weight=payload.weight,
        signed_by_expert=payload.signed_by_expert,
    )
    session.add(rule)
    session.flush()
    write_operation_log(
        session, admin, _MODULE_RULE, "create",
        target_type="flavor_pairing_rule", target_id=int(rule.id),
        before=None, after=_rule_snapshot(rule), request=request,
    )
    session.commit()
    return _rule_snapshot(rule) | {"id": int(rule.id)}


@router.put("/rules/{rule_id}", summary="更新搭配规则")
def update_rule(
    rule_id: int,
    payload: PairingRuleUpdate,
    request: Request,
    admin=Depends(require_writer),
    session: Session = Depends(get_db),
) -> dict:
    """更新规则端点（函数）。

    参数：
        rule_id：规则 ID。
        payload：更新请求体（全字段可选）。
        request：FastAPI 请求对象（取 ip）。
        admin：当前管理员（require_writer）。
        session：请求级数据库会话。

    返回值：
        dict：{id} + 更新后快照。

    异常：
        HTTPException 404：规则不存在；403：readonly。
    """
    rule = _load_rule_or_404(session, rule_id)
    before = _rule_snapshot(rule)
    if payload.technique_suggestion is not None:
        rule.technique_suggestion = payload.technique_suggestion
    if payload.rationale is not None:
        rule.rationale = payload.rationale
    if payload.weight is not None:
        rule.weight = payload.weight
    if payload.signed_by_expert is not None:
        rule.signed_by_expert = payload.signed_by_expert
    write_operation_log(
        session, admin, _MODULE_RULE, "update",
        target_type="flavor_pairing_rule", target_id=rule_id,
        before=before, after=_rule_snapshot(rule), request=request,
    )
    session.commit()
    return _rule_snapshot(rule) | {"id": int(rule.id)}


@router.delete("/rules/{rule_id}", summary="删除搭配规则")
def delete_rule(
    rule_id: int,
    request: Request,
    admin=Depends(require_writer),
    session: Session = Depends(get_db),
) -> dict:
    """删除规则端点（函数）。

    参数：
        rule_id：规则 ID。
        request：FastAPI 请求对象（取 ip）。
        admin：当前管理员（require_writer）。
        session：请求级数据库会话。

    返回值：
        dict：{deleted: true}。

    异常：
        HTTPException 404：规则不存在；403：readonly。
    """
    rule = _load_rule_or_404(session, rule_id)
    before = _rule_snapshot(rule)
    session.delete(rule)
    write_operation_log(
        session, admin, _MODULE_RULE, "delete",
        target_type="flavor_pairing_rule", target_id=rule_id,
        before=before, after=None, request=request,
    )
    session.commit()
    return {"deleted": True}


@router.get("/recipes", summary="AI 创新菜列表（status 过滤）")
def list_innovation_recipes(
    status: str | None = None,
    session: Session = Depends(get_db),
    offset_limit: tuple[int, int] = Depends(page_args),
) -> dict:
    """创新菜列表端点（函数）。

    参数：
        status：状态过滤（generated/adopted/indexed/removed，可 None）。
        session：请求级数据库会话。
        offset_limit：(offset, limit)。

    返回值：
        dict：{items, total}；item 含 ingredients/steps/nutrition JSONB 全量。

    异常：
        无。
    """
    offset, limit = offset_limit
    base = select(InnovationRecipe)
    if status:
        base = base.where(InnovationRecipe.status == status)
    total = session.execute(select(func.count()).select_from(base.subquery())).scalar_one()
    rows = session.execute(
        base.order_by(InnovationRecipe.updated_at.desc(), InnovationRecipe.id.desc())
        .offset(offset).limit(limit)
    ).scalars().all()
    return {
        "items": [
            {
                "id": int(r.id),
                "user_id": int(r.user_id),
                "name": r.name,
                "ingredients": list(r.ingredients or []),
                "steps": list(r.steps or []),
                "nutrition": dict(r.nutrition or {}),
                "status": r.status,
                "is_ai_innovated": bool(r.is_ai_innovated),
                "created_at": r.created_at.isoformat() if r.created_at else None,
            }
            for r in rows
        ],
        "total": int(total),
    }


def _load_innovation_or_404(session: Session, recipe_id: int) -> InnovationRecipe:
    """加载创新菜或抛 404（函数）。

    参数：
        session：数据库会话。
        recipe_id：创新菜 ID。

    返回值：
        InnovationRecipe：创新菜 ORM 实例。

    异常：
        HTTPException 404：不存在。
    """
    recipe = session.get(InnovationRecipe, recipe_id)
    if recipe is None:
        raise api_error(404, ERR_NOT_FOUND, "创新菜不存在", f"recipe_id={recipe_id}")
    return recipe


@router.post("/recipes/{recipe_id}/inspect", summary="创新菜巡检（只报告不升格）")
def inspect_innovation_recipe(
    recipe_id: int,
    session: Session = Depends(get_db),
) -> dict:
    """创新菜巡检端点（函数）。

    说明：
        校验三项：(1) 用量量化——ingredients JSONB 每行 amount 数值存在且
        unit 非空；(2) 步骤存在——steps 非空数组；(3) is_ai_innovated 恒真。
        Q13 口径：巡检只报告问题，不自动升格（adopted/indexed 需另行流程）。

    参数：
        recipe_id：创新菜 ID。
        session：请求级数据库会话。

    返回值：
        dict：{ok, issues: [{field, value, reason}], status}。

    异常：
        HTTPException 404：不存在。
    """
    recipe = _load_innovation_or_404(session, recipe_id)
    issues: list[dict] = []
    ingredients = list(recipe.ingredients or [])
    for idx, ing in enumerate(ingredients):
        row = idx + 1
        if not isinstance(ing, dict):
            issues.append({"field": f"ingredients[{row}]", "value": ing, "reason": "条目必须为对象"})
            continue
        amount = ing.get("amount")
        if amount is None or not isinstance(amount, (int, float)):
            issues.append({
                "field": f"ingredients[{row}].amount", "value": amount,
                "reason": "用量数值缺失，未量化",
            })
        if not str(ing.get("unit") or "").strip():
            issues.append({
                "field": f"ingredients[{row}].unit", "value": ing.get("unit"),
                "reason": "用量单位缺失",
            })
    if not list(recipe.steps or []):
        issues.append({"field": "steps", "value": None, "reason": "步骤为空"})
    if not recipe.is_ai_innovated:
        issues.append({
            "field": "is_ai_innovated", "value": recipe.is_ai_innovated,
            "reason": "AI 创新菜标记必须为 true",
        })
    return {"ok": len(issues) == 0, "issues": issues, "status": recipe.status}


@router.post("/recipes/{recipe_id}/remove", summary="创新菜下架（status → removed）")
def remove_innovation_recipe(
    recipe_id: int,
    request: Request,
    admin=Depends(require_writer),
    session: Session = Depends(get_db),
) -> dict:
    """创新菜下架端点（函数）。

    说明：
        status 置 removed（终态，不校验来源状态——巡检下架从任意状态可达）；
        写审计日志。Q13 口径：巡检下架不升格。

    参数：
        recipe_id：创新菜 ID。
        request：FastAPI 请求对象（取 ip）。
        admin：当前管理员（require_writer）。
        session：请求级数据库会话。

    返回值：
        dict：{id, from_status, status:'removed'}。

    异常：
        HTTPException 404：不存在；403：readonly。
    """
    recipe = _load_innovation_or_404(session, recipe_id)
    before = {"status": recipe.status}
    from_status = recipe.status
    recipe.status = "removed"
    write_operation_log(
        session, admin, _MODULE_RECIPE, "remove",
        target_type="innovation_recipe", target_id=recipe_id,
        before=before, after={"status": "removed"}, request=request,
    )
    session.commit()
    return {"id": recipe_id, "from_status": from_status, "status": recipe.status}
