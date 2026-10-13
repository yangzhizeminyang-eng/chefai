/**
 * 文件职责：REST API 端点封装（自 web-stage1/src/api/endpoints.ts 逐函数迁移，
 * 函数名 / 参数 / 返回类型 / URL / 方法全部保持一致；底层由 axios 换为本工程 request 封装）。
 * 差异点（阶段二小程序新增）：
 * - postVisionRecognize(file: File) → postVisionRecognize(tempFilePath: string)：
 *   改用 uni.uploadFile 上传临时文件（header 携带 X-Request-Id / X-Anonymous-Id）；
 * - postWxLogin：POST /v1/auth/wx-login（本期后端未实现，调用方须降级处理，契约预留）；
 * - postTrackEvents：POST /v1/track/events（本期后端未实现，调用方失败丢弃）。
 * 错误统一由 request 层归一为 { code, message, detail? } 对象抛出。
 */
import {
  get as getRequest,
  post as postRequest,
  put as putRequest,
  patch as patchRequest,
  del as delRequest,
  RECOGNIZE_TIMEOUT_MS,
  INNOVATION_TIMEOUT_MS,
  generateRequestId,
  API_BASE_URL,
} from './request'
import { fromUniFailure } from '@shared/utils/apiError'
import type { ApiError } from '@shared/types'
import { get as storageGet, ANONYMOUS_ID_KEY } from '@/utils/storage'
import type {
  AnonymousResponse,
  AskResponse,
  BlockedResponse,
  ConsentResponse,
  ConsentSensitiveResponse,
  CookingHelpOutcome,
  CookingSession,
  DietGoal,
  DeductConfirmBody,
  DeductSuggestResponse,
  FamilyMember,
  FamilyProfile,
  FavoriteItem,
  FavoritesResponse,
  FeedbackCreateResponse,
  FeedbackDetailResponse,
  FilteredRecommendRequestBody,
  FilteredRecommendResponse,
  HistoryResponse,
  HomeResponse,
  InnovationAdoptResponse,
  InnovationFeedbackBody,
  InnovationJobCreated,
  InnovationJobStatusResponse,
  InnovationPrecheckResponse,
  InnovationRecipe,
  InnovationReuseResponse,
  InventoryCreateBody,
  InventoryItem,
  InventoryListResponse,
  InventoryPatchBody,
  MeExportData,
  MemberMeResponse,
  MemberMockPayResponse,
  MemberOrderCreateResponse,
  MemberOrdersResponse,
  MemberPlanResponse,
  NutritionManualBody,
  NutritionManualResponse,
  NutritionSummaryResponse,
  NutritionResult,
  RecommendRequest,
  RecommendResponse,
  RecipeDetail,
  RecipeSearchResponse,
  SettingsData,
  ShoppingCreateBody,
  ShoppingListResponse,
  SignatureDishesResponse,
  SkillProfile,
  Switches,
  TraceDetail,
  TraceListItem,
  VisionConfirmResponse,
  VisionRecognizeResponse,
  Ingredient,
} from '@shared/types'

/* ═══════════════ 阶段一基础端点 ═══════════════ */

/**
 * 创建匿名会话（POST /v1/auth/anonymous）。
 * 与 web-stage1 同构仅换值：client_type 由 'web_stage1' 改为 'miniprogram'（文档 §11.2）。
 * @returns 含 anonymous_id 的响应体
 * @throws 归一化 ApiError
 */
export function postAnonymous(): Promise<AnonymousResponse> {
  return postRequest<AnonymousResponse>('/v1/auth/anonymous', { client_type: 'miniprogram' })
}

/**
 * 微信登录（POST /v1/auth/wx-login）：uni.login code 换会话令牌。
 * ⚠️ 本期后端未实现该接口（预期 404）：调用方须按 WxLoginResult 降级处理，勿直接向用户抛错。
 * @param code uni.login 返回的临时登录凭证
 * @returns 令牌 + 用户 ID + 是否合并了历史匿名数据
 * @throws 归一化 ApiError（404 / 网络失败等，由调用方静默降级）
 */
export interface WxLoginResponse {
  /** 会话令牌（后续登录态请求头使用） */
  token: string
  /** 用户 ID */
  user_id: string
  /** 是否合并了同 anonymous_id 的历史匿名数据（合并由后端完成） */
  merged: boolean
}

/**
 * 微信登录请求封装（契约预留，本期后端未实现）。
 * @param code uni.login 的临时登录凭证（一次性，5 分钟有效）
 * @returns 登录响应体
 * @throws 归一化 ApiError（本期预期 404，调用方降级）
 */
export function postWxLogin(code: string): Promise<WxLoginResponse> {
  return postRequest<WxLoginResponse>('/v1/auth/wx-login', { code })
}

/**
 * 免责声明同意落库（POST /v1/consent/disclaimer）。
 * @param version 免责声明版本号（当前固定 DISCLAIMER_V1）
 * @returns 同意记录结果
 * @throws 归一化 ApiError
 */
export function postConsent(version: string = 'DISCLAIMER_V1'): Promise<ConsentResponse> {
  return postRequest<ConsentResponse>('/v1/consent/disclaimer', { disclaimer_version: version })
}

/**
 * 查询食材库（GET /v1/ingredients），支持分类与关键词（含别名）过滤。
 * @param params.category 分类编码（10 类，可选）
 * @param params.q 关键词（含别名搜索，可选）
 * @returns 食材列表
 * @throws 归一化 ApiError
 */
export function getIngredients(params?: { category?: string; q?: string }): Promise<IngredientListResponse> {
  return getRequest<IngredientListResponse>('/v1/ingredients', params)
}

/** 食材列表响应体 */
export interface IngredientListResponse {
  /** 食材数组 */
  items: Ingredient[]
}

/**
 * 自然语言提问（POST /v1/ask）：输入闸门 → 意图路由 → 受限问答/搜索；命中阻断返回 G-01 数据。
 * @param question 用户输入的自然语言文本
 * @returns 意图与对应负载（answer / recipe_ids / blocked）
 * @throws 归一化 ApiError
 */
export function postAsk(question: string): Promise<AskResponse> {
  return postRequest<AskResponse>('/v1/ask', { question })
}

/**
 * 推荐主接口（POST /v1/recommend）：三档结果 + rank_reasons + filtered_by；短路返回体纯净。
 * @param body 推荐请求体（request_id 由请求层自动注入，也可显式传入）
 * @returns 正常路径为 RecommendResponse，一票否决时后端返回 BlockedResponse
 * @throws 归一化 ApiError
 */
export function postRecommend(body: RecommendRequest): Promise<RecommendResponse | BlockedResponse> {
  return postRequest<RecommendResponse | BlockedResponse>('/v1/recommend', body)
}

/**
 * 布尔硬过滤重放（POST /v1/recommend/filtered）：W-02「显示被我过滤掉的菜」明细数据源。
 * 以用户食材 + 档案过敏原/忌口/设备现场重放布尔硬过滤，返回会被移除的菜谱及
 * {type, detail} 结构化原因；主推荐响应不含 filtered 明细（仅 filtered_by 计数），
 * 清单必须通过本接口获取。
 * @param body 重放请求体（ingredients + allergen_codes/dietary_restrictions/equipment 等）
 * @returns 被过滤菜谱列表与总数
 * @throws 归一化 ApiError
 */
export function postRecommendFiltered(body: FilteredRecommendRequestBody): Promise<FilteredRecommendResponse> {
  return postRequest<FilteredRecommendResponse>('/v1/recommend/filtered', body)
}

/**
 * 获取菜谱详情（GET /v1/recipes/{id}），支持 servings 缩放重算。
 * @param id 菜谱 ID
 * @param servings 份数（可选，缺省用菜谱基准份数）
 * @returns 菜谱详情
 * @throws 归一化 ApiError
 */
export function getRecipe(id: number | string, servings?: number): Promise<RecipeDetail> {
  return getRequest<RecipeDetail>(`/v1/recipes/${id}`, servings != null ? { servings } : undefined)
}

/**
 * 菜谱搜索（GET /v1/recipes?q=&page=&page_size=，DEF-02 后端配套）。
 * q 模糊匹配菜名与食材名/别名，仅返回已发布菜谱；q 缺省返回全部分页列表。
 * @param params.q 搜索关键词（可选）
 * @param params.page 页码（可选，默认 1）
 * @param params.page_size 每页条数（可选，默认 10，上限 50）
 * @returns 菜谱列表 + 总命中数
 * @throws 归一化 ApiError
 */
export function getRecipes(params?: {
  q?: string
  page?: number
  page_size?: number
}): Promise<RecipeSearchResponse> {
  return getRequest<RecipeSearchResponse>('/v1/recipes', params)
}

/**
 * 获取营养估算（GET /v1/recipes/{id}/nutrition），缺失项标注 excluded_items。
 * @param id 菜谱 ID
 * @param servings 份数（可选，营养随份数线性重算）
 * @returns 营养估算结果
 * @throws 归一化 ApiError
 */
export function getNutrition(id: number | string, servings?: number): Promise<NutritionResult> {
  return getRequest<NutritionResult>(`/v1/recipes/${id}/nutrition`, servings != null ? { servings } : undefined)
}

/**
 * 创建烹饪会话（POST /v1/cooking/sessions），后端会做过敏原冲突检查。
 * @param body 含菜谱 ID 与份数
 * @returns 新建的烹饪会话
 * @throws 归一化 ApiError
 */
export function createCookingSession(body: { recipe_id: number; servings: number }): Promise<CookingSession> {
  return postRequest<CookingSession>('/v1/cooking/sessions', body)
}

/**
 * 更新烹饪会话（PATCH /v1/cooking/sessions/{id}）：步骤推进 / 断点续做。
 * @param sessionId 会话 ID
 * @param patch 当前步骤与状态增量
 * @returns 更新后的烹饪会话
 * @throws 归一化 ApiError
 */
export function patchCookingSession(
  sessionId: string,
  patch: { current_step_no?: number; status?: CookingSession['status'] },
): Promise<CookingSession> {
  return patchRequest<CookingSession>(`/v1/cooking/sessions/${sessionId}`, patch)
}

/**
 * 完成烹饪会话（POST /v1/cooking/sessions/{id}/finish），可选评分与标签。
 * DEF-05：完成页评价组件携带 {rating, tags} 提交；会话已 completed 时后端对带
 * rating 的请求做幂等评分补录（重复补录 409「该次烹饪已完成评价」）。
 * @param sessionId 会话 ID
 * @param rating 评分 1~5（可选，null 表示跳过评分）
 * @param tags 评价标签列表（可选，如 ['太咸', '完美']）
 * @returns 完成后的烹饪会话
 * @throws 归一化 ApiError
 */
export function finishCookingSession(sessionId: string, rating?: number | null, tags?: string[]): Promise<CookingSession> {
  return postRequest<CookingSession>(`/v1/cooking/sessions/${sessionId}/finish`, {
    rating: rating ?? null,
    tags: tags ?? [],
  })
}

/**
 * 查询 Agent 调度 trace 详情（GET /v1/trace/{request_id}），阶段一面板数据源。
 * @param requestId 幂等键
 * @returns 节点列表 + 风控判定 + veto + 汇总
 * @throws 归一化 ApiError
 */
export function getTrace(requestId: string): Promise<TraceDetail> {
  return getRequest<TraceDetail>(`/v1/trace/${requestId}`)
}

/**
 * 查询最近 trace 列表（GET /v1/trace），面板场景切换用。
 * @param limit 返回条数上限（可选，默认后端决定）
 * @returns trace 列表
 * @throws 归一化 ApiError
 */
export function listTraces(limit?: number): Promise<TraceListItem[]> {
  return getRequest<TraceListItem[]>('/v1/trace', limit != null ? { limit } : undefined)
}

/**
 * 拉取远程开关（GET /v1/config/switches）：4 模块开关。
 * @returns 开关集合
 * @throws 归一化 ApiError
 */
export function getSwitches(): Promise<Switches> {
  return getRequest<Switches>('/v1/config/switches')
}

/* ═══════════════ 阶段二新增端点（Task 9 契约） ═══════════════ */

/* ── 首页聚合 ── */

/**
 * 首页聚合数据（GET /v1/home）：入口可用性 / 未完成会话 / 临期食材 / 档案提示 / 时令分类。
 * @returns 首页聚合响应体
 * @throws 归一化 ApiError
 */
export function getHome(): Promise<HomeResponse> {
  return getRequest<HomeResponse>('/v1/home')
}

/* ── 家庭档案 ── */

/**
 * 获取家庭档案（GET /v1/profile/family）：家庭成员 + 口味 + 过敏原。
 * @returns 家庭档案
 * @throws 归一化 ApiError
 */
export function getFamilyProfile(): Promise<FamilyProfile> {
  return getRequest<FamilyProfile>('/v1/profile/family')
}

/**
 * 整体保存家庭档案（PUT /v1/profile/family）。
 * @param body 家庭名称 + 全量成员列表
 * @returns 保存后的家庭档案
 * @throws 归一化 ApiError
 */
export function putFamilyProfile(body: { name: string; members: FamilyMember[] }): Promise<FamilyProfile> {
  return putRequest<FamilyProfile>('/v1/profile/family', body)
}

/**
 * 新增家庭成员（POST /v1/profile/members，body 为单个成员）。
 * @param member 新成员数据（无 id）
 * @returns 创建成功后的成员（含后端生成的 id）
 * @throws 归一化 ApiError
 */
export function postFamilyMember(member: Omit<FamilyMember, 'id'>): Promise<FamilyMember> {
  return postRequest<FamilyMember>('/v1/profile/members', member)
}

/**
 * 更新家庭成员（PUT /v1/profile/members/{id}）。
 * @param id 成员 ID
 * @param member 成员字段增量
 * @returns 更新后的成员
 * @throws 归一化 ApiError
 */
export function putFamilyMember(id: number, member: Partial<FamilyMember>): Promise<FamilyMember> {
  return putRequest<FamilyMember>(`/v1/profile/members/${id}`, member)
}

/**
 * 删除家庭成员（DELETE /v1/profile/members/{id}）。
 * @param id 成员 ID
 * @returns 无（删除成功）
 * @throws 归一化 ApiError
 */
export function deleteFamilyMember(id: number): Promise<void> {
  return delRequest<void>(`/v1/profile/members/${id}`)
}

/**
 * 获取厨艺与设备档案（GET /v1/profile/skill）。
 * @returns 厨艺等级 + 已有设备列表
 * @throws 归一化 ApiError
 */
export function getSkillProfile(): Promise<SkillProfile> {
  return getRequest<SkillProfile>('/v1/profile/skill')
}

/**
 * 保存厨艺与设备档案（PUT /v1/profile/skill）。
 * @param body 厨艺等级（1~5）与设备列表
 * @returns 保存后的档案
 * @throws 归一化 ApiError
 */
export function putSkillProfile(body: SkillProfile): Promise<SkillProfile> {
  return putRequest<SkillProfile>('/v1/profile/skill', body)
}

/**
 * 获取饮食目标（GET /v1/profile/diet-goal）。
 * @returns 目标 5 类之一 + 备注
 * @throws 归一化 ApiError
 */
export function getDietGoal(): Promise<DietGoal> {
  return getRequest<DietGoal>('/v1/profile/diet-goal')
}

/**
 * 保存饮食目标（PUT /v1/profile/diet-goal）。
 * @param body 目标 + 备注
 * @returns 保存后的目标
 * @throws 归一化 ApiError
 */
export function putDietGoal(body: DietGoal): Promise<DietGoal> {
  return putRequest<DietGoal>('/v1/profile/diet-goal', body)
}

/* ── 敏感操作同意 ── */

/**
 * PIPL 敏感信息单独同意落库（POST /v1/consent/sensitive）。
 * @param scene 同意场景编码（如 family_allergen）
 * @returns 同意记录 ID
 * @throws 归一化 ApiError
 */
export function postConsentSensitive(scene: string): Promise<ConsentSensitiveResponse> {
  return postRequest<ConsentSensitiveResponse>('/v1/consent/sensitive', { scene })
}

/* ── 库存 ── */

/**
 * 查询库存列表（GET /v1/inventory），可按状态过滤。
 * @param status 条目状态过滤（active / used / expired / discarded，可选）
 * @returns 库存条目列表
 * @throws 归一化 ApiError
 */
export function getInventory(status?: InventoryItem['status']): Promise<InventoryListResponse> {
  return getRequest<InventoryListResponse>('/v1/inventory', status ? { status } : undefined)
}

/**
 * 新增库存条目（POST /v1/inventory）。
 * @param body 食材 ID + 数量档位 + 可选到期日/位置
 * @returns 创建后的条目
 * @throws 归一化 ApiError
 */
export function postInventory(body: InventoryCreateBody): Promise<InventoryItem> {
  return postRequest<InventoryItem>('/v1/inventory', body)
}

/**
 * 修改库存条目（PATCH /v1/inventory/{id}）。
 * @param id 库存条目 ID
 * @param patch 增量字段（数量档位/位置/到期日/状态）
 * @returns 更新后的条目
 * @throws 归一化 ApiError
 */
export function patchInventory(id: number, patch: InventoryPatchBody): Promise<InventoryItem> {
  return patchRequest<InventoryItem>(`/v1/inventory/${id}`, patch)
}

/**
 * 删除库存条目（DELETE /v1/inventory/{id}）。
 * @param id 库存条目 ID
 * @returns 无（删除成功）
 * @throws 归一化 ApiError
 */
export function deleteInventory(id: number): Promise<void> {
  return delRequest<void>(`/v1/inventory/${id}`)
}

/**
 * 烹饪完成后的库存扣减建议（POST /v1/inventory/deduct-suggest）。
 * @param sessionId 本次烹饪会话 ID
 * @returns 建议列表（可能为空）
 * @throws 归一化 ApiError
 */
export function postDeductSuggest(sessionId: string): Promise<DeductSuggestResponse> {
  return postRequest<DeductSuggestResponse>('/v1/inventory/deduct-suggest', { session_id: sessionId })
}

/**
 * 提交用户勾选的扣减确认（POST /v1/inventory/deduct-confirm）。
 * @param body 会话 ID + 勾选确认列表
 * @returns 无（确认成功）
 * @throws 归一化 ApiError
 */
export function postDeductConfirm(body: DeductConfirmBody): Promise<void> {
  return postRequest<void>('/v1/inventory/deduct-confirm', body)
}

/* ── 购物清单 ── */

/**
 * 查询购物清单（GET /v1/shopping-list）。
 * @returns 清单条目列表
 * @throws 归一化 ApiError
 */
export function getShoppingList(): Promise<ShoppingListResponse> {
  return getRequest<ShoppingListResponse>('/v1/shopping-list')
}

/**
 * 新增购物清单条目（POST /v1/shopping-list，后端按食材合并去重）。
 * @param body 新增条目列表
 * @returns 合并后的清单条目列表
 * @throws 归一化 ApiError
 */
export function postShoppingList(body: ShoppingCreateBody): Promise<ShoppingListResponse> {
  return postRequest<ShoppingListResponse>('/v1/shopping-list', body)
}

/**
 * 删除购物清单条目（DELETE /v1/shopping-list/{id}）。
 * @param id 条目 ID
 * @returns 无（删除成功）
 * @throws 归一化 ApiError
 */
export function deleteShoppingItem(id: number): Promise<void> {
  return delRequest<void>(`/v1/shopping-list/${id}`)
}

/**
 * 购物清单条目一键转入库存（POST /v1/shopping-list/{id}/to-inventory）。
 * @param id 条目 ID
 * @returns 无（转入成功）
 * @throws 归一化 ApiError
 */
export function postShoppingToInventory(id: number): Promise<void> {
  return postRequest<void>(`/v1/shopping-list/${id}/to-inventory`, {})
}

/* ── 营养汇总 ── */

/**
 * 查询营养汇总（GET /v1/nutrition/summary?days=N）。
 * @param days 统计天数（默认 7）
 * @returns 逐日四餐数据 + 周期合计 + 免责文案
 * @throws 归一化 ApiError
 */
export function getNutritionSummary(days: number = 7): Promise<NutritionSummaryResponse> {
  return getRequest<NutritionSummaryResponse>('/v1/nutrition/summary', { days })
}

/**
 * 手动补录外食（POST /v1/nutrition/manual，走风控）。
 * @param body 餐次 + 描述
 * @returns 正常 {ok:true}；命中拦截返回 blocked 结构
 * @throws 归一化 ApiError
 */
export function postNutritionManual(body: NutritionManualBody): Promise<NutritionManualResponse> {
  return postRequest<NutritionManualResponse>('/v1/nutrition/manual', body)
}

/* ── 收藏 / 历史 / 拿手菜 / 设置 ── */

/**
 * 查询收藏（GET /v1/favorites），可按分组过滤。
 * @param group 分组名（可选，缺省返回全部分组）
 * @returns 分组列表 + 收藏条目
 * @throws 归一化 ApiError
 */
export function getFavorites(group?: string): Promise<FavoritesResponse> {
  return getRequest<FavoritesResponse>('/v1/favorites', group ? { group } : undefined)
}

/**
 * 添加收藏（POST /v1/favorites）。
 * @param recipeId 菜谱 ID
 * @param groupName 分组名（可选，缺省由后端归入默认分组）
 * @returns 创建后的收藏条目
 * @throws 归一化 ApiError
 */
export function postFavorite(recipeId: number, groupName?: string): Promise<FavoriteItem> {
  return postRequest<FavoriteItem>('/v1/favorites', { recipe_id: recipeId, group_name: groupName })
}

/**
 * 取消收藏（DELETE /v1/favorites/{recipeId}）。
 * @param recipeId 菜谱 ID
 * @returns 无（删除成功）
 * @throws 归一化 ApiError
 */
export function deleteFavorite(recipeId: number): Promise<void> {
  return delRequest<void>(`/v1/favorites/${recipeId}`)
}

/**
 * 查询烹饪历史（GET /v1/history?limit=N），后端按完成时间倒序。
 * @param limit 返回条数上限（默认 50）
 * @returns 历史条目列表
 * @throws 归一化 ApiError
 */
export function getHistory(limit: number = 50): Promise<HistoryResponse> {
  return getRequest<HistoryResponse>('/v1/history', { limit })
}

/**
 * 查询拿手菜（GET /v1/signature-dishes），按烹饪次数倒序。
 * @returns 拿手菜列表
 * @throws 归一化 ApiError
 */
export function getSignatureDishes(): Promise<SignatureDishesResponse> {
  return getRequest<SignatureDishesResponse>('/v1/signature-dishes')
}

/**
 * 获取用户设置（GET /v1/settings）。
 * @returns 字号/单位/语音/提醒设置
 * @throws 归一化 ApiError
 */
export function getSettings(): Promise<SettingsData> {
  return getRequest<SettingsData>('/v1/settings')
}

/**
 * 保存用户设置（PUT /v1/settings）。
 * @param body 全量设置字段
 * @returns 保存后的设置
 * @throws 归一化 ApiError
 */
export function putSettings(body: SettingsData): Promise<SettingsData> {
  return putRequest<SettingsData>('/v1/settings', body)
}

/* ── 数据权利 ── */

/**
 * 导出个人数据（GET /v1/me/export，返回 JSON 结构，由页面触发下载/转发）。
 * @returns 导出的 JSON 数据（结构不做前端假设）
 * @throws 归一化 ApiError
 */
export function getMeExport(): Promise<MeExportData> {
  return getRequest<MeExportData>('/v1/me/export')
}

/**
 * 注销账号（DELETE /v1/me）。
 * @returns 无（注销成功）
 * @throws 归一化 ApiError
 */
export function deleteMeAccount(): Promise<void> {
  return delRequest<void>('/v1/me')
}

/* ── 会员 ── */

/**
 * 获取会员套餐与支付开关（GET /v1/member/plan）。
 * @returns 三档套餐 + 支付渠道 + 支付总开关
 * @throws 归一化 ApiError
 */
export function getMemberPlan(): Promise<MemberPlanResponse> {
  return getRequest<MemberPlanResponse>('/v1/member/plan')
}

/**
 * 获取当前会员状态与额度（GET /v1/member/me）。
 * @returns 是否会员 + 到期时间 + 识别额度
 * @throws 归一化 ApiError
 */
export function getMemberMe(): Promise<MemberMeResponse> {
  return getRequest<MemberMeResponse>('/v1/member/me')
}

/**
 * 创建会员订单（POST /v1/member/orders）。
 * @param productType 套餐类型（monthly / quarterly / yearly）
 * @returns 新建订单（pending）
 * @throws 归一化 ApiError
 */
export function postMemberOrder(productType: MemberPlanResponse['plans'][number]['product_type']): Promise<MemberOrderCreateResponse> {
  return postRequest<MemberOrderCreateResponse>('/v1/member/orders', { product_type: productType })
}

/**
 * 模拟支付（POST /v1/member/orders/{orderNo}/mock-pay，联调用；iOS 永不到达此处）。
 * @param orderNo 订单号
 * @returns 支付后状态与时间
 * @throws 归一化 ApiError
 */
export function postMemberMockPay(orderNo: string): Promise<MemberMockPayResponse> {
  return postRequest<MemberMockPayResponse>(`/v1/member/orders/${orderNo}/mock-pay`, {})
}

/**
 * 查询订单列表（GET /v1/member/orders）。
 * @returns 订单条目数组
 * @throws 归一化 ApiError
 */
export function getMemberOrders(): Promise<MemberOrdersResponse> {
  return getRequest<MemberOrdersResponse>('/v1/member/orders')
}

/* ── 反馈 ── */

/**
 * 提交意见反馈（POST /v1/feedback）。
 * @param content 反馈内容
 * @param type 反馈类型（bug / suggestion / other）
 * @returns 反馈 ID + 回执号 + 承诺回复时限
 * @throws 归一化 ApiError
 */
export function postFeedback(content: string, type: 'bug' | 'suggestion' | 'other'): Promise<FeedbackCreateResponse> {
  return postRequest<FeedbackCreateResponse>('/v1/feedback', { content, type })
}

/**
 * 查询反馈处理状态（GET /v1/feedback/{id}）。
 * @param id 反馈 ID
 * @returns 状态 + 回执号 + 提交时间
 * @throws 归一化 ApiError
 */
export function getFeedbackDetail(id: number): Promise<FeedbackDetailResponse> {
  return getRequest<FeedbackDetailResponse>(`/v1/feedback/${id}`)
}

/* ── AI 创新 ── */

/**
 * 创新预检（POST /v1/innovation/precheck）：食材组合合法性检查。
 * @param ingredients 食材名列表
 * @returns 预检结果（blocked=true 时带拦截话术）
 * @throws 归一化 ApiError
 */
export function postInnovationPrecheck(ingredients: string[]): Promise<InnovationPrecheckResponse> {
  return postRequest<InnovationPrecheckResponse>('/v1/innovation/precheck', { ingredients })
}

/**
 * 生成创新菜谱（POST /v1/innovation/generate，同步兼容口）。
 * P1 DEF-01：LLM 表达实测 10–30s（后端 25s 硬超时 + 模板降级兜底），本请求
 * 显式传 60s 超时覆盖默认 15s，否则用户侧 100% 超时。
 * 主链路已迁移异步 job（见 postInnovationJobCreate / getInnovationJob，M-01），
 * 本接口保留向后兼容。
 * @param ingredients 食材名列表
 * @returns 创新菜谱实体（含创新依据与强制声明；basis.generated_by 标注 llm/template）
 * @throws 归一化 ApiError
 */
export function postInnovationGenerate(ingredients: string[]): Promise<InnovationRecipe> {
  return postRequest<InnovationRecipe>('/v1/innovation/generate', { ingredients }, INNOVATION_TIMEOUT_MS)
}

/**
 * 提交创新生成异步任务（POST /v1/innovation/jobs，M-01 异步化主链路）。
 * 后端校验后线程池执行生成并秒级返回 202（job 排队中），LLM 波动被 job 状态吸收，
 * 前端不再依赖 60s 同步长请求；提交本身不等 LLM，30s 超时仅为提交链路留余量。
 * @param ingredients 食材名列表
 * @returns 任务创建结果（job_id + status=pending）
 * @throws 归一化 ApiError
 */
export function postInnovationJobCreate(ingredients: string[]): Promise<InnovationJobCreated> {
  return postRequest<InnovationJobCreated>('/v1/innovation/jobs', { ingredients }, 30000)
}

/**
 * 查询创新生成任务状态（GET /v1/innovation/jobs/{job_id}）。
 * 前端以 2.5s 间隔轮询本接口直至终态：succeeded（含完整 recipe）/ failed（含 error）/
 * blocked（含 issues）；404 = 任务不存在或他人 job（跨用户隔离，由请求层归一为错误）。
 * @param jobId 任务 ID（来自 postInnovationJobCreate 返回）
 * @returns 任务状态（含 recipe / issues / error 视终态而定）
 * @throws 归一化 ApiError
 */
export function getInnovationJob(jobId: string): Promise<InnovationJobStatusResponse> {
  return getRequest<InnovationJobStatusResponse>(`/v1/innovation/jobs/${jobId}`)
}

/**
 * 获取创新菜谱详情（GET /v1/innovation/recipes/{id}）。
 * @param id 创新菜谱 ID
 * @returns 创新菜谱实体
 * @throws 归一化 ApiError
 */
export function getInnovationRecipe(id: number): Promise<InnovationRecipe> {
  return getRequest<InnovationRecipe>(`/v1/innovation/recipes/${id}`)
}

/**
 * 采纳创新菜（POST /v1/innovation/recipes/{id}/adopt），入库「我的创新菜」。
 * @param id 创新菜谱 ID
 * @returns 采纳结果
 * @throws 归一化 ApiError
 */
export function postInnovationAdopt(id: number): Promise<InnovationAdoptResponse> {
  return postRequest<InnovationAdoptResponse>(`/v1/innovation/recipes/${id}/adopt`, {})
}

/**
 * 复用创新菜（POST /v1/innovation/recipes/{id}/reuse）：再次开做。
 * @param id 创新菜谱 ID
 * @returns 可复用标记 + 创新菜谱实体
 * @throws 归一化 ApiError
 */
export function postInnovationReuse(id: number): Promise<InnovationReuseResponse> {
  return postRequest<InnovationReuseResponse>(`/v1/innovation/recipes/${id}/reuse`, {})
}

/**
 * 创新菜评分反馈（POST /v1/innovation/recipes/{id}/feedback）。
 * @param id 创新菜谱 ID
 * @param body 评分 1~5 与可选评论
 * @returns 无（提交成功）
 * @throws 归一化 ApiError
 */
export function postInnovationFeedback(id: number, body: InnovationFeedbackBody): Promise<void> {
  return postRequest<void>(`/v1/innovation/recipes/${id}/feedback`, body)
}

/* ── 图像识别 ── */

/**
 * 冰箱照片识别（POST /v1/vision/recognize，uni.uploadFile 临时文件上传）。
 * 与 web-stage1 差异：入参由 File 改为小程序 choose/compress 产出的临时文件路径。
 * request_id 放 X-Request-Id 头（multipart 体不注入 JSON 字段，对齐 web-stage1 FormData 口径）；
 * 超时 30s（真实视觉模型 P95 15~20s）；client_type 经 uploadFile formData 兜底注入。
 * @param tempFilePath 压缩后的图像临时路径（uni.chooseMedia/compressImage 产出）
 * @returns 识别结果 + 剩余额度 + 降级标记
 * @throws 归一化 ApiError（非 2xx 取后端 message；响应体非法 JSON 按 NETWORK 兜底）
 */
export function postVisionRecognize(tempFilePath: string): Promise<VisionRecognizeResponse> {
  const rid = generateRequestId()
  const header: Record<string, string> = { 'X-Request-Id': rid }
  const anonId = storageGet<string>(ANONYMOUS_ID_KEY, '')
  if (anonId) header['X-Anonymous-Id'] = anonId
  return new Promise<VisionRecognizeResponse>((resolve, reject) => {
    try {
      uni.uploadFile({
        url: `${API_BASE_URL}/v1/vision/recognize`,
        filePath: tempFilePath,
        name: 'file',
        header,
        formData: { client_type: 'miniprogram' },
        timeout: RECOGNIZE_TIMEOUT_MS,
        success: (res) => {
          let payload: unknown = null
          try {
            payload = JSON.parse(res.data)
          } catch {
            payload = null
          }
          if (res.statusCode >= 200 && res.statusCode < 300 && payload && typeof payload === 'object') {
            resolve(payload as VisionRecognizeResponse)
            return
          }
          const errPayload = (payload ?? {}) as { message?: string; detail?: unknown }
          reject({
            code: res.statusCode,
            message: errPayload.message ?? `识别请求失败（${res.statusCode}）`,
            detail: errPayload.detail,
          })
        },
        fail: (err) => {
          reject(fromUniFailure(err?.errMsg ?? ''))
        },
      })
    } catch (e) {
      // uploadFile 同步异常（参数非法等）：按网络不可用兜底
      const apiError: ApiError = fromUniFailure('')
      reject(apiError)
      void e
    }
  })
}

/**
 * 确认识别结果入库（POST /v1/vision/confirm）。
 * @param names 用户勾选确认的食材名列表
 * @returns 成功加入的食材数
 * @throws 归一化 ApiError
 */
export function postVisionConfirm(names: string[]): Promise<VisionConfirmResponse> {
  return postRequest<VisionConfirmResponse>('/v1/vision/confirm', { names })
}

/* ── 烹饪求助 ── */

/**
 * 烹饪过程求助（POST /v1/cooking/sessions/{id}/help）。
 * 正常返回回答列表；命中风控返回 blocked 结构；429 为当日次数超限（由调用方按错误码处理）。
 * @param sessionId 烹饪会话 ID
 * @param question 求助问题
 * @returns 回答列表或拦截结构
 * @throws 归一化 ApiError
 */
export function postCookingHelp(sessionId: string, question: string): Promise<CookingHelpOutcome> {
  return postRequest<CookingHelpOutcome>(`/v1/cooking/sessions/${sessionId}/help`, { question })
}

/* ── 埋点上报 ── */

/**
 * 埋点事件负载（POST /v1/track/events 请求体元素）。
 */
export interface TrackEventPayload {
  /** 事件名（对齐 TrackEventName 枚举口径，string 便于后端宽松接收） */
  name: string
  /** 事件属性（可选，结构随事件定义） */
  props?: Record<string, unknown>
  /** 事件发生时间（毫秒时间戳，客户端本地时钟） */
  ts: number
  /** 关联请求标识（生成事件时的幂等键，用于与服务端日志对账） */
  request_id: string
}

/**
 * 批量上报埋点事件（POST /v1/track/events）。
 * ⚠️ 本期后端未实现该接口：调用方（track 模块）对失败一律静默丢弃缓冲，不阻断主流程。
 * @param events 事件数组（缓冲批量提交）
 * @returns 无（成功即 resolve）
 * @throws 归一化 ApiError（调用方须自行吞掉——埋点永不阻断）
 */
export function postTrackEvents(events: TrackEventPayload[]): Promise<void> {
  return postRequest<void>('/v1/track/events', { events })
}
