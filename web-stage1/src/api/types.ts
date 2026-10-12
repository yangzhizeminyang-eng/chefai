/**
 * 文件职责：后端 REST API 契约的 TypeScript 类型定义。
 * 严格对齐《spec.md》阶段一 REST API 清单与《02-架构设计与数据库设计文档》§9.2 推荐接口示例。
 * 所有类型字段均为后端响应/请求体的直译，前端不做二次加工。
 */

/** 食材实体（GET /v1/ingredients 列表项） */
export interface Ingredient {
  /** 食材唯一 ID */
  id: number
  /** 食材名称 */
  name: string
  /** 所属分类编码（如 veg / meat / seafood ...） */
  category: string
  /** 致敏原标注列表（可为空） */
  allergens?: string[]
  /** 别名列表（搜索命中用，可为空） */
  aliases?: string[]
}

/** 推荐请求体（POST /v1/recommend） */
export interface RecommendRequest {
  /** 幂等键：req_ + 时间戳 + 随机短串 */
  request_id: string
  /** 客户端类型标识 */
  client_type: 'web_stage1'
  /** 已选食材（ID + 数量档位） */
  ingredients: Array<{ ingredient_id: number; quantity_level?: 'few' | 'enough' | 'plenty' }>
  /** 附加选项（如是否展示被过滤项） */
  options?: { show_filtered?: boolean }
}

/** 推荐结果单条菜谱（对齐架构文档 §9.2） */
export interface RecommendResultItem {
  /** 菜谱 ID */
  recipe_id: number
  /** 菜名 */
  title: string
  /** 三档匹配等级：现在就能做 / 差1–2样 / 需要多买几样 */
  match_level: 'can_cook_now' | 'missing_1_2' | 'need_more'
  /** 已覆盖（用户现有）食材名列表 */
  covered_ingredients: string[]
  /** 缺失食材名列表 */
  missing_ingredients: string[]
  /** 总耗时（分钟） */
  time_minutes: number
  /** 难度：easy / medium / hard */
  difficulty: 'easy' | 'medium' | 'hard'
  /** 每份估算热量（kcal） */
  calories_kcal: number | null
  /** 菜谱含有的致敏原列表 */
  allergens: string[]
  /** 所需厨房设备 */
  required_equipment: string[]
  /** 7 因子加权排序得分 */
  rank_score: number
  /** 排序理由（至少 1 条） */
  rank_reasons: string[]
  /** 菜谱来源标注 */
  source: string
}

/** 过滤计数（被布尔硬过滤剔除的菜谱统计） */
export interface FilteredBy {
  /** 因过敏原被过滤的数量 */
  allergen?: number
  /** 因忌口被过滤的数量 */
  dietary_restriction?: number
  /** 因难度被过滤的数量 */
  difficulty?: number
  /** 因缺少设备被过滤的数量（M2/P6/S8：设备维度硬过滤计数，档案设备非空时生效） */
  equipment?: number
}

/** 推荐正常响应体（POST /v1/recommend，非短路场景） */
export interface RecommendResponse {
  /** 幂等键回显 */
  request_id: string
  /** 是否处于保守模式（风控异常降级） */
  safe_mode: boolean
  /** 三档推荐结果 */
  results: RecommendResultItem[]
  /** 布尔硬过滤计数 */
  filtered_by: FilteredBy
  /** 附着的免责声明 ID */
  disclaimer_id: string
  /** Agent 调度 trace ID */
  trace_id: string
  /** 并行营养估算结果（可选） */
  nutrition?: NutritionResult
  /** 部分 Agent 失败说明（可选，非空时页面顶部展示说明条） */
  partial_failures?: string[]
  /** 附加提示文案（可选） */
  notice?: string
}

/** 风险详情（一票否决短路返回体中的 risk 对象） */
export interface RiskDetail {
  /** 风险类别（如 food_safety_high_risk / medical_refusal / pseudoscience） */
  category: string
  /** 命中的规则编码（如 FS-018） */
  rule_code: string
  /** 风险等级：high / medium / low */
  risk_level: 'high' | 'medium' | 'low'
  /** 话术模板 ID（risk_message 表） */
  message_id: string
  /** 风险说明标题 */
  title: string
  /** 风险说明正文 */
  body: string
  /** 正确做法 */
  correct_action: string
  /** 已食用处置建议（就医引导） */
  after_consumption_advice: string
  /** 依据来源引用（如 FS-018@rules-v1.2） */
  evidence_ref: string[]
}

/** 一票否决短路响应体（不含 results/candidates/nutrition 任何字段） */
export interface BlockedResponse {
  /** 幂等键回显 */
  request_id: string
  /** 是否被阻断（恒为 true） */
  blocked: boolean
  /** 是否一票否决（覆盖所有业务输出） */
  overrides_all: boolean
  /** 风险详情 */
  risk: RiskDetail
  /** 附着的免责声明 ID */
  disclaimer_id: string
  /** Agent 调度 trace ID */
  trace_id: string
}

/** 菜谱食材行（含量化值与勺参照） */
export interface RecipeIngredientItem {
  /** 食材名 */
  name: string
  /** 量化值描述（如「200g」「2 勺」；区间用「100~150g」） */
  amount: string
  /** 是否主料 */
  is_main?: boolean
  /** 该食材的致敏原标注（可为空） */
  allergens?: string[]
  /** 替代说明（该食材缺失时的替代建议，可选） */
  substitute?: string
}

/** 菜谱步骤 */
export interface RecipeStep {
  /** 步骤序号（从 1 开始） */
  no: number
  /** 步骤描述 */
  description: string
  /** 预计耗时（秒，0 表示无需等待） */
  duration_sec: number
  /** 新手动作要点 */
  tips?: string
  /** 失败补救建议 */
  rescue?: string
  /** 本步用量提示（如「盐 2g（约半勺）」） */
  amount_hint?: string
}

/** 菜谱详情（GET /v1/recipes/{id}，支持 servings 缩放重算） */
export interface RecipeDetail {
  /** 菜谱 ID */
  id: number
  /** 菜名 */
  title: string
  /** 菜谱简介（可选） */
  description?: string
  /** 难度 */
  difficulty: 'easy' | 'medium' | 'hard'
  /** 总耗时（分钟） */
  time_minutes: number
  /** 当前份数（默认基準，随 servings 参数缩放） */
  servings: number
  /** 每份估算热量（kcal，可能为 null 表示未纳入统计） */
  calories_kcal: number | null
  /** 菜谱聚合致敏原列表 */
  allergen_codes: string[]
  /** 所需厨房设备 */
  equipment: string[]
  /** 主料清单 */
  main_ingredients: RecipeIngredientItem[]
  /** 辅料清单 */
  side_ingredients: RecipeIngredientItem[]
  /** 调味料清单（用量必量化，不出现「适量/少许」） */
  seasoning_ingredients: RecipeIngredientItem[]
  /** 步骤列表 */
  steps: RecipeStep[]
  /** 替代食材建议 */
  substitutes: string[]
  /** 小贴士 */
  tips: string[]
  /** 来源标注（如 HowToCook / 公开家常菜语料） */
  source_label: string
}

/** 菜谱搜索结果条目（GET /v1/recipes?q= 列表项） */
export interface RecipeSearchItem {
  /** 菜谱 ID */
  id: number
  /** 菜名 */
  title: string
  /** 难度三档文案（easy / medium / hard） */
  difficulty: 'easy' | 'medium' | 'hard'
  /** 总耗时（分钟，可 null 表示未标注） */
  time_minutes: number | null
  /** 热量（kcal，可 null 表示未纳入统计） */
  calories_kcal: number | null
}

/** 菜谱搜索响应体（GET /v1/recipes） */
export interface RecipeSearchResponse {
  /** 当前页菜谱条目 */
  items: RecipeSearchItem[]
  /** 总命中数 */
  total: number
  /** 当前页码 */
  page: number
  /** 每页条数 */
  page_size: number
}

/** 营养估算结果（GET /v1/recipes/{id}/nutrition） */
export interface NutritionResult {
  /** 每份热量（kcal，唯一口径；DB calories_kcal 优先，缺失时回退估算） */
  kcal: number | null
  /** 蛋白质（g/份） */
  protein: number | null
  /** 脂肪（g/份） */
  fat: number | null
  /** 碳水化合物（g/份） */
  carbs: number | null
  /** 钠（mg/份） */
  sodium: number | null
  /** 当前计算份数 */
  per_serving: number
  /** 按当前份数合计（= 每份 × 份数，同源换算；与 kcal 口径一致，可为空） */
  total?: {
    /** 合计热量（kcal） */
    kcal: number | null
    /** 合计蛋白质（g） */
    protein: number | null
    /** 合计脂肪（g） */
    fat: number | null
    /** 合计碳水（g） */
    carbs: number | null
    /** 合计钠（mg） */
    sodium: number | null
  }
  /** 每份 kcal 数据来源（recipe_seed 菜谱库值 / llm_estimate LLM 回退 / deterministic_fallback 食材聚合；旧后端无该字段） */
  kcal_source?: string | null
  /** 未纳入统计的食材名列表（缺失营养数据，不按 0 计） */
  excluded_items: string[]
  /** 估算说明（固定含「估算值，非实测值，误差约 ±15%」） */
  estimate_note: string
}

/** 烹饪会话（POST/PATCH /v1/cooking/sessions） */
export interface CookingSession {
  /** 会话 ID */
  id: string
  /** 关联菜谱 ID */
  recipe_id: number
  /** 份数 */
  servings: number
  /** 当前步骤序号（从 1 开始） */
  current_step_no: number
  /** 会话状态（in_progress / finished 等） */
  status: 'in_progress' | 'finished'
  /** 过敏原冲突说明（创建时检查，无冲突为空） */
  allergen_conflict: string[]
}

/** Agent 调度单个节点 span（GET /v1/trace/{request_id}） */
export interface TraceSpan {
  /** 节点名（如 intake_guard / supervisor / recipe_rank ...） */
  node_name: string
  /** 节点状态：not_executed / running / ok / degraded / failed / timeout / skipped_by_veto */
  status: 'not_executed' | 'running' | 'ok' | 'degraded' | 'failed' | 'timeout' | 'skipped_by_veto'
  /** 耗时（毫秒） */
  duration_ms: number
  /** 调用的模型名（纯规则节点为空） */
  model_name: string | null
  /** prompt token 数 */
  prompt_tokens: number
  /** completion token 数 */
  completion_tokens: number
  /** 成本（分） */
  cost_cents: number
  /** 命中的风控规则编码（未命中为空） */
  rule_hit: string
}

/** 风控判定摘要 */
export interface TraceRisk {
  /** 是否命中 */
  hit: boolean
  /** 风险类别 */
  category?: string
  /** 命中的规则 ID */
  rule_id?: string
  /** 话术模板 ID */
  message_id?: string
}

/** 是否一票否决 */
export interface TraceVeto {
  /** 是否触发一票否决 */
  veto: boolean
  /** 触发原因说明 */
  reason?: string
}

/** trace 详情（GET /v1/trace/{request_id}） */
export interface TraceDetail {
  /** 幂等键 */
  request_id: string
  /** 一票否决判定 */
  veto: TraceVeto
  /** 风控判定 */
  risk: TraceRisk
  /** 节点执行列表 */
  nodes: TraceSpan[]
  /** 汇总（token 与成本） */
  totals: {
    prompt_tokens: number
    completion_tokens: number
    cost_cents: number
  }
}

/** trace 列表项（GET /v1/trace） */
export interface TraceListItem {
  /** 幂等键 */
  request_id: string
  /** 创建时间（ISO 8601） */
  created_at: string
  /** 是否一票否决 */
  veto: boolean
  /** 风控判定摘要 */
  risk: TraceRisk
}

/** 远程开关（GET /v1/config/switches，4 模块） */
export interface Switches {
  /** 推荐模块开关 */
  recommend: boolean
  /** 识别模块开关（阶段一预留） */
  vision: boolean
  /** 问答模块开关 */
  qa: boolean
  /** 支付模块开关（阶段一预留） */
  payment: boolean
  /** AI 创新模块开关（阶段二新增，后端未返回时前端按 undefined → 默认放开） */
  innovation?: boolean
}

/** 匿名会话响应（POST /v1/auth/anonymous） */
export interface AnonymousResponse {
  /** 匿名用户 ID */
  anonymous_id: string
}

/** 免责同意响应（POST /v1/consent/disclaimer） */
export interface ConsentResponse {
  /** 是否记录成功 */
  ok: boolean
}

/** 自然语言提问响应（POST /v1/ask） */
export interface AskResponse {
  /** 幂等键回显 */
  request_id: string
  /** 识别的意图：recommend（跳推荐）/ recipe_search（菜名搜索）/ free_qa（受限问答）/ blocked（命中阻断） */
  intent: 'recommend' | 'recipe_search' | 'free_qa' | 'blocked'
  /** 受限问答的回答文本（free_qa 时） */
  answer?: string
  /** 命中菜谱 ID 列表（recipe_search 时） */
  recipe_ids?: number[]
  /** 一票否决短路返回体（blocked 时，体结构同 BlockedResponse） */
  blocked?: BlockedResponse
  /** trace ID */
  trace_id: string
  /** 附着的免责声明 ID */
  disclaimer_id: string
}

/** 统一错误对象（axios 拦截器归一化后抛出） */
export interface ApiError {
  /** 错误码（HTTP 状态码或后端业务码） */
  code: number | string
  /** 面向用户的错误文案 */
  message: string
  /** 后端返回的原始 detail（422 校验错误时为 str(exc.errors()) repr 串或原生错误数组，可选） */
  detail?: unknown
}

/** 单条过滤原因（POST /v1/recommend/filtered 响应 reasons 元素直译：{type, detail}） */
export interface FilteredReason {
  /**
   * 原因类型码：allergen 致敏原 / taboo 忌口 / difficulty 难度超限 / equipment 缺少设备
   */
  type: string
  /** 中文明细说明（后端直出文案，如「命中过敏原：花生」「缺少设备：燃气灶」） */
  detail: string
}

/**
 * 被过滤菜谱条目（POST /v1/recommend/filtered 响应 filtered 元素）。
 * 后端字段名为 recipe_name，前端映射为 title（与推荐结果条目字段名对齐）。
 */
export interface FilteredRecipeItem {
  /** 菜谱 ID */
  recipe_id: number
  /** 菜名（后端 recipe_name 映射） */
  title: string
  /** 全部过滤原因列表（{type, detail} 结构，后端直译） */
  filter_reasons: FilteredReason[]
}

/** 布尔硬过滤重放请求体（POST /v1/recommend/filtered，口径对齐主推荐实际生效的过滤条件） */
export interface FilteredRecommendRequestBody {
  /** 已选食材列表（形态同 POST /v1/recommend 的 ingredients） */
  ingredients: RecommendRequest['ingredients']
  /** 过敏原 code 集合（家庭成员并集，来自家庭档案；缺省空） */
  allergen_codes?: string[]
  /** 忌口标记集合（家庭成员并集，来自家庭档案；缺省空） */
  dietary_restrictions?: string[]
  /** 难度上限 1~5（可选；主推荐管线未启用难度上限时不传） */
  difficulty_cap?: number
  /** 用户已有设备清单（来自厨艺与设备档案；缺省空 = 不启用设备过滤） */
  equipment?: string[]
}

/** 布尔硬过滤重放响应单个条目（后端直译：recipe_name / reason / reasons 结构） */
export interface FilteredRecommendItemRaw {
  /** 菜谱 ID */
  recipe_id: number
  /** 菜名（后端字段名，前端映射为 FilteredRecipeItem.title） */
  recipe_name: string
  /** 主过滤原因类型码（兼容保留；多原因并存时按优先级取首项） */
  reason: string
  /** 全部过滤原因列表（{type, detail} 结构） */
  reasons: FilteredReason[]
}

/** 布尔硬过滤重放响应体（POST /v1/recommend/filtered） */
export interface FilteredRecommendResponse {
  /** 被过滤菜谱列表（后端直译结构） */
  filtered: FilteredRecommendItemRaw[]
  /** 被过滤菜谱总数 */
  total_filtered: number
}

/* ═══════════════════════════════════════════════════════════════════
 * 以下为 Task 9（阶段二前端）新增契约类型：
 * 首页聚合 / 家庭档案 / 库存与购物清单 / 营养汇总 / 收藏历史拿手菜 /
 * 设置与数据权利 / 会员 / 反馈 / AI 创新 / 图像识别 / 烹饪求助。
 * 字段以后端接口契约为准，前端不做二次加工。
 * ═══════════════════════════════════════════════════════════════════ */

/* ── 首页聚合（GET /v1/home）── */

/** 临期食材条目（首页临期提醒数据源） */
export interface ExpiringIngredient {
  /** 库存条目 ID */
  id: number
  /** 食材名 */
  ingredient_name: string
  /** 到期日（YYYY-MM-DD） */
  expire_date: string
  /** 剩余天数（负数表示已过期） */
  days_left: number
  /** 该食材的致敏原编码列表 */
  allergen_codes: string[]
}

/** 未完成烹饪会话摘要（首页「继续上次的菜」卡片数据源） */
export interface UnfinishedSession {
  /** 会话 ID */
  session_id: string
  /** 菜谱 ID */
  recipe_id: number
  /** 菜名 */
  recipe_name: string
  /** 当前进度：当前步骤序号 */
  current_step: number
  /** 当前进度：总步骤数 */
  total_steps: number
}

/** 首页聚合响应体 */
export interface HomeResponse {
  /** 五大入口可用性（false → 前端置灰） */
  entries: {
    /** 今天吃什么（手选食材） */
    cooking: boolean
    /** 拍一下冰箱（图像识别） */
    vision: boolean
    /** 时令推荐 */
    seasonal: boolean
    /** 饮食目标（档案） */
    goal: boolean
    /** 我的冰箱（库存） */
    fridge: boolean
    /** AI 创新 */
    innovation: boolean
  }
  /** 未完成会话（null = 无进行中会话） */
  unfinished_session: UnfinishedSession | null
  /** 临期食材列表（首页提醒条） */
  expiring: ExpiringIngredient[]
  /** 档案提示（是否已建档 + 成员数） */
  profile_hint: { has_profile: boolean; member_count: number }
  /** 当前时令分类编码列表（如 ['veg','seafood']） */
  seasonal_categories: string[]
}

/* ── 家庭档案（/v1/profile/*）── */

/** 家庭成员条目 */
export interface FamilyMember {
  /** 成员 ID（新增成功后由后端生成） */
  id: number
  /** 成员姓名 */
  name: string
  /** 与本人关系（如 本人/配偶/孩子） */
  relation: string
  /** GB 7718 八类致敏原编码列表 */
  allergen_codes: string[]
  /** 自定义过敏原文本列表（八类之外的） */
  custom_allergens: string[]
  /** 是否勾选「暂无已知过敏原」 */
  no_known_allergen: boolean
  /** 口味-辣度偏好（0 清淡 / 1 适中 / 2 嗜辣） */
  taste_spicy: number
  /** 口味-咸淡偏好（0~2） */
  taste_salt: number
  /** 口味-甜度偏好（0~2） */
  taste_sweet: number
  /** 忌口列表（如 香菜/内脏） */
  dietary_restrictions: string[]
  /** 特殊饮食（6 类，如 素食/低 GI） */
  special_diet: string[]
  /** 特殊人群（5 类，如 孕期/哺乳期/婴幼儿辅食） */
  special_population: string[]
}

/** 家庭档案（GET/PUT /v1/profile/family） */
export interface FamilyProfile {
  /** 家庭 ID */
  family_id: number
  /** 家庭名称 */
  name: string
  /** 成员列表 */
  members: FamilyMember[]
}

/** 厨艺与设备档案（GET/PUT /v1/profile/skill） */
export interface SkillProfile {
  /** 厨艺水平 1~5（1 新手 / 5 大厨） */
  cooking_level: number
  /** 已有厨房设备（13 项编码列表，如 ['炒锅','电饭煲']） */
  equipment: string[]
}

/** 饮食目标（GET/PUT /v1/profile/diet-goal） */
export interface DietGoal {
  /** 目标 5 类 */
  goal: 'control_weight' | 'muscle_gain' | 'light_salt' | 'low_sugar' | 'balanced'
  /** 备注说明 */
  note: string
}

/** 敏感操作 PIPL 单独同意响应（POST /v1/consent/sensitive） */
export interface ConsentSensitiveResponse {
  /** 同意记录 ID */
  consent_id: string
}

/* ── 库存与购物清单（/v1/inventory、/v1/shopping-list）── */

/**
 * 存放位置枚举（对齐后端 StorageLocation 四值，见 backend/app/schemas/inventory.py；
 * DB 列 storage 受 chk_storage 约束，仅接受这四个枚举值，传中文标签会 422）。
 */
export type StorageLocation = 'fridge' | 'freezer' | 'room' | 'dry'

/** 库存条目 */
export interface InventoryItem {
  /** 库存条目 ID */
  id: number
  /** 食材 ID */
  ingredient_id: number
  /** 食材名 */
  ingredient_name: string
  /** 数量档位：low 少量 / mid 有 / plenty 充足 */
  quantity_level: 'low' | 'mid' | 'plenty'
  /** 入库时间（ISO 8601） */
  stocked_at: string
  /** 到期日（YYYY-MM-DD） */
  expire_date: string
  /** 存放位置（fridge 冷藏 / freezer 冷冻 / room 常温 / dry 阴凉干燥） */
  location: StorageLocation
  /** 该食材的致敏原编码列表 */
  allergen_codes: string[]
  /** 条目状态：active 在库 / used 已用完 / expired 已过期 / discarded 已丢弃 */
  status: 'active' | 'used' | 'expired' | 'discarded'
}

/** 库存列表响应体 */
export interface InventoryListResponse {
  /** 库存条目数组 */
  items: InventoryItem[]
}

/** 新增库存请求体（POST /v1/inventory） */
export interface InventoryCreateBody {
  /** 食材 ID */
  ingredient_id: number
  /** 数量档位 */
  quantity_level: InventoryItem['quantity_level']
  /** 到期日（可选） */
  expire_date?: string
  /** 存放位置（可选，必须为 StorageLocation 四值枚举之一，传中文标签会 422） */
  location?: StorageLocation
}

/** 修改库存请求体（PATCH /v1/inventory/{id}，增量字段） */
export interface InventoryPatchBody {
  /** 数量档位（可选） */
  quantity_level?: InventoryItem['quantity_level']
  /** 存放位置（可选，必须为 StorageLocation 四值枚举之一，传中文标签会 422） */
  location?: StorageLocation
  /** 到期日（可选） */
  expire_date?: string
  /** 条目状态（可选，如标记用完/丢弃） */
  status?: InventoryItem['status']
}

/** 扣减建议单条（POST /v1/inventory/deduct-suggest 列表项） */
export interface DeductSuggestion {
  /** 建议关联的库存条目 ID */
  item_id: number
  /** 食材 ID */
  ingredient_id: number
  /** 食材名 */
  ingredient_name: string
  /** 建议动作：deduce 扣减数量 / mark_used 标记用完 */
  suggest_action: 'deduce' | 'mark_used'
  /** 建议理由说明 */
  reason: string
}

/** 扣减建议响应体 */
export interface DeductSuggestResponse {
  /** 建议列表（可能为空 = 无需扣减） */
  suggestions: DeductSuggestion[]
}

/** 扣减确认请求体（POST /v1/inventory/deduct-confirm） */
export interface DeductConfirmBody {
  /** 本次烹饪会话 ID */
  session_id: string
  /** 用户勾选确认的条目列表 */
  confirmations: Array<{ item_id: number; action: DeductSuggestion['suggest_action'] }>
}

/** 购物清单条目 */
export interface ShoppingItem {
  /** 条目 ID */
  id: number
  /** 食材名 */
  ingredient_name: string
  /** 数量备注（如 「2 根」「500g」） */
  quantity_note: string
  /** 来源菜谱名（可选） */
  from_recipe_name?: string
  /** 是否已勾选（已购） */
  checked: boolean
  /** 该食材的致敏原编码列表 */
  allergen_codes: string[]
}

/** 购物清单响应体 */
export interface ShoppingListResponse {
  /** 条目数组 */
  items: ShoppingItem[]
}

/** 购物清单新增请求体（POST /v1/shopping-list，后端按食材合并去重） */
export interface ShoppingCreateBody {
  /** 新增条目列表 */
  items: Array<{
    /** 食材 ID */
    ingredient_id: number
    /** 数量备注 */
    quantity_note: string
    /** 来源菜谱名（可选） */
    from_recipe_name?: string
  }>
}

/* ── 营养汇总（/v1/nutrition/*）── */

/** 单日单餐营养数据（缺失项为 null，不按 0 计） */
export interface NutritionDayMeal {
  /** 热量（kcal） */
  kcal: number | null
  /** 蛋白质（g） */
  protein: number | null
  /** 脂肪（g） */
  fat: number | null
  /** 碳水（g） */
  carb: number | null
  /** 钠（mg） */
  sodium: number | null
  /** 未纳入统计的食材名列表 */
  excluded: string[]
}

/** 单日营养数据 */
export interface NutritionDay {
  /** 日期（YYYY-MM-DD） */
  date: string
  /** 四餐数据 */
  meals: {
    /** 早餐 */
    breakfast: NutritionDayMeal
    /** 午餐 */
    lunch: NutritionDayMeal
    /** 晚餐 */
    dinner: NutritionDayMeal
    /** 加餐/零食 */
    snack: NutritionDayMeal
  }
}

/** 营养汇总响应体（GET /v1/nutrition/summary?days=7） */
export interface NutritionSummaryResponse {
  /** 逐日数据（按日期正序） */
  days: NutritionDay[]
  /** 周期合计 */
  totals: {
    /** 合计热量（kcal） */
    kcal: number | null
    /** 合计蛋白质（g） */
    protein: number | null
    /** 合计脂肪（g） */
    fat: number | null
    /** 合计碳水（g） */
    carb: number | null
    /** 合计钠（mg） */
    sodium: number | null
  }
  /** 全周期未纳入统计食材列表 */
  excluded: string[]
  /** 免责声明文案（估算值） */
  disclaimer: string
}

/** 手动补录外食请求体（POST /v1/nutrition/manual，走风控） */
export interface NutritionManualBody {
  /** 餐次 */
  meal_type: 'breakfast' | 'lunch' | 'dinner' | 'snack'
  /** 外食描述（自然语言） */
  description: string
}

/** 手动补录响应体：正常 {ok:true}；命中风控拦截返回 blocked 结构 */
export interface NutritionManualResponse {
  /** 是否记录成功 */
  ok?: boolean
  /** 是否被风控拦截 */
  blocked?: boolean
  /** 拦截话术标题（blocked 时） */
  title?: string
  /** 拦截话术正文（blocked 时） */
  message?: string
}

/* ── 收藏 / 历史 / 拿手菜 / 设置 ── */

/** 收藏条目 */
export interface FavoriteItem {
  /** 菜谱 ID */
  recipe_id: number
  /** 菜名 */
  recipe_name: string
  /** 分组名（如 常做的/想吃） */
  group_name: string
  /** 封面 emoji（可选） */
  cover_emoji?: string
  /** 菜谱致敏原编码列表 */
  allergen_codes: string[]
}

/** 收藏列表响应体（GET /v1/favorites?group=） */
export interface FavoritesResponse {
  /** 全部分组名列表 */
  groups: string[]
  /** 收藏条目数组 */
  items: FavoriteItem[]
}

/** 烹饪历史条目 */
export interface HistoryItem {
  /** 会话 ID */
  session_id: string
  /** 菜谱 ID */
  recipe_id: number
  /** 菜名 */
  recipe_name: string
  /** 完成时间（ISO 8601） */
  finished_at: string
  /** 用户评分 1~5（可选） */
  rating?: number | null
  /** 本次烹饪耗时分钟数（完成-创建向上取整；无完成时间的旧数据为 null） */
  duration_minutes?: number | null
}

/** 烹饪历史响应体 */
export interface HistoryResponse {
  /** 历史条目数组（后端按完成时间倒序） */
  items: HistoryItem[]
}

/** 拿手菜条目 */
export interface SignatureDish {
  /** 菜谱 ID */
  recipe_id: number
  /** 菜名 */
  recipe_name: string
  /** 累计烹饪次数 */
  cook_count: number
  /** 平均评分（1~5，无评分记录时 null） */
  avg_rating: number | null
}

/** 拿手菜响应体 */
export interface SignatureDishesResponse {
  /** 拿手菜数组（按 cook_count 倒序） */
  items: SignatureDish[]
}

/** 用户设置（GET/PUT /v1/settings） */
export interface SettingsData {
  /** 字号档位：normal 标准 / large 大 / xlarge 特大 */
  font_size: 'normal' | 'large' | 'xlarge'
  /** 计量单位三选（PRD §5.4）：gram 克 / milliliter 毫升 / spoon 勺（历史值 metric/imperial 由 store 读时迁移） */
  unit: 'gram' | 'milliliter' | 'spoon'
  /** 语音播报开关 */
  voice_enabled: boolean
  /** 做菜提醒开关 */
  reminder_enabled: boolean
}

/* ── 数据权利（/v1/me/*）── */

/** 个人数据导出（GET /v1/me/export，JSON 下载） */
export interface MeExportData {
  /** 导出时间（ISO 8601） */
  exported_at?: string
  /** 导出的数据分片（后端聚合的各域数据，前端不做结构假设） */
  [key: string]: unknown
}

/* ── 会员（/v1/member/*）── */

/** 会员套餐 */
export interface MemberPlan {
  /** 套餐类型 */
  product_type: 'monthly' | 'quarterly' | 'yearly'
  /** 套餐名（如 月卡） */
  name: string
  /** 价格（分） */
  price_cents: number
  /** 权益说明列表 */
  benefits: string[]
  /** 是否仅预览（preview_only=true 时不可购买） */
  preview_only: boolean
}

/** 套餐列表响应体 */
export interface MemberPlanResponse {
  /** 套餐数组 */
  plans: MemberPlan[]
  /** 支付渠道标识（web 端固定 miniprogram_virtual 说明文案） */
  pay_channel: string
  /** 支付总开关（false → 购买按钮禁用） */
  payment_switch_on: boolean
}

/** 当前会员状态响应体（GET /v1/member/me） */
export interface MemberMeResponse {
  /** 是否有效会员 */
  is_member: boolean
  /** 到期时间（ISO 8601，非会员为 null） */
  expire_at?: string | null
  /** 本周期识别额度 */
  quota: { used: number; limit: number }
}

/** 创建订单响应体（POST /v1/member/orders） */
export interface MemberOrderCreateResponse {
  /** 订单号 */
  order_no: string
  /** 应付金额（分） */
  amount_cents: number
  /** 订单状态（创建后为 pending） */
  status: 'pending'
}

/** 模拟支付响应体（POST /v1/member/orders/{order_no}/mock-pay） */
export interface MemberMockPayResponse {
  /** 支付后状态 */
  status: 'paid'
  /** 支付时间（ISO 8601） */
  paid_at: string
}

/** 订单列表条目 */
export interface MemberOrderItem {
  /** 订单号 */
  order_no: string
  /** 套餐类型 */
  product_type: MemberPlan['product_type']
  /** 金额（分） */
  amount_cents: number
  /** 订单状态 */
  status: 'pending' | 'paid'
  /** 支付时间（未支付为 null） */
  paid_at?: string | null
  /** 创建时间（ISO 8601） */
  created_at: string
}

/** 订单列表响应体 */
export interface MemberOrdersResponse {
  /** 订单数组 */
  items: MemberOrderItem[]
}

/* ── 反馈（/v1/feedback）── */

/** 提交反馈响应体 */
export interface FeedbackCreateResponse {
  /** 反馈 ID */
  feedback_id: number
  /** 回执编号 */
  receipt_no: string
  /** 承诺回复时限（小时，固定 24） */
  expected_reply_within_hours: number
}

/** 反馈详情响应体（GET /v1/feedback/{id}） */
export interface FeedbackDetailResponse {
  /** 处理状态（如 pending/processing/resolved） */
  status: string
  /** 回执编号 */
  receipt_no: string
  /** 提交时间（ISO 8601） */
  created_at: string
}

/* ── AI 创新（/v1/innovation/*）── */

/** 创新预检响应体（POST /v1/innovation/precheck） */
export interface InnovationPrecheckResponse {
  /** 预检是否通过 */
  ok: boolean
  /** 是否被风控拦截 */
  blocked: boolean
  /** 命中的规则 ID（未命中为空） */
  rule_id?: string
  /** 拦截话术（blocked 时非空） */
  message?: string
}

/** 创新菜谱食材行（含量化） */
export interface InnovationIngredient {
  /** 食材名 */
  name: string
  /** 量化值（如 200） */
  amount: string
  /** 单位（如 g / 勺） */
  unit: string
}

/** 创新菜谱步骤 */
export interface InnovationStep {
  /** 步骤序号 */
  no: number
  /** 步骤描述 */
  description: string
  /** 预计耗时（秒） */
  duration_sec: number
  /** 小贴士（可选） */
  tips?: string
}

/** 创新依据-搭配规则引用 */
export interface InnovationPairing {
  /** 食材 A */
  a: string
  /** 食材 B */
  b: string
  /** 搭配关系（如 去腥增鲜） */
  relation: string
  /** 依据说明 */
  rationale: string
}

/** 创新依据-食性标注 */
export interface InnovationProperty {
  /** 性质名（如 性温） */
  name: string
  /** 说明 */
  note: string
}

/** 创新菜谱实体（generate 返回体 / reuse 返回体结构） */
export interface InnovationRecipe {
  /** 创新菜谱 ID */
  id: number
  /** 菜名 */
  name: string
  /** 用量清单（量化） */
  ingredients: InnovationIngredient[]
  /** 步骤列表 */
  steps: InnovationStep[]
  /** 创新依据 */
  basis: {
    /** 搭配规则引用列表 */
    pairings: InnovationPairing[]
    /** 食性标注列表 */
    properties: InnovationProperty[]
    /** 生成来源（P1 DEF-01）：llm = LLM 表达成功 / template = LLM 超时或失败降级规则模板 */
    generated_by?: 'llm' | 'template'
  }
  /** 营养估算（缺失项为 null，excluded 列出未纳入食材） */
  nutrition: {
    /** 热量（kcal） */
    kcal: number | null
    /** 蛋白质（g） */
    protein: number | null
    /** 脂肪（g） */
    fat: number | null
    /** 碳水（g） */
    carb: number | null
    /** 未纳入统计食材名列表 */
    excluded: string[]
  }
  /** 状态（generated = 已生成） */
  status: 'generated'
  /** 是否 AI 创新（恒为 true） */
  is_ai_innovated: boolean
  /** 强制声明文案 */
  disclaimer: string
}

/** 复用响应体（POST /v1/innovation/recipes/{id}/reuse） */
export interface InnovationReuseResponse {
  /** 是否可复用 */
  ok: boolean
  /** 创新菜谱实体 */
  recipe: InnovationRecipe
}

/** 采纳响应体（POST /v1/innovation/recipes/{id}/adopt） */
export interface InnovationAdoptResponse {
  /** 是否采纳成功 */
  ok?: boolean
}

/** 创新菜评分请求体（POST /v1/innovation/recipes/{id}/feedback） */
export interface InnovationFeedbackBody {
  /** 评分 1~5 */
  rating: number
  /** 文字评价（可选） */
  comment?: string
}

/* ── 图像识别（/v1/vision/*）── */

/** 识别响应体（POST /v1/vision/recognize，multipart file） */
export interface VisionRecognizeResponse {
  /** 识别结果列表 */
  recognized: Array<{
    /** 食材名 */
    name: string
    /** 置信度：high 直接勾选 / low 需人工确认 */
    confidence: 'high' | 'low'
    /** 命中的食材库 ID（未收录为 null） */
    ingredient_id?: number | null
  }>
  /** 本周期识别额度 */
  quota: { used: number; limit: number }
  /** 是否降级（true → 顶部展示降级提示条） */
  degraded: boolean
}

/** 识别确认入库响应体（POST /v1/vision/confirm） */
export interface VisionConfirmResponse {
  /** 成功加入的食材数 */
  added: number
}

/* ── 烹饪求助（POST /v1/cooking/sessions/{id}/help）── */

/** 烹饪求助响应体（正常路径） */
export interface CookingHelpResponse {
  /** 回答列表 */
  answers: string[]
}

/** 烹饪求助拦截响应体（命中风控时返回的 blocked 结构） */
export interface CookingHelpBlockedResponse {
  /** 是否被拦截（恒为 true） */
  blocked: boolean
  /** 拦截话术标题 */
  title?: string
  /** 拦截话术正文 */
  message?: string
}

/** 烹饪求助响应（正常回答或拦截结构二选一，运行时以 blocked 字段判别） */
export type CookingHelpOutcome = CookingHelpResponse | CookingHelpBlockedResponse
