"""用户档案 Schema 模块。

职责：
    定义 /v1/profile/*（家庭、成员、厨艺设备、饮食目标）与 POST /v1/consent/sensitive
    的请求/响应模型，以及过敏原/设备/目标编码的校验常量与归一化工具。
    字段命名对齐前端 web-stage1/src/api/types.ts 的 FamilyProfile / FamilyMember /
    SkillProfile / DietGoal / ConsentSensitiveResponse 契约。

存储映射说明（🔴 重要）：
    - family_member 表无 relation / custom_allergens 列：relation 仅在接口层透传
      （不持久化，GET 返回默认「本人」）；custom_allergens 与八类编码合并存入
      allergen_codes JSONB（读取时按八类编码集合拆分还原），同时满足表级
      CHECK chk_allergen_required（过敏原必选）；
    - diet_goal 表无 note 列：备注存入 user.preferences JSONB 的 diet_goal_note 键；
    - API 目标编码（control_weight/light_salt/low_sugar）与 DB goal_type CHECK 枚举
      （fat_loss/low_sodium/sugar_control）通过 GOAL_API_TO_DB 双向映射。
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

# ---------------------------------------------------------------------------
# 常量与校验集合
# ---------------------------------------------------------------------------

# GB 7718 八类致敏原编码（与库内 ingredient.allergen_codes / 前端 ALLERGEN_OPTIONS 对齐）：
# gluten 含麸质谷物 / crustacean 甲壳类 / fish 鱼类 / egg 蛋类 /
# peanut 花生 / soybean 大豆 / milk 乳制品 / nuts 坚果断果类
ALLERGEN_CODES: frozenset[str] = frozenset(
    {"gluten", "crustacean", "fish", "egg", "peanut", "soybean", "milk", "nuts"}
)

# 任务口径别名 → 库内编码归一化（wheat 即含麸质谷物、tree_nut 即坚果、
# crustacean_shellfish 即甲壳类），避免不同口径调用方被 422 拒绝
ALLERGEN_ALIASES: dict[str, str] = {
    "wheat": "gluten",
    "tree_nut": "nuts",
    "crustacean_shellfish": "crustacean",
}

# 年龄段枚举（family_member.chk_age_group 表级 CHECK 对齐）
MemberAgeGroup = Literal["0-3", "4-12", "13-17", "18-59", "60+"]

# 13 项厨房设备白名单（与前端 EQUIPMENT_OPTIONS 逐项对齐）
EQUIPMENT_WHITELIST: tuple[str, ...] = (
    "炒锅", "蒸锅", "电饭煲", "空气炸锅", "烤箱", "微波炉", "破壁机",
    "高压锅", "平底锅", "汤锅", "刨丝器", "厨房秤", "砧板",
)

# API 饮食目标编码（前端契约）→ DB diet_goal.goal_type（CHECK 枚举）映射
GOAL_API_TO_DB: dict[str, str] = {
    "control_weight": "fat_loss",
    "muscle_gain": "muscle_gain",
    "light_salt": "low_sodium",
    "low_sugar": "sugar_control",
    "balanced": "balanced",
}

# DB goal_type → API 编码（反向映射，GET 还原前端契约编码）
GOAL_DB_TO_API: dict[str, str] = {v: k for k, v in GOAL_API_TO_DB.items()}

# 疾病相关目标（响应需附加提示语）
DISEASE_RELATED_GOALS: frozenset[str] = frozenset({"light_salt", "low_sugar"})

# 疾病相关目标的固定提示语（仅提示，不含任何诊疗建议内容）
HEALTH_WARNING = "饮食目标涉及健康话题，如有疾病请遵医嘱"

# 过敏原必选校验失败文案（任务口径 detail）
ALLERGEN_REQUIRED_DETAIL = "过敏原为必选：请选择八类过敏原、添加自定义过敏原或确认暂无已知过敏原"

# 默认家庭名（GET /v1/profile/family 自动建档时使用）
DEFAULT_FAMILY_NAME = "我的家庭"

# PIPL 敏感同意版本与场景 → consent_record.scope 映射（scope 受表级 CHECK 枚举约束）
CONSENT_SENSITIVE_VERSION = "SENSITIVE_V1"
SCENE_TO_SCOPE: dict[str, str] = {
    "family_allergen": "allergen",
    "allergen": "allergen",
    "health_goal": "health_goal",
    "diet_goal": "health_goal",
    "special_population": "special_population",
}


# ---------------------------------------------------------------------------
# 归一化工具
# ---------------------------------------------------------------------------

def normalize_allergen_codes(codes: list[str]) -> list[str]:
    """归一化并校验八类过敏原编码列表（函数）。

    说明：
        编码小写化 + 别名映射；不在八类编码集合内的编码视为非法。

    参数：
        codes：原始编码列表。

    返回值：
        list[str]：归一化后的编码列表（保持原顺序，去空白）。

    异常：
        ValueError：存在非法编码（携带非法项说明，由调用方转 422）。
    """
    normalized: list[str] = []
    for code in codes:
        key = str(code).strip().lower()
        if not key:
            continue
        mapped = ALLERGEN_ALIASES.get(key, key)
        if mapped not in ALLERGEN_CODES:
            raise ValueError(f"未知过敏原编码：{code}（允许：{sorted(ALLERGEN_CODES)}）")
        if mapped not in normalized:
            normalized.append(mapped)
    return normalized


def clean_custom_allergens(items: list[str]) -> list[str]:
    """清洗自定义过敏原文本列表（函数）。

    参数：
        items：原始自定义过敏原文本列表。

    返回值：
        list[str]：去空白去重后的文本列表（保持原顺序）。

    异常：
        无。
    """
    cleaned: list[str] = []
    for item in items:
        text = str(item).strip()
        if text and text not in cleaned:
            cleaned.append(text)
    return cleaned


def split_allergen_codes(stored: list[str]) -> tuple[list[str], list[str]]:
    """按八类编码集合拆分存储态过敏原列表（函数）。

    说明：
        存储层将八类编码与自定义过敏原合并写入 allergen_codes JSONB；
        读取时按是否属于八类编码集合还原为接口契约的两段列表。

    参数：
        stored：存储态 allergen_codes JSONB 列表（编码 + 自定义文本混存）。

    返回值：
        tuple[list[str], list[str]]：(八类编码列表, 自定义过敏原列表)。

    异常：
        无。
    """
    codes = [str(c) for c in (stored or []) if str(c) in ALLERGEN_CODES]
    custom = [str(c) for c in (stored or []) if str(c) not in ALLERGEN_CODES]
    return codes, custom


# ---------------------------------------------------------------------------
# 家庭与成员
# ---------------------------------------------------------------------------

class MemberCreate(BaseModel):
    """新增成员请求体（模型类）。

    说明：
        过敏原三选一校验（八类编码 / 自定义 / 暂无已知）在路由层执行；
        age_group 缺省 18-59（DB age_group 列 NOT NULL，前端契约无此字段）。

    属性：
        name：成员姓名（必填，≤10 字符对齐 DB nickname varchar(10)）。
        relation：与本人关系（仅接口层透传，不持久化）。
        age_group：年龄段枚举（缺省 18-59）。
        allergen_codes：八类过敏原编码列表。
        custom_allergens：自定义过敏原文本列表。
        no_known_allergen：是否勾选「暂无已知过敏原」（勾选时清空前两者）。
        taste_spicy/taste_salt/taste_sweet：口味三档 0~2（缺省 1=适中）。
        dietary_restrictions：忌口列表。
        special_diet：特殊饮食列表。
        special_population：特殊人群列表。
    """

    name: str = Field(min_length=1, max_length=10)
    relation: str = Field(default="本人", max_length=20)
    age_group: MemberAgeGroup | None = None
    allergen_codes: list[str] = Field(default_factory=list)
    custom_allergens: list[str] = Field(default_factory=list)
    no_known_allergen: bool = False
    taste_spicy: int = Field(default=1, ge=0, le=2)
    taste_salt: int = Field(default=1, ge=0, le=2)
    taste_sweet: int = Field(default=1, ge=0, le=2)
    dietary_restrictions: list[str] = Field(default_factory=list)
    special_diet: list[str] = Field(default_factory=list)
    special_population: list[str] = Field(default_factory=list)


class MemberUpdate(BaseModel):
    """更新成员请求体（模型类，增量语义）。

    说明：
        全字段可选：未提供的字段保持原值（路由层以 model_fields_set 区分
        「未提供」与「显式空」）；过敏原三选一校验对合并后的生效值执行。

    属性：
        与 MemberCreate 同名字段均可选（None = 未提供，保持原值）。
    """

    name: str | None = Field(default=None, min_length=1, max_length=10)
    relation: str | None = Field(default=None, max_length=20)
    age_group: MemberAgeGroup | None = None
    allergen_codes: list[str] | None = None
    custom_allergens: list[str] | None = None
    no_known_allergen: bool | None = None
    taste_spicy: int | None = Field(default=None, ge=0, le=2)
    taste_salt: int | None = Field(default=None, ge=0, le=2)
    taste_sweet: int | None = Field(default=None, ge=0, le=2)
    dietary_restrictions: list[str] | None = None
    special_diet: list[str] | None = None
    special_population: list[str] | None = None


class MemberOut(BaseModel):
    """成员响应体（模型类，对齐前端 FamilyMember）。

    属性：
        id：成员 ID。
        name：成员姓名。
        relation：与本人关系（阶段一无持久化列，恒返回「本人」）。
        allergen_codes：八类过敏原编码列表（存储态拆分还原）。
        custom_allergens：自定义过敏原文本列表（存储态拆分还原）。
        no_known_allergen：是否暂无已知过敏原。
        taste_spicy/taste_salt/taste_sweet：口味三档 0~2。
        dietary_restrictions：忌口列表。
        special_diet：特殊饮食列表。
        special_population：特殊人群列表。
    """

    id: int
    name: str
    relation: str = "本人"
    allergen_codes: list[str] = Field(default_factory=list)
    custom_allergens: list[str] = Field(default_factory=list)
    no_known_allergen: bool = False
    taste_spicy: int = 1
    taste_salt: int = 1
    taste_sweet: int = 1
    dietary_restrictions: list[str] = Field(default_factory=list)
    special_diet: list[str] = Field(default_factory=list)
    special_population: list[str] = Field(default_factory=list)


class FamilyProfileOut(BaseModel):
    """家庭档案响应体（模型类，对齐前端 FamilyProfile）。

    属性：
        family_id：家庭 ID。
        name：家庭名称。
        members：成员列表。
    """

    family_id: int
    name: str
    members: list[MemberOut] = Field(default_factory=list)


class FamilyNameUpdate(BaseModel):
    """家庭名称更新请求体（模型类）。

    属性：
        name：家庭名称（1~50 字符，对齐 DB family.name varchar(50)）。
    """

    name: str = Field(min_length=1, max_length=50)


# ---------------------------------------------------------------------------
# 厨艺与设备
# ---------------------------------------------------------------------------

class SkillProfileOut(BaseModel):
    """厨艺与设备档案响应体（模型类，对齐前端 SkillProfile）。

    属性：
        cooking_level：厨艺水平 1~5（1 新手 / 5 大厨；无档案时默认 1）。
        equipment：已有设备列表（13 项白名单编码）。
    """

    cooking_level: int
    equipment: list[str] = Field(default_factory=list)


class SkillProfileUpdate(BaseModel):
    """厨艺与设备更新请求体（模型类）。

    属性：
        cooking_level：厨艺水平 1~5。
        equipment：设备列表（逐项须在 13 项白名单内，路由层校验）。
    """

    cooking_level: int = Field(ge=1, le=5)
    equipment: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# 饮食目标
# ---------------------------------------------------------------------------

class DietGoalOut(BaseModel):
    """饮食目标响应体（模型类，对齐前端 DietGoal）。

    说明：
        warning 仅在目标为疾病相关（light_salt/low_sugar）时由 PUT 响应返回
        （路由层配 response_model_exclude_none，GET 恒为 {goal, note} 两字段）。

    属性：
        goal：目标 5 类之一（前端编码）。
        note：备注（存于 user.preferences.diet_goal_note）。
        warning：健康提示语（疾病相关目标时非空，否则省略）。
    """

    goal: str
    note: str = ""
    warning: str | None = None


class DietGoalUpdate(BaseModel):
    """饮食目标更新请求体（模型类）。

    属性：
        goal：目标 5 类之一（前端编码，路由层映射为 DB goal_type）。
        note：备注（≤100 字符，可缺省）。
    """

    goal: Literal["control_weight", "muscle_gain", "light_salt", "low_sugar", "balanced"]
    note: str | None = Field(default=None, max_length=100)


# ---------------------------------------------------------------------------
# PIPL 敏感信息单独同意
# ---------------------------------------------------------------------------

class ConsentSensitiveRequest(BaseModel):
    """敏感同意请求体（模型类）。

    属性：
        scene：同意场景编码（如 family_allergen，路由层映射为 consent_record.scope）。
        anonymous_id：匿名会话 ID（可缺省，读 X-Anonymous-Id 头或新建匿名用户）。
    """

    scene: str = Field(min_length=1, max_length=40)
    anonymous_id: str | None = Field(default=None, max_length=64)


class ConsentSensitiveResponse(BaseModel):
    """敏感同意响应体（模型类，对齐前端 ConsentSensitiveResponse）。

    属性：
        consent_id：同意记录 ID（字符串化，幂等重复提交返回同一记录）。
    """

    consent_id: str
