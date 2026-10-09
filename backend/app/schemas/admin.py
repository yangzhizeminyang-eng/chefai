"""后台管理端 Schema 模块（模块 K）。

职责：
    定义 /admin/v1/** 全部请求体 Pydantic 模型（响应体多处直接用 dict 组装，
    请求体统一走本模块以获得 422 校验）：
    - 鉴权：AdminLoginRequest；
    - 成员：AdminUserCreate / AdminUserUpdate；
    - 菜谱：RecipeIngredientIn / RecipeStepIn / RecipeUpsertRequest /
      PublishActionRequest / RollbackRequest / BatchImportRequest（multipart 表单直收）；
    - 食材/营养：IngredientCreate / IngredientUpdate / AliasCreate /
      NutritionUpsertRequest；
    - 风控：RiskRuleCreate / RiskRuleUpdate / RiskRuleToggle /
      SensitiveWordItem / SensitiveWordsPut / SensitiveWordAppend；
    - 反馈：FeedbackTransition；
    - 开关：SwitchesPut；
    - 订单：OrderCompensate；
    - 创新：PairingRuleCreate / PairingRuleUpdate。
"""

from __future__ import annotations

from pydantic import BaseModel, Field, field_validator

# 三级角色合法枚举（admin_user.role CHECK 同口径）
ADMIN_ROLES = ("super_admin", "content_ops", "readonly")

# 账号状态合法枚举（admin_user.status）
ADMIN_STATUSES = ("active", "disabled")

# 风控规则类别（risk_rule.category CHECK 五类）
RISK_CATEGORIES = (
    "food_safety_high_risk",
    "special_population",
    "medical_refusal",
    "pseudoscience",
    "output_ban",
)

# 风控阶段（risk_rule.stage_scope CHECK）
RISK_STAGES = ("input", "output", "both")

# 风险等级（risk_rule.risk_level CHECK）
RISK_LEVELS = ("critical", "high", "medium")

# 食材 10 分类（ingredient.category CHECK 同口径）
INGREDIENT_CATEGORIES = (
    "veg", "meat", "seafood", "egg_milk", "soy",
    "staple", "seasoning", "dry", "frozen", "other",
)

# 菜谱食材用量类型（recipe_ingredient.amount_type CHECK）
AMOUNT_TYPES = ("main", "minor", "seasoning")

# 搭配规则关系（flavor_pairing_rule.relation CHECK）
PAIRING_RELATIONS = ("recommend", "conflict", "taboo")


# ---------------------------------------------------------------------------
# 鉴权与成员管理
# ---------------------------------------------------------------------------
class AdminLoginRequest(BaseModel):
    """登录请求体（模型类）。

    属性：
        username：用户名。
        password：明文密码。
    """

    username: str = Field(min_length=1, max_length=50)
    password: str = Field(min_length=1, max_length=128)


class AdminUserCreate(BaseModel):
    """创建管理员请求体（模型类）。

    属性：
        username：用户名（唯一）。
        password：明文密码（落库前 pbkdf2_sha256 哈希）。
        role：三级角色枚举。
        status：账号状态（缺省 active）。
    """

    username: str = Field(min_length=1, max_length=50)
    password: str = Field(min_length=6, max_length=128)
    role: str
    status: str = "active"

    @field_validator("role")
    @classmethod
    def _check_role(cls, v: str) -> str:
        """校验角色枚举（内部函数）。

        参数：
            v：角色字符串。

        返回值：
            str：合法角色。

        异常：
            ValueError：非法角色（Pydantic 转 422）。
        """
        if v not in ADMIN_ROLES:
            raise ValueError(f"role 必须为 {'/'.join(ADMIN_ROLES)}")
        return v

    @field_validator("status")
    @classmethod
    def _check_status(cls, v: str) -> str:
        """校验状态枚举（内部函数）。

        参数：
            v：状态字符串。

        返回值：
            str：合法状态。

        异常：
            ValueError：非法状态（Pydantic 转 422）。
        """
        if v not in ADMIN_STATUSES:
            raise ValueError(f"status 必须为 {'/'.join(ADMIN_STATUSES)}")
        return v


class AdminUserUpdate(BaseModel):
    """更新管理员请求体（模型类）：全部字段可选（函数）。

    属性：
        role：新角色（可选）。
        status：新状态（可选）。
        password：新明文密码（可选，落库前哈希）。
    """

    role: str | None = None
    status: str | None = None
    password: str | None = Field(default=None, min_length=6, max_length=128)

    @field_validator("role")
    @classmethod
    def _check_role(cls, v: str | None) -> str | None:
        """校验角色枚举（内部函数）。

        参数：
            v：角色字符串或 None。

        返回值：
            str | None：合法角色。

        异常：
            ValueError：非法角色。
        """
        if v is not None and v not in ADMIN_ROLES:
            raise ValueError(f"role 必须为 {'/'.join(ADMIN_ROLES)}")
        return v

    @field_validator("status")
    @classmethod
    def _check_status(cls, v: str | None) -> str | None:
        """校验状态枚举（内部函数）。

        参数：
            v：状态字符串或 None。

        返回值：
            str | None：合法状态。

        异常：
            ValueError：非法状态。
        """
        if v is not None and v not in ADMIN_STATUSES:
            raise ValueError(f"status 必须为 {'/'.join(ADMIN_STATUSES)}")
        return v


# ---------------------------------------------------------------------------
# 菜谱
# ---------------------------------------------------------------------------
class RecipeIngredientIn(BaseModel):
    """菜谱食材行请求体（模型类）。

    属性：
        ingredient_id：食材 ID（FK）。
        amount_value：单值用量（可选；与 amount_min/max 至少其一）。
        amount_min / amount_max：范围用量（可选）。
        amount_unit：单位（克/毫升/个…，可选）。
        amount_note：用量备注（发布校验会检查"适量/少许/若干"模糊词）。
        amount_type：main/minor/seasoning。
        sort_order：排序序号（缺省按出现顺序）。
    """

    ingredient_id: int
    amount_value: float | None = None
    amount_min: float | None = None
    amount_max: float | None = None
    amount_unit: str | None = Field(default=None, max_length=10)
    amount_note: str | None = Field(default=None, max_length=50)
    amount_type: str = "main"
    sort_order: int = 0

    @field_validator("amount_type")
    @classmethod
    def _check_amount_type(cls, v: str) -> str:
        """校验用量类型枚举（内部函数）。

        参数：
            v：类型字符串。

        返回值：
            str：合法类型。

        异常：
            ValueError：非法类型。
        """
        if v not in AMOUNT_TYPES:
            raise ValueError(f"amount_type 必须为 {'/'.join(AMOUNT_TYPES)}")
        return v


class RecipeStepIn(BaseModel):
    """菜谱步骤行请求体（模型类）。

    属性：
        step_no：步骤序号（1 起，(recipe_id, step_no) 唯一）。
        description：步骤描述。
        duration_seconds：该步耗时秒（可选，供一键计时）。
        key_point：关键点（可选）。
        failure_tips：失败补救（可选）。
        amount_hint：用量提示（发布校验会检查模糊词）。
    """

    step_no: int = Field(ge=1)
    description: str = Field(min_length=1)
    duration_seconds: int | None = None
    key_point: str | None = Field(default=None, max_length=200)
    failure_tips: str | None = None
    amount_hint: str | None = Field(default=None, max_length=100)


class RecipeUpsertRequest(BaseModel):
    """菜谱创建/整卡更新请求体（模型类）。

    说明：
        PUT 语义为整卡替换：ingredients / steps 传入即整体重建（before/after 快照）。

    属性：
        title：菜名。
        cuisine：菜系（可选）。
        cooking_method：做法（可选）。
        difficulty：难度 1~5。
        time_minutes：耗时分钟（可选）。
        servings：份数（缺省 2）。
        calories_kcal：热量（可选）。
        tips：小贴士（可选）。
        ingredients：食材行（可选，PUT 缺省不重建）。
        steps：步骤行（可选，PUT 缺省不重建）。
    """

    title: str | None = Field(default=None, min_length=1, max_length=100)
    cuisine: str | None = Field(default=None, max_length=30)
    cooking_method: str | None = Field(default=None, max_length=20)
    difficulty: int = Field(default=2, ge=1, le=5)
    time_minutes: int | None = Field(default=None, ge=0)
    servings: int = Field(default=2, ge=1, le=50)
    calories_kcal: int | None = Field(default=None, ge=0)
    tips: str | None = None
    ingredients: list[RecipeIngredientIn] | None = None
    steps: list[RecipeStepIn] | None = None

    @field_validator("title")
    @classmethod
    def _check_title(cls, v: str | None) -> str | None:
        """POST 时菜名必填校验（内部函数，PUT 传 None 跳过）。

        参数：
            v：菜名或 None。

        返回值：
            str | None：菜名。

        异常：
            ValueError：空串。
        """
        if v is not None and not v.strip():
            raise ValueError("title 不能为空")
        return v


class RecipeRollbackRequest(BaseModel):
    """菜谱回滚请求体（模型类）。

    属性：
        log_id：目标操作日志 ID（取其 before_snapshot 恢复菜谱内容）。
    """

    log_id: int


class BatchImportRequest(BaseModel):
    """批量导入表单参数（模型类，multipart 直收时仅作参考）。

    说明：
        实际端点用 Form/File 直收 multipart（python-multipart），本模型仅
        文档化参数契约：format=json|csv|md。

    属性：
        format：导入格式。
    """

    format: str = "json"

    @field_validator("format")
    @classmethod
    def _check_format(cls, v: str) -> str:
        """校验导入格式枚举（内部函数）。

        参数：
            v：格式字符串。

        返回值：
            str：json/csv/md。

        异常：
            ValueError：非法格式。
        """
        if v not in ("json", "csv", "md"):
            raise ValueError("format 必须为 json/csv/md")
        return v


# ---------------------------------------------------------------------------
# 食材 / 营养
# ---------------------------------------------------------------------------
class IngredientCreate(BaseModel):
    """创建食材请求体（模型类）。

    属性：
        name：食材名。
        category：10 分类枚举。
        allergen_codes：GB 7718 致敏原 code 列表。
        verified：致敏原是否已核实（映射 allergen_verified）。
        unit_conversion：单位换算（可选 JSONB）。
    """

    name: str = Field(min_length=1, max_length=50)
    category: str
    allergen_codes: list[str] = Field(default_factory=list)
    verified: bool = False
    unit_conversion: dict | None = None

    @field_validator("category")
    @classmethod
    def _check_category(cls, v: str) -> str:
        """校验分类枚举（内部函数）。

        参数：
            v：分类字符串。

        返回值：
            str：合法分类。

        异常：
            ValueError：非法分类。
        """
        if v not in INGREDIENT_CATEGORIES:
            raise ValueError("category 不在 10 分类枚举内")
        return v


class IngredientUpdate(BaseModel):
    """更新食材请求体（模型类）：全字段可选。

    属性：
        name：食材名（可选）。
        category：分类（可选）。
        allergen_codes：致敏原（可选）。
        verified：核实标记（可选）。
        is_active：启用标记（可选）。
    """

    name: str | None = Field(default=None, min_length=1, max_length=50)
    category: str | None = None
    allergen_codes: list[str] | None = None
    verified: bool | None = None
    is_active: bool | None = None

    @field_validator("category")
    @classmethod
    def _check_category(cls, v: str | None) -> str | None:
        """校验分类枚举（内部函数）。

        参数：
            v：分类字符串或 None。

        返回值：
            str | None：合法分类。

        异常：
            ValueError：非法分类。
        """
        if v is not None and v not in INGREDIENT_CATEGORIES:
            raise ValueError("category 不在 10 分类枚举内")
        return v


class AliasCreate(BaseModel):
    """新增食材别名请求体（模型类）。

    属性：
        alias：别名文本。
    """

    alias: str = Field(min_length=1, max_length=50)


class NutritionUpsertRequest(BaseModel):
    """食材营养数据 upsert 请求体（模型类）。

    说明：
        data_source 必填（422 校验，数据溯源红线）；数值字段 None = 未纳入
        统计，不得按 0 计算（PRD §8.4）。

    属性：
        kcal_100g：每 100g 热量。
        protein_g / fat_g / carbs_g：三大营养素克数。
        sodium_mg：钠毫克。
        data_source：数据来源（必填）。
        source_license：来源许可（缺省 admin_manual）。
    """

    kcal_100g: float | None = None
    protein_g: float | None = None
    fat_g: float | None = None
    carbs_g: float | None = None
    sodium_mg: float | None = None
    data_source: str = Field(min_length=1, max_length=100)
    source_license: str = Field(default="admin_manual", max_length=50)


# ---------------------------------------------------------------------------
# 风控
# ---------------------------------------------------------------------------
class RiskRuleCreate(BaseModel):
    """创建风控规则请求体（模型类）。

    属性：
        rule_code：规则编码（唯一前缀，如 FS-9xx）。
        category：五类枚举。
        stage_scope：input/output/both。
        trigger_condition：触发条件 JSONB（keywords/groups/regex）。
        response_message_id：话术模板 ID（可选）。
        block：命中是否阻断（一票否决）。
        risk_level：critical/high/medium。
        evidence_ref：证据引用（可选）。
        version：版本号字符串。
        enabled：是否启用（缺省 True）。
    """

    rule_code: str = Field(min_length=1, max_length=30)
    category: str
    stage_scope: str
    trigger_condition: dict
    response_message_id: str | None = Field(default=None, max_length=40)
    block: bool = True
    risk_level: str
    evidence_ref: str | None = Field(default=None, max_length=200)
    version: str = Field(min_length=1, max_length=20)
    enabled: bool = True

    @field_validator("category")
    @classmethod
    def _check_category(cls, v: str) -> str:
        """校验规则类别枚举（内部函数）。

        参数：
            v：类别字符串。

        返回值：
            str：合法类别。

        异常：
            ValueError：非法类别。
        """
        if v not in RISK_CATEGORIES:
            raise ValueError("category 不在风控五类枚举内")
        return v

    @field_validator("stage_scope")
    @classmethod
    def _check_stage(cls, v: str) -> str:
        """校验阶段枚举（内部函数）。

        参数：
            v：阶段字符串。

        返回值：
            str：合法阶段。

        异常：
            ValueError：非法阶段。
        """
        if v not in RISK_STAGES:
            raise ValueError("stage_scope 必须为 input/output/both")
        return v

    @field_validator("risk_level")
    @classmethod
    def _check_level(cls, v: str) -> str:
        """校验风险等级枚举（内部函数）。

        参数：
            v：等级字符串。

        返回值：
            str：合法等级。

        异常：
            ValueError：非法等级。
        """
        if v not in RISK_LEVELS:
            raise ValueError("risk_level 必须为 critical/high/medium")
        return v


class RiskRuleUpdate(BaseModel):
    """更新风控规则请求体（模型类）：全字段可选。

    属性：
        trigger_condition：触发条件（可选）。
        block：阻断标记（可选）。
        risk_level：等级（可选）。
        response_message_id：话术 ID（可选）。
        evidence_ref：证据引用（可选）。
        enabled：启用标记（可选；热更新语义同 toggle）。
    """

    trigger_condition: dict | None = None
    block: bool | None = None
    risk_level: str | None = None
    response_message_id: str | None = Field(default=None, max_length=40)
    evidence_ref: str | None = Field(default=None, max_length=200)
    enabled: bool | None = None

    @field_validator("risk_level")
    @classmethod
    def _check_level(cls, v: str | None) -> str | None:
        """校验风险等级枚举（内部函数）。

        参数：
            v：等级字符串或 None。

        返回值：
            str | None：合法等级。

        异常：
            ValueError：非法等级。
        """
        if v is not None and v not in RISK_LEVELS:
            raise ValueError("risk_level 必须为 critical/high/medium")
        return v


class RiskRuleToggleRequest(BaseModel):
    """风控规则启停请求体（模型类）。

    属性：
        enabled：目标启用状态。
    """

    enabled: bool


class SensitiveWordItem(BaseModel):
    """自定义输出敏感词条目（模型类）。

    说明：
        存 remote_config 'output_sensitive_words'（JSONB 数组），sanitize 时
        优先消费本配置，空/缺省回退代码内置表。

    属性：
        word：违规词（构建正则时自动转义）。
        replacement：合规替换文本。
        category：禁令类别（缺省 custom）。
    """

    word: str = Field(min_length=1, max_length=50)
    replacement: str = Field(min_length=1, max_length=100)
    category: str = Field(default="custom", max_length=30)


class SensitiveWordsPut(BaseModel):
    """敏感词全量替换请求体（模型类）。

    属性：
        words：词条数组（全量覆盖）。
    """

    words: list[SensitiveWordItem]


class SensitiveWordAppend(BaseModel):
    """敏感词追加请求体（模型类）。

    属性：
        word：违规词。
        replacement：替换文本。
        category：类别（缺省 custom）。
    """

    word: str = Field(min_length=1, max_length=50)
    replacement: str = Field(min_length=1, max_length=100)
    category: str = Field(default="custom", max_length=30)


# ---------------------------------------------------------------------------
# 反馈 / 开关 / 订单
# ---------------------------------------------------------------------------
class FeedbackTransitionRequest(BaseModel):
    """反馈工单流转请求体（模型类）。

    属性：
        action：start（pending→processing）或 resolve（processing→resolved）。
    """

    action: str

    @field_validator("action")
    @classmethod
    def _check_action(cls, v: str) -> str:
        """校验流转动作枚举（内部函数）。

        参数：
            v：动作字符串。

        返回值：
            str：start/resolve。

        异常：
            ValueError：非法动作。
        """
        if v not in ("start", "resolve"):
            raise ValueError("action 必须为 start/resolve")
        return v


class SwitchesPutRequest(BaseModel):
    """远程开关全量更新请求体（模型类）。

    属性：
        switches：五模块开关字典（recommend/vision/qa/payment/innovation）。
    """

    switches: dict[str, bool] = Field(min_length=1, max_length=5)

    @field_validator("switches")
    @classmethod
    def _check_keys(cls, v: dict[str, bool]) -> dict[str, bool]:
        """校验开关键名枚举（内部函数）。

        参数：
            v：开关字典。

        返回值：
            dict[str, bool]：合法开关字典。

        异常：
            ValueError：含未知键。
        """
        allowed = {"recommend", "vision", "qa", "payment", "innovation"}
        unknown = set(v.keys()) - allowed
        if unknown:
            raise ValueError(f"非法开关键: {sorted(unknown)}")
        return v


class OrderCompensateRequest(BaseModel):
    """订单补发请求体（模型类）。

    属性：
        reason：补发原因（必填，落审计日志）。
        target_status：目标状态 paid/refunded（缺省 paid）。
    """

    reason: str = Field(min_length=1, max_length=200)
    target_status: str = "paid"

    @field_validator("target_status")
    @classmethod
    def _check_status(cls, v: str) -> str:
        """校验目标状态枚举（内部函数）。

        参数：
            v：状态字符串。

        返回值：
            str：paid/refunded。

        异常：
            ValueError：非法状态。
        """
        if v not in ("paid", "refunded"):
            raise ValueError("target_status 必须为 paid/refunded")
        return v


# ---------------------------------------------------------------------------
# 创新规则库
# ---------------------------------------------------------------------------
class PairingRuleCreate(BaseModel):
    """创建风味搭配规则请求体（模型类）。

    属性：
        ingredient_a_id / ingredient_b_id：食材 ID 对。
        relation：recommend/conflict/taboo。
        technique_suggestion：技法建议（可选）。
        rationale：搭配依据（烹饪学表述）。
        weight：权重 0~9.99（缺省 1.0）。
        signed_by_expert：专家签标（缺省 False）。
    """

    ingredient_a_id: int
    ingredient_b_id: int
    relation: str
    technique_suggestion: str | None = Field(default=None, max_length=128)
    rationale: str = Field(min_length=1, max_length=255)
    weight: float = Field(default=1.0, ge=0, le=9.99)
    signed_by_expert: bool = False

    @field_validator("relation")
    @classmethod
    def _check_relation(cls, v: str) -> str:
        """校验关系枚举（内部函数）。

        参数：
            v：关系字符串。

        返回值：
            str：合法关系。

        异常：
            ValueError：非法关系。
        """
        if v not in PAIRING_RELATIONS:
            raise ValueError("relation 必须为 recommend/conflict/taboo")
        return v


class PairingRuleUpdate(BaseModel):
    """更新风味搭配规则请求体（模型类）：全字段可选。

    属性：
        technique_suggestion：技法建议（可选）。
        rationale：搭配依据（可选）。
        weight：权重（可选）。
        signed_by_expert：专家签标（可选）。
    """

    technique_suggestion: str | None = Field(default=None, max_length=128)
    rationale: str | None = Field(default=None, min_length=1, max_length=255)
    weight: float | None = Field(default=None, ge=0, le=9.99)
    signed_by_expert: bool | None = None
