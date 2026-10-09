"""用户档案路由模块。

职责：
    GET/PUT /v1/profile/family：家庭档案（无家庭自动建档 name=我的家庭）；
    POST/PUT/DELETE /v1/profile/members[/{id}]：家庭成员增删改（过敏原三选一必选校验）；
    GET/PUT /v1/profile/skill：厨艺与设备（设备白名单校验，含燃气灶等灶具）；
    GET/PUT /v1/profile/diet-goal：饮食目标（疾病相关目标附加健康提示语）。

身份与存储约定：
    - 当前用户由 get_current_user 依赖解析（X-Anonymous-Id 头 → user 表，
      缺失/不存在时自动 upsert 匿名用户，跟随 auth/consent 惯例）；
    - custom_allergens 与八类编码合并存 family_member.allergen_codes（读取时按
      八类集合拆分还原），relation 无持久化列仅接口层透传；
    - 饮食目标 goal 经 GOAL_API_TO_DB 映射落 diet_goal.goal_type（对齐 DB CHECK 枚举），
      note 存 user.preferences.diet_goal_note。
"""

from __future__ import annotations

from datetime import UTC, date, datetime

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.v1.deps import ERR_NOT_FOUND, ERR_VALIDATION, api_error, get_current_user
from app.core.db import get_db
from app.models import DietGoal, Family, FamilyMember, User, UserSkillProfile
from app.schemas.profile import (
    DEFAULT_FAMILY_NAME,
    DISEASE_RELATED_GOALS,
    EQUIPMENT_WHITELIST,
    GOAL_API_TO_DB,
    GOAL_DB_TO_API,
    HEALTH_WARNING,
    DietGoalOut,
    DietGoalUpdate,
    FamilyNameUpdate,
    FamilyProfileOut,
    MemberCreate,
    MemberOut,
    MemberUpdate,
    SkillProfileOut,
    SkillProfileUpdate,
    clean_custom_allergens,
    normalize_allergen_codes,
    split_allergen_codes,
)

router = APIRouter(prefix="/profile", tags=["档案与同意"])


# ---------------------------------------------------------------------------
# 内部工具
# ---------------------------------------------------------------------------

def _get_or_create_family(session: Session, user_id: int) -> Family:
    """获取用户默认家庭，不存在则自动建档（函数）。

    参数：
        session：数据库会话。
        user_id：用户 ID。

    返回值：
        Family：家庭 ORM 实例（新建行已 flush，主键可用，提交由调用方负责）。

    异常：
        SQLAlchemyError：数据库异常向上抛出（全局异常处理器兜底）。
    """
    family = session.execute(
        select(Family)
        .where(Family.user_id == user_id)
        .where(Family.deleted_at.is_(None))
        .order_by(Family.id)
        .limit(1)
    ).scalar_one_or_none()
    if family is None:
        family = Family(user_id=user_id, name=DEFAULT_FAMILY_NAME)
        session.add(family)
        session.flush()
    return family


def _load_members(session: Session, family_id: int) -> list[FamilyMember]:
    """加载家庭下未删除成员（函数）。

    参数：
        session：数据库会话。
        family_id：家庭 ID。

    返回值：
        list[FamilyMember]：按 ID 升序的成员列表（软删行已过滤）。

    异常：
        无。
    """
    return list(
        session.execute(
            select(FamilyMember)
            .where(FamilyMember.family_id == family_id)
            .where(FamilyMember.deleted_at.is_(None))
            .order_by(FamilyMember.id)
        ).scalars().all()
    )


def _member_to_out(member: FamilyMember) -> MemberOut:
    """成员 ORM 行 → 接口契约响应体（函数）。

    说明：
        存储态 allergen_codes（八类编码 + 自定义文本混存）按八类集合拆分为
        allergen_codes / custom_allergens 两段；relation 无持久化列，返回默认「本人」。

    参数：
        member：成员 ORM 实例。

    返回值：
        MemberOut：契约响应体。

    异常：
        无。
    """
    codes, custom = split_allergen_codes(list(member.allergen_codes or []))
    return MemberOut(
        id=int(member.id),
        name=str(member.nickname),
        relation="本人",
        allergen_codes=codes,
        custom_allergens=custom,
        no_known_allergen=bool(member.no_known_allergen),
        taste_spicy=int(member.taste_spicy if member.taste_spicy is not None else 1),
        taste_salt=int(member.taste_salt if member.taste_salt is not None else 1),
        taste_sweet=int(member.taste_sweet if member.taste_sweet is not None else 1),
        dietary_restrictions=list(member.dietary_restrictions or []),
        special_diet=list(member.special_diet or []),
        special_population=list(member.special_population or []),
    )


def _family_profile_out(session: Session, family: Family) -> FamilyProfileOut:
    """家庭 ORM 行 + 成员列表 → 家庭档案响应体（函数）。

    参数：
        session：数据库会话。
        family：家庭 ORM 实例。

    返回值：
        FamilyProfileOut：{family_id, name, members}。

    异常：
        无。
    """
    members = _load_members(session, int(family.id))
    return FamilyProfileOut(
        family_id=int(family.id),
        name=str(family.name),
        members=[_member_to_out(m) for m in members],
    )


def _merge_allergen_storage(
    allergen_codes: list[str], custom_allergens: list[str], no_known_allergen: bool
) -> tuple[list[str], bool]:
    """过敏原三选一校验并生成存储态列表（函数）。

    说明：
        互斥归一化：勾选「暂无已知过敏原」时清空两段；任一段非空时视为有过敏原。
        三者皆空抛 422（任务口径 detail 文案）；八类编码经别名归一化，
        非法编码抛 422。存储态 = 八类编码 + 自定义文本合并（满足表级
        CHECK chk_allergen_required，读取端按集合拆分还原）。

    参数：
        allergen_codes：八类过敏原编码列表（原始输入）。
        custom_allergens：自定义过敏原文本列表（原始输入）。
        no_known_allergen：是否勾选「暂无已知过敏原」。

    返回值：
        tuple[list[str], bool]：(存储态 allergen_codes 合并列表, 生效 no_known_allergen)。

    异常：
        HTTPException 422：三选一未满足 / 八类编码非法。
    """
    if no_known_allergen:
        return [], True
    try:
        codes = normalize_allergen_codes(list(allergen_codes or []))
    except ValueError as exc:
        raise api_error(422, ERR_VALIDATION, "过敏原编码不合法", str(exc)) from exc
    custom = clean_custom_allergens(list(custom_allergens or []))
    merged = list(codes)
    for item in custom:
        if item not in merged:
            merged.append(item)
    if not merged:
        raise api_error(422, ERR_VALIDATION, "过敏原为必选", "过敏原为必选：请选择八类过敏原、添加自定义过敏原或确认暂无已知过敏原")
    return merged, False


def _load_member_or_404(session: Session, user_id: int, member_id: int) -> FamilyMember:
    """加载当前用户家庭下的成员，否则 404（函数）。

    说明：
        经 family JOIN 校验归属（防止跨用户按 ID 越权操作他人成员）。

    参数：
        session：数据库会话。
        user_id：当前用户 ID。
        member_id：成员 ID。

    返回值：
        FamilyMember：成员 ORM 实例。

    异常：
        HTTPException 404：成员不存在、已软删或不属于当前用户家庭。
    """
    member = session.execute(
        select(FamilyMember)
        .join(Family, Family.id == FamilyMember.family_id)
        .where(FamilyMember.id == member_id)
        .where(FamilyMember.deleted_at.is_(None))
        .where(Family.deleted_at.is_(None))
        .where(Family.user_id == user_id)
    ).scalar_one_or_none()
    if member is None:
        raise api_error(404, ERR_NOT_FOUND, "家庭成员不存在", f"member_id={member_id}")
    return member


# ---------------------------------------------------------------------------
# 家庭档案
# ---------------------------------------------------------------------------

@router.get("/family", response_model=FamilyProfileOut, summary="获取家庭档案（无家庭自动建档）")
def get_family_profile(
    user: User = Depends(get_current_user),
    session: Session = Depends(get_db),
) -> FamilyProfileOut:
    """获取家庭档案端点（函数）。

    说明：
        用户名下无未删除家庭时自动创建 name=我的家庭 的默认家庭（幂等：重复
        GET 返回同一 family_id）。

    参数：
        user：当前用户（依赖注入）。
        session：请求级数据库会话。

    返回值：
        FamilyProfileOut：{family_id, name, members}。

    异常：
        数据库异常向上抛出（全局异常处理器兜底 500）。
    """
    family = _get_or_create_family(session, int(user.id))
    session.commit()
    return _family_profile_out(session, family)


@router.put("/family", response_model=FamilyProfileOut, summary="更新家庭名称")
def update_family_name(
    payload: FamilyNameUpdate,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_db),
) -> FamilyProfileOut:
    """更新家庭名称端点（函数）。

    参数：
        payload：{name}（1~50 字符，空白拒收）。
        user：当前用户（依赖注入）。
        session：请求级数据库会话。

    返回值：
        FamilyProfileOut：更新后的完整家庭档案（含成员）。

    异常：
        HTTPException 422：名称空白；数据库异常向上抛出。
    """
    name = payload.name.strip()
    if not name:
        raise api_error(422, ERR_VALIDATION, "家庭名称不能为空白", "name 为空白")
    family = _get_or_create_family(session, int(user.id))
    family.name = name
    session.commit()
    return _family_profile_out(session, family)


# ---------------------------------------------------------------------------
# 家庭成员
# ---------------------------------------------------------------------------

@router.post("/members", response_model=MemberOut, status_code=201, summary="新增家庭成员（过敏原必选）")
def create_member(
    payload: MemberCreate,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_db),
) -> MemberOut:
    """新增家庭成员端点（函数）。

    说明：
        过敏原三选一必选：allergen_codes / custom_allergens / no_known_allergen
        至少满足其一，否则 422；勾选暂无已知时清空两段（互斥语义对齐前端）。

    参数：
        payload：成员数据（name 必填）。
        user：当前用户（依赖注入）。
        session：请求级数据库会话。

    返回值：
        MemberOut：创建成功的成员（含后端生成的 id）。

    异常：
        HTTPException 422：过敏原三选一未满足 / 编码非法 / 姓名空白；
        数据库异常向上抛出。
    """
    name = payload.name.strip()
    if not name:
        raise api_error(422, ERR_VALIDATION, "成员姓名不能为空白", "name 为空白")
    merged, no_known = _merge_allergen_storage(
        payload.allergen_codes, payload.custom_allergens, payload.no_known_allergen
    )
    family = _get_or_create_family(session, int(user.id))
    member = FamilyMember(
        family_id=int(family.id),
        nickname=name,
        age_group=payload.age_group or "18-59",
        taste_spicy=payload.taste_spicy,
        taste_salt=payload.taste_salt,
        taste_sweet=payload.taste_sweet,
        dietary_restrictions=list(payload.dietary_restrictions or []),
        allergen_codes=merged,
        no_known_allergen=no_known,
        special_diet=list(payload.special_diet or []),
        special_population=list(payload.special_population or []),
    )
    session.add(member)
    session.commit()
    return _member_to_out(member)


@router.put("/members/{member_id}", response_model=MemberOut, summary="更新家庭成员（增量，校验同新增）")
def update_member(
    member_id: int,
    payload: MemberUpdate,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_db),
) -> MemberOut:
    """更新家庭成员端点（函数）。

    说明：
        增量语义：以 model_fields_set 区分「未提供」与「显式空」，未提供字段
        保持原值；过敏原三选一校验对合并后的生效值执行（只改口味时既有
        过敏原仍然满足必选）。

    参数：
        member_id：成员 ID。
        payload：待更新字段（均可选）。
        user：当前用户（依赖注入）。
        session：请求级数据库会话。

    返回值：
        MemberOut：更新后的成员。

    异常：
        HTTPException 404：成员不存在或不属于当前用户；
        HTTPException 422：生效值过敏原三选一未满足 / 编码非法 / 姓名空白。
    """
    member = _load_member_or_404(session, int(user.id), member_id)
    provided = payload.model_fields_set

    if "name" in provided and payload.name is not None:
        name = payload.name.strip()
        if not name:
            raise api_error(422, ERR_VALIDATION, "成员姓名不能为空白", "name 为空白")
        member.nickname = name

    # 过敏原：未提供的段从存储态拆分还原为生效值，再统一做三选一校验
    stored_codes, stored_custom = split_allergen_codes(list(member.allergen_codes or []))
    effective_codes = payload.allergen_codes if "allergen_codes" in provided else stored_codes
    effective_custom = payload.custom_allergens if "custom_allergens" in provided else stored_custom
    effective_no_known = (
        payload.no_known_allergen if "no_known_allergen" in provided else bool(member.no_known_allergen)
    )
    merged, no_known = _merge_allergen_storage(effective_codes, effective_custom, effective_no_known)
    member.allergen_codes = merged
    member.no_known_allergen = no_known

    if "taste_spicy" in provided and payload.taste_spicy is not None:
        member.taste_spicy = payload.taste_spicy
    if "taste_salt" in provided and payload.taste_salt is not None:
        member.taste_salt = payload.taste_salt
    if "taste_sweet" in provided and payload.taste_sweet is not None:
        member.taste_sweet = payload.taste_sweet
    if "dietary_restrictions" in provided and payload.dietary_restrictions is not None:
        member.dietary_restrictions = list(payload.dietary_restrictions)
    if "special_diet" in provided and payload.special_diet is not None:
        member.special_diet = list(payload.special_diet)
    if "special_population" in provided and payload.special_population is not None:
        member.special_population = list(payload.special_population)

    session.commit()
    return _member_to_out(member)


@router.delete("/members/{member_id}", status_code=204, summary="删除家庭成员（软删，允许删空）")
def delete_member(
    member_id: int,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_db),
) -> None:
    """删除家庭成员端点（函数）。

    说明：
        软删除（置 deleted_at）；家庭允许删空（无最少成员数约束）。

    参数：
        member_id：成员 ID。
        user：当前用户（依赖注入）。
        session：请求级数据库会话。

    返回值：
        None：204 无响应体。

    异常：
        HTTPException 404：成员不存在或不属于当前用户。
    """
    member = _load_member_or_404(session, int(user.id), member_id)
    member.deleted_at = datetime.now(UTC)
    session.commit()


# ---------------------------------------------------------------------------
# 厨艺与设备
# ---------------------------------------------------------------------------

@router.get("/skill", response_model=SkillProfileOut, summary="获取厨艺与设备档案（无则默认值）")
def get_skill_profile(
    user: User = Depends(get_current_user),
    session: Session = Depends(get_db),
) -> SkillProfileOut:
    """获取厨艺与设备档案端点（函数）。

    说明：
        user_skill_profile 一人一份；无档案行时返回默认值 level=1 / 空设备
        （不建行，首次 PUT 时才落库）。

    参数：
        user：当前用户（依赖注入）。
        session：请求级数据库会话。

    返回值：
        SkillProfileOut：{cooking_level, equipment}。

    异常：
        数据库异常向上抛出（全局异常处理器兜底 500）。
    """
    row = session.execute(
        select(UserSkillProfile).where(UserSkillProfile.user_id == int(user.id))
    ).scalar_one_or_none()
    if row is None:
        return SkillProfileOut(cooking_level=1, equipment=[])
    return SkillProfileOut(cooking_level=int(row.difficulty_cap), equipment=list(row.equipment or []))


@router.put("/skill", response_model=SkillProfileOut, summary="保存厨艺与设备（设备白名单校验）")
def update_skill_profile(
    payload: SkillProfileUpdate,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_db),
) -> SkillProfileOut:
    """保存厨艺与设备档案端点（函数）。

    说明：
        equipment 逐项校验设备白名单（EQUIPMENT_WHITELIST，白名单外 422）；
        DB skill_level 枚举（beginner/skilled/expert）由 cooking_level 映射
        （1-2/3/4-5），difficulty_cap 同步存 cooking_level（GET 以此回读）。

    参数：
        payload：{cooking_level, equipment}。
        user：当前用户（依赖注入）。
        session：请求级数据库会话。

    返回值：
        SkillProfileOut：保存后的档案。

    异常：
        HTTPException 422：设备不在白名单；数据库异常向上抛出。
    """
    equipment: list[str] = []
    for item in payload.equipment:
        name = str(item).strip()
        if not name:
            continue
        if name not in EQUIPMENT_WHITELIST:
            raise api_error(
                422,
                ERR_VALIDATION,
                "设备不在支持列表内",
                f"未知设备：{name}（允许：{list(EQUIPMENT_WHITELIST)}）",
            )
        if name not in equipment:
            equipment.append(name)

    skill_level = "beginner" if payload.cooking_level <= 2 else (
        "skilled" if payload.cooking_level == 3 else "expert"
    )
    row = session.execute(
        select(UserSkillProfile).where(UserSkillProfile.user_id == int(user.id))
    ).scalar_one_or_none()
    if row is None:
        row = UserSkillProfile(
            user_id=int(user.id),
            skill_level=skill_level,
            difficulty_cap=payload.cooking_level,
            equipment=equipment,
        )
        session.add(row)
    else:
        row.skill_level = skill_level
        row.difficulty_cap = payload.cooking_level
        row.equipment = equipment
    session.commit()
    return SkillProfileOut(cooking_level=payload.cooking_level, equipment=equipment)


# ---------------------------------------------------------------------------
# 饮食目标
# ---------------------------------------------------------------------------

def _load_diet_goal_note(user: User) -> str:
    """读取用户偏好中的饮食目标备注（函数）。

    参数：
        user：用户 ORM 实例。

    返回值：
        str：备注文本（无则空串）。

    异常：
        无。
    """
    prefs = user.preferences if isinstance(user.preferences, dict) else {}
    return str(prefs.get("diet_goal_note") or "")


@router.get("/diet-goal", response_model=DietGoalOut, response_model_exclude_none=True,
            summary="获取饮食目标（无则默认 balanced）")
def get_diet_goal(
    user: User = Depends(get_current_user),
    session: Session = Depends(get_db),
) -> DietGoalOut:
    """获取饮食目标端点（函数）。

    说明：
        goal 从 diet_goal 表最新行读取（DB goal_type 反向映射为前端编码），
        note 从 user.preferences.diet_goal_note 读取；无记录返回
        {goal: balanced, note: 空}。

    参数：
        user：当前用户（依赖注入）。
        session：请求级数据库会话。

    返回值：
        DietGoalOut：{goal, note}。

    异常：
        数据库异常向上抛出（全局异常处理器兜底 500）。
    """
    row = session.execute(
        select(DietGoal).where(DietGoal.user_id == int(user.id)).order_by(DietGoal.id.desc()).limit(1)
    ).scalar_one_or_none()
    goal = GOAL_DB_TO_API.get(str(row.goal_type), "balanced") if row is not None else "balanced"
    return DietGoalOut(goal=goal, note=_load_diet_goal_note(user))


@router.put("/diet-goal", response_model=DietGoalOut, response_model_exclude_none=True,
            summary="保存饮食目标（疾病相关目标返回健康提示）")
def update_diet_goal(
    payload: DietGoalUpdate,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_db),
) -> DietGoalOut:
    """保存饮食目标端点（函数）。

    说明：
        goal 经 GOAL_API_TO_DB 映射落 diet_goal.goal_type（对齐 DB CHECK 枚举：
        control_weight→fat_loss / light_salt→low_sodium / low_sugar→sugar_control），
        upsert 最新一行；note 写 user.preferences.diet_goal_note。目标为
        light_salt/low_sugar 时响应附加固定提示语 warning（仅提示，无诊疗建议）。

    参数：
        payload：{goal, note?}。
        user：当前用户（依赖注入）。
        session：请求级数据库会话。

    返回值：
        DietGoalOut：{goal, note[, warning]}。

    异常：
        数据库异常向上抛出（全局异常处理器兜底 500）。
    """
    row = session.execute(
        select(DietGoal).where(DietGoal.user_id == int(user.id)).order_by(DietGoal.id.desc()).limit(1)
    ).scalar_one_or_none()
    goal_type = GOAL_API_TO_DB[payload.goal]
    if row is None:
        row = DietGoal(user_id=int(user.id), goal_type=goal_type, effective_from=date.today())
        session.add(row)
    else:
        row.goal_type = goal_type

    note = (payload.note or "").strip()
    prefs = dict(user.preferences or {})
    prefs["diet_goal_note"] = note
    user.preferences = prefs

    session.commit()
    out = DietGoalOut(goal=payload.goal, note=note)
    if payload.goal in DISEASE_RELATED_GOALS:
        out.warning = HEALTH_WARNING
    return out
