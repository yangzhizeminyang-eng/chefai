/**
 * 文件职责：REST API 端点封装（对齐 spec.md 接口清单 + Task 9 阶段二新增契约）。
 * 每个函数对应一个后端接口，返回类型来自 types.ts 的契约定义；
 * 错误统一由 axios 拦截器归一为 { code, message } 抛出。
 */
import apiClient from './index'
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
  HistoryResponse,
  HomeResponse,
  InnovationAdoptResponse,
  InnovationFeedbackBody,
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
  NutritionResult,
  NutritionSummaryResponse,
  RecommendRequest,
  RecommendResponse,
  RecipeDetail,
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
} from './types'

/**
 * 创建匿名会话（POST /v1/auth/anonymous）。
 * @returns 含 anonymous_id 的响应体
 */
export function postAnonymous(): Promise<AnonymousResponse> {
  return apiClient.post('/v1/auth/anonymous', { client_type: 'web_stage1' })
}

/**
 * 免责声明同意落库（POST /v1/consent/disclaimer）。
 * @param version 免责声明版本号（当前固定 DISCLAIMER_V1）
 * @returns 同意记录结果
 */
export function postConsent(version: string = 'DISCLAIMER_V1'): Promise<ConsentResponse> {
  return apiClient.post('/v1/consent/disclaimer', { disclaimer_version: version })
}

/**
 * 查询食材库（GET /v1/ingredients），支持分类与关键词（含别名）过滤。
 * @param params.category 分类编码（10 类，可选）
 * @param params.q 关键词（含别名搜索，可选）
 * @returns 食材列表
 */
export function getIngredients(params?: { category?: string; q?: string }): Promise<IngredientListResponse> {
  return apiClient.get('/v1/ingredients', { params })
}

/** 食材列表响应体 */
export interface IngredientListResponse {
  /** 食材数组 */
  items: import('./types').Ingredient[]
}

/**
 * 自然语言提问（POST /v1/ask）：输入闸门 → 意图路由 → 受限问答/搜索；命中阻断返回 G-01 数据。
 * @param question 用户输入的自然语言文本
 * @returns 意图与对应负载（answer / recipe_ids / blocked）
 */
export function postAsk(question: string): Promise<AskResponse> {
  return apiClient.post('/v1/ask', { question })
}

/**
 * 推荐主接口（POST /v1/recommend）：三档结果 + rank_reasons + filtered_by；短路返回体纯净。
 * @param body 推荐请求体（request_id 由拦截器自动注入，也可显式传入）
 * @returns 正常路径为 RecommendResponse，一票否决时后端返回 BlockedResponse
 */
export function postRecommend(body: RecommendRequest): Promise<RecommendResponse | BlockedResponse> {
  return apiClient.post('/v1/recommend', body)
}

/**
 * 获取菜谱详情（GET /v1/recipes/{id}），支持 servings 缩放重算。
 * @param id 菜谱 ID
 * @param servings 份数（可选，缺省用菜谱基准份数）
 * @returns 菜谱详情
 */
export function getRecipe(id: number | string, servings?: number): Promise<RecipeDetail> {
  return apiClient.get(`/v1/recipes/${id}`, { params: servings != null ? { servings } : undefined })
}

/**
 * 获取营养估算（GET /v1/recipes/{id}/nutrition），缺失项标注 excluded_items。
 * @param id 菜谱 ID
 * @param servings 份数（可选，营养随份数线性重算）
 * @returns 营养估算结果
 */
export function getNutrition(id: number | string, servings?: number): Promise<NutritionResult> {
  return apiClient.get(`/v1/recipes/${id}/nutrition`, { params: servings != null ? { servings } : undefined })
}

/**
 * 创建烹饪会话（POST /v1/cooking/sessions），后端会做过敏原冲突检查。
 * @param body 含菜谱 ID 与份数
 * @returns 新建的烹饪会话
 */
export function createCookingSession(body: { recipe_id: number; servings: number }): Promise<CookingSession> {
  return apiClient.post('/v1/cooking/sessions', body)
}

/**
 * 更新烹饪会话（PATCH /v1/cooking/sessions/{id}）：步骤推进 / 断点续做。
 * @param sessionId 会话 ID
 * @param patch 当前步骤与状态增量
 * @returns 更新后的烹饪会话
 */
export function patchCookingSession(
  sessionId: string,
  patch: { current_step_no?: number; status?: CookingSession['status'] },
): Promise<CookingSession> {
  return apiClient.patch(`/v1/cooking/sessions/${sessionId}`, patch)
}

/**
 * 完成烹饪会话（POST /v1/cooking/sessions/{id}/finish），可选评分。
 * @param sessionId 会话 ID
 * @param rating 评分 1~5（可选，null 表示跳过评分）
 * @returns 完成后的烹饪会话
 */
export function finishCookingSession(sessionId: string, rating?: number): Promise<CookingSession> {
  return apiClient.post(`/v1/cooking/sessions/${sessionId}/finish`, { rating: rating ?? null })
}

/**
 * 查询 Agent 调度 trace 详情（GET /v1/trace/{request_id}），阶段一面板数据源。
 * @param requestId 幂等键
 * @returns 节点列表 + 风控判定 + veto + 汇总
 */
export function getTrace(requestId: string): Promise<TraceDetail> {
  return apiClient.get(`/v1/trace/${requestId}`)
}

/**
 * 查询最近 trace 列表（GET /v1/trace），面板场景切换用。
 * @param limit 返回条数上限（可选，默认后端决定）
 * @returns trace 列表
 */
export function listTraces(limit?: number): Promise<TraceListItem[]> {
  return apiClient.get('/v1/trace', { params: limit != null ? { limit } : undefined })
}

/**
 * 拉取远程开关（GET /v1/config/switches）：4 模块开关。
 * @returns 开关集合
 */
export function getSwitches(): Promise<Switches> {
  return apiClient.get('/v1/config/switches')
}

/* ═══════════════════════════════════════════════════════════════════
 * Task 9（阶段二前端）新增端点：首页 / 档案 / 库存 / 购物清单 / 营养 /
 * 收藏历史拿手菜 / 设置与数据权利 / 会员 / 反馈 / AI 创新 / 识别 / 烹饪求助。
 * ═══════════════════════════════════════════════════════════════════ */

/* ── 首页聚合 ── */

/**
 * 首页聚合数据（GET /v1/home）：入口可用性 / 未完成会话 / 临期食材 / 档案提示 / 时令分类。
 * @returns 首页聚合响应体
 */
export function getHome(): Promise<HomeResponse> {
  return apiClient.get('/v1/home')
}

/* ── 家庭档案 ── */

/**
 * 获取家庭档案（GET /v1/profile/family）：家庭成员 + 口味 + 过敏原。
 * @returns 家庭档案
 */
export function getFamilyProfile(): Promise<FamilyProfile> {
  return apiClient.get('/v1/profile/family')
}

/**
 * 整体保存家庭档案（PUT /v1/profile/family）。
 * @param body 家庭名称 + 全量成员列表
 * @returns 保存后的家庭档案
 */
export function putFamilyProfile(body: { name: string; members: FamilyMember[] }): Promise<FamilyProfile> {
  return apiClient.put('/v1/profile/family', body)
}

/**
 * 新增家庭成员（POST /v1/profile/members，body 为单个成员）。
 * @param member 新成员数据（无 id）
 * @returns 创建成功后的成员（含后端生成的 id）
 */
export function postFamilyMember(member: Omit<FamilyMember, 'id'>): Promise<FamilyMember> {
  return apiClient.post('/v1/profile/members', member)
}

/**
 * 更新家庭成员（PUT /v1/profile/members/{id}）。
 * @param id 成员 ID
 * @param member 成员字段增量
 * @returns 更新后的成员
 */
export function putFamilyMember(id: number, member: Partial<FamilyMember>): Promise<FamilyMember> {
  return apiClient.put(`/v1/profile/members/${id}`, member)
}

/**
 * 删除家庭成员（DELETE /v1/profile/members/{id}）。
 * @param id 成员 ID
 * @returns 无（删除成功）
 */
export function deleteFamilyMember(id: number): Promise<void> {
  return apiClient.delete(`/v1/profile/members/${id}`)
}

/**
 * 获取厨艺与设备档案（GET /v1/profile/skill）。
 * @returns 厨艺等级 + 已有设备列表
 */
export function getSkillProfile(): Promise<SkillProfile> {
  return apiClient.get('/v1/profile/skill')
}

/**
 * 保存厨艺与设备档案（PUT /v1/profile/skill）。
 * @param body 厨艺等级（1~5）与设备列表
 * @returns 保存后的档案
 */
export function putSkillProfile(body: SkillProfile): Promise<SkillProfile> {
  return apiClient.put('/v1/profile/skill', body)
}

/**
 * 获取饮食目标（GET /v1/profile/diet-goal）。
 * @returns 目标 5 类之一 + 备注
 */
export function getDietGoal(): Promise<DietGoal> {
  return apiClient.get('/v1/profile/diet-goal')
}

/**
 * 保存饮食目标（PUT /v1/profile/diet-goal）。
 * @param body 目标 + 备注
 * @returns 保存后的目标
 */
export function putDietGoal(body: DietGoal): Promise<DietGoal> {
  return apiClient.put('/v1/profile/diet-goal', body)
}

/* ── 敏感操作同意 ── */

/**
 * PIPL 敏感信息单独同意落库（POST /v1/consent/sensitive）。
 * @param scene 同意场景编码（如 family_allergen）
 * @returns 同意记录 ID
 */
export function postConsentSensitive(scene: string): Promise<ConsentSensitiveResponse> {
  return apiClient.post('/v1/consent/sensitive', { scene })
}

/* ── 库存 ── */

/**
 * 查询库存列表（GET /v1/inventory），可按状态过滤。
 * @param status 条目状态过滤（active / used / expired / discarded，可选）
 * @returns 库存条目列表
 */
export function getInventory(status?: InventoryItem['status']): Promise<InventoryListResponse> {
  return apiClient.get('/v1/inventory', { params: status ? { status } : undefined })
}

/**
 * 新增库存条目（POST /v1/inventory）。
 * @param body 食材 ID + 数量档位 + 可选到期日/位置
 * @returns 创建后的条目
 */
export function postInventory(body: InventoryCreateBody): Promise<InventoryItem> {
  return apiClient.post('/v1/inventory', body)
}

/**
 * 修改库存条目（PATCH /v1/inventory/{id}）。
 * @param id 库存条目 ID
 * @param patch 增量字段（数量档位/位置/到期日/状态）
 * @returns 更新后的条目
 */
export function patchInventory(id: number, patch: InventoryPatchBody): Promise<InventoryItem> {
  return apiClient.patch(`/v1/inventory/${id}`, patch)
}

/**
 * 删除库存条目（DELETE /v1/inventory/{id}）。
 * @param id 库存条目 ID
 * @returns 无（删除成功）
 */
export function deleteInventory(id: number): Promise<void> {
  return apiClient.delete(`/v1/inventory/${id}`)
}

/**
 * 烹饪完成后的库存扣减建议（POST /v1/inventory/deduct-suggest）。
 * @param sessionId 本次烹饪会话 ID
 * @returns 建议列表（可能为空）
 */
export function postDeductSuggest(sessionId: string): Promise<DeductSuggestResponse> {
  return apiClient.post('/v1/inventory/deduct-suggest', { session_id: sessionId })
}

/**
 * 提交用户勾选的扣减确认（POST /v1/inventory/deduct-confirm）。
 * @param body 会话 ID + 勾选确认列表
 * @returns 无（确认成功）
 */
export function postDeductConfirm(body: DeductConfirmBody): Promise<void> {
  return apiClient.post('/v1/inventory/deduct-confirm', body)
}

/* ── 购物清单 ── */

/**
 * 查询购物清单（GET /v1/shopping-list）。
 * @returns 清单条目列表
 */
export function getShoppingList(): Promise<ShoppingListResponse> {
  return apiClient.get('/v1/shopping-list')
}

/**
 * 新增购物清单条目（POST /v1/shopping-list，后端按食材合并去重）。
 * @param body 新增条目列表
 * @returns 合并后的清单条目列表
 */
export function postShoppingList(body: ShoppingCreateBody): Promise<ShoppingListResponse> {
  return apiClient.post('/v1/shopping-list', body)
}

/**
 * 删除购物清单条目（DELETE /v1/shopping-list/{id}）。
 * @param id 条目 ID
 * @returns 无（删除成功）
 */
export function deleteShoppingItem(id: number): Promise<void> {
  return apiClient.delete(`/v1/shopping-list/${id}`)
}

/**
 * 购物清单条目一键转入库存（POST /v1/shopping-list/{id}/to-inventory）。
 * @param id 条目 ID
 * @returns 无（转入成功）
 */
export function postShoppingToInventory(id: number): Promise<void> {
  return apiClient.post(`/v1/shopping-list/${id}/to-inventory`, {})
}

/* ── 营养汇总 ── */

/**
 * 查询营养汇总（GET /v1/nutrition/summary?days=N）。
 * @param days 统计天数（默认 7）
 * @returns 逐日四餐数据 + 周期合计 + 免责文案
 */
export function getNutritionSummary(days: number = 7): Promise<NutritionSummaryResponse> {
  return apiClient.get('/v1/nutrition/summary', { params: { days } })
}

/**
 * 手动补录外食（POST /v1/nutrition/manual，走风控）。
 * @param body 餐次 + 描述
 * @returns 正常 {ok:true}；命中拦截返回 blocked 结构
 */
export function postNutritionManual(body: NutritionManualBody): Promise<NutritionManualResponse> {
  return apiClient.post('/v1/nutrition/manual', body)
}

/* ── 收藏 / 历史 / 拿手菜 / 设置 ── */

/**
 * 查询收藏（GET /v1/favorites），可按分组过滤。
 * @param group 分组名（可选，缺省返回全部分组）
 * @returns 分组列表 + 收藏条目
 */
export function getFavorites(group?: string): Promise<FavoritesResponse> {
  return apiClient.get('/v1/favorites', { params: group ? { group } : undefined })
}

/**
 * 添加收藏（POST /v1/favorites）。
 * @param recipeId 菜谱 ID
 * @param groupName 分组名（可选，缺省由后端归入默认分组）
 * @returns 创建后的收藏条目
 */
export function postFavorite(recipeId: number, groupName?: string): Promise<FavoriteItem> {
  return apiClient.post('/v1/favorites', { recipe_id: recipeId, group_name: groupName })
}

/**
 * 取消收藏（DELETE /v1/favorites/{recipeId}）。
 * @param recipeId 菜谱 ID
 * @returns 无（删除成功）
 */
export function deleteFavorite(recipeId: number): Promise<void> {
  return apiClient.delete(`/v1/favorites/${recipeId}`)
}

/**
 * 查询烹饪历史（GET /v1/history?limit=N），后端按完成时间倒序。
 * @param limit 返回条数上限（默认 50）
 * @returns 历史条目列表
 */
export function getHistory(limit: number = 50): Promise<HistoryResponse> {
  return apiClient.get('/v1/history', { params: { limit } })
}

/**
 * 查询拿手菜（GET /v1/signature-dishes），按烹饪次数倒序。
 * @returns 拿手菜列表
 */
export function getSignatureDishes(): Promise<SignatureDishesResponse> {
  return apiClient.get('/v1/signature-dishes')
}

/**
 * 获取用户设置（GET /v1/settings）。
 * @returns 字号/单位/语音/提醒设置
 */
export function getSettings(): Promise<SettingsData> {
  return apiClient.get('/v1/settings')
}

/**
 * 保存用户设置（PUT /v1/settings）。
 * @param body 全量设置字段
 * @returns 保存后的设置
 */
export function putSettings(body: SettingsData): Promise<SettingsData> {
  return apiClient.put('/v1/settings', body)
}

/* ── 数据权利 ── */

/**
 * 导出个人数据（GET /v1/me/export，返回 JSON 结构，由页面触发下载）。
 * @returns 导出的 JSON 数据（结构不做前端假设）
 */
export function getMeExport(): Promise<MeExportData> {
  return apiClient.get('/v1/me/export')
}

/**
 * 注销账号（DELETE /v1/me）。
 * @returns 无（注销成功）
 */
export function deleteMeAccount(): Promise<void> {
  return apiClient.delete('/v1/me')
}

/* ── 会员 ── */

/**
 * 获取会员套餐与支付开关（GET /v1/member/plan）。
 * @returns 三档套餐 + 支付渠道 + 支付总开关
 */
export function getMemberPlan(): Promise<MemberPlanResponse> {
  return apiClient.get('/v1/member/plan')
}

/**
 * 获取当前会员状态与额度（GET /v1/member/me）。
 * @returns 是否会员 + 到期时间 + 识别额度
 */
export function getMemberMe(): Promise<MemberMeResponse> {
  return apiClient.get('/v1/member/me')
}

/**
 * 创建会员订单（POST /v1/member/orders）。
 * @param productType 套餐类型（monthly / quarterly / yearly）
 * @returns 新建订单（pending）
 */
export function postMemberOrder(productType: MemberPlanResponse['plans'][number]['product_type']): Promise<MemberOrderCreateResponse> {
  return apiClient.post('/v1/member/orders', { product_type: productType })
}

/**
 * 模拟支付（POST /v1/member/orders/{orderNo}/mock-pay，web 端联调用）。
 * @param orderNo 订单号
 * @returns 支付后状态与时间
 */
export function postMemberMockPay(orderNo: string): Promise<MemberMockPayResponse> {
  return apiClient.post(`/v1/member/orders/${orderNo}/mock-pay`, {})
}

/**
 * 查询订单列表（GET /v1/member/orders）。
 * @returns 订单条目数组
 */
export function getMemberOrders(): Promise<MemberOrdersResponse> {
  return apiClient.get('/v1/member/orders')
}

/* ── 反馈 ── */

/**
 * 提交意见反馈（POST /v1/feedback）。
 * @param content 反馈内容
 * @param type 反馈类型（bug / suggestion / other）
 * @returns 反馈 ID + 回执号 + 承诺回复时限
 */
export function postFeedback(content: string, type: 'bug' | 'suggestion' | 'other'): Promise<FeedbackCreateResponse> {
  return apiClient.post('/v1/feedback', { content, type })
}

/**
 * 查询反馈处理状态（GET /v1/feedback/{id}）。
 * @param id 反馈 ID
 * @returns 状态 + 回执号 + 提交时间
 */
export function getFeedbackDetail(id: number): Promise<FeedbackDetailResponse> {
  return apiClient.get(`/v1/feedback/${id}`)
}

/* ── AI 创新 ── */

/**
 * 创新预检（POST /v1/innovation/precheck）：食材组合合法性检查。
 * @param ingredients 食材名列表
 * @returns 预检结果（blocked=true 时带拦截话术）
 */
export function postInnovationPrecheck(ingredients: string[]): Promise<InnovationPrecheckResponse> {
  return apiClient.post('/v1/innovation/precheck', { ingredients })
}

/**
 * 生成创新菜谱（POST /v1/innovation/generate）。
 * @param ingredients 食材名列表
 * @returns 创新菜谱实体（含创新依据与强制声明）
 */
export function postInnovationGenerate(ingredients: string[]): Promise<InnovationRecipe> {
  return apiClient.post('/v1/innovation/generate', { ingredients })
}

/**
 * 获取创新菜谱详情（GET /v1/innovation/recipes/{id}）。
 * @param id 创新菜谱 ID
 * @returns 创新菜谱实体
 */
export function getInnovationRecipe(id: number): Promise<InnovationRecipe> {
  return apiClient.get(`/v1/innovation/recipes/${id}`)
}

/**
 * 采纳创新菜（POST /v1/innovation/recipes/{id}/adopt），入库「我的创新菜」。
 * @param id 创新菜谱 ID
 * @returns 采纳结果
 */
export function postInnovationAdopt(id: number): Promise<InnovationAdoptResponse> {
  return apiClient.post(`/v1/innovation/recipes/${id}/adopt`, {})
}

/**
 * 复用创新菜（POST /v1/innovation/recipes/{id}/reuse）：再次开做。
 * @param id 创新菜谱 ID
 * @returns 可复用标记 + 创新菜谱实体
 */
export function postInnovationReuse(id: number): Promise<InnovationReuseResponse> {
  return apiClient.post(`/v1/innovation/recipes/${id}/reuse`, {})
}

/**
 * 创新菜评分反馈（POST /v1/innovation/recipes/{id}/feedback）。
 * @param id 创新菜谱 ID
 * @param body 评分 1~5 与可选评论
 * @returns 无（提交成功）
 */
export function postInnovationFeedback(id: number, body: InnovationFeedbackBody): Promise<void> {
  return apiClient.post(`/v1/innovation/recipes/${id}/feedback`, body)
}

/* ── 图像识别 ── */

/**
 * 冰箱照片识别（POST /v1/vision/recognize，multipart 上传）。
 * request_id 由 axios 拦截器放入 X-Request-Id 头（FormData 体不注入 JSON 字段）。
 * @param file 图像文件（前端已压缩至 ≤1MB）
 * @returns 识别结果 + 剩余额度 + 降级标记
 */
export function postVisionRecognize(file: File): Promise<VisionRecognizeResponse> {
  const form = new FormData()
  form.append('file', file)
  return apiClient.post('/v1/vision/recognize', form, {
    headers: { 'Content-Type': 'multipart/form-data' },
  })
}

/**
 * 确认识别结果入库（POST /v1/vision/confirm）。
 * @param names 用户勾选确认的食材名列表
 * @returns 成功加入的食材数
 */
export function postVisionConfirm(names: string[]): Promise<VisionConfirmResponse> {
  return apiClient.post('/v1/vision/confirm', { names })
}

/* ── 烹饪求助 ── */

/**
 * 烹饪过程求助（POST /v1/cooking/sessions/{id}/help）。
 * 正常返回回答列表；命中风控返回 blocked 结构；429 为当日次数超限（由调用方按错误码处理）。
 * @param sessionId 烹饪会话 ID
 * @param question 求助问题
 * @returns 回答列表或拦截结构
 */
export function postCookingHelp(sessionId: string, question: string): Promise<CookingHelpOutcome> {
  return apiClient.post(`/v1/cooking/sessions/${sessionId}/help`, { question })
}
