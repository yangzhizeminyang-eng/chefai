/**
 * 文件职责：后台管理端统一 API 模块（/admin/v1/** 契约封装）。
 * - 统一 axios 实例：baseURL 为 '/'，开发环境经 Vite 代理转发到本地 FastAPI 后端；
 * - 请求拦截器自动注入 Bearer Token（localStorage 键 aicook_admin_token）；
 * - 响应拦截器统一处理 401：清理登录态并跳转登录页；
 * - 导出全部后台接口函数与配套 TypeScript 类型，供各管理页面复用。
 */
import axios from 'axios'
import type { AxiosError, AxiosInstance, InternalAxiosRequestConfig } from 'axios'
import { ElMessage } from 'element-plus'

/** localStorage 键名：登录令牌 */
export const TOKEN_KEY = 'aicook_admin_token'
/** localStorage 键名：当前登录角色 */
export const ROLE_KEY = 'aicook_admin_role'
/** localStorage 键名：当前登录用户名 */
export const USERNAME_KEY = 'aicook_admin_username'

// ==================== 通用类型 ====================

/** 后台角色三级：超级管理员 / 内容运营 / 只读 */
export type AdminRole = 'super_admin' | 'content_ops' | 'readonly'

/** 角色中文标签映射（顶栏与成员权限展示用） */
export const ROLE_LABELS: Record<AdminRole, string> = {
  super_admin: '超级管理员',
  content_ops: '内容运营',
  readonly: '只读',
}

/** 登录接口返回体 */
export interface LoginResult {
  access_token: string
  token_type: string
  role: AdminRole
  username: string
}

/** 当前登录用户信息 */
export interface MeInfo {
  username: string
  role: AdminRole
}

/** 列表接口统一结果（兼容 {items,total} 与裸数组两种返回形态） */
export interface PageResult<T> {
  items: T[]
  total: number
}

/** 后端错误响应体（发布 422 / 导入失败等） */
export interface ApiErrorData {
  code?: string | number
  message?: string
  detail?: unknown
  errors?: ValidationErrorItem[]
}

/** 校验错误明细（逐条定位：行 / 字段 / 值 / 原因） */
export interface ValidationErrorItem {
  row?: number | string
  field?: string
  value?: unknown
  reason?: string
  message?: string
  [key: string]: unknown
}

// ==================== 成员权限 ====================

/** 管理员成员 */
export interface AdminUser {
  id: number
  username: string
  role: AdminRole
  status: 'active' | 'disabled'
  created_at?: string
}

/** 新增成员入参 */
export interface CreateAdminUserPayload {
  username: string
  password: string
  role: AdminRole
}

/** 编辑成员入参（角色 / 状态 / 重置密码） */
export interface UpdateAdminUserPayload {
  role?: AdminRole
  status?: 'active' | 'disabled'
  password?: string
}

// ==================== 菜谱 ====================

/** 菜谱状态：草稿 / 已发布 */
export type RecipeStatus = 'draft' | 'published'

/** 菜谱列表项 */
export interface RecipeListItem {
  id: number
  name: string
  status: RecipeStatus
  quantified: boolean
  updated_at?: string
}

/** 菜谱食材用量行 */
export interface RecipeIngredientRow {
  name: string
  amount: string
  unit?: string
}

/** 菜谱步骤行 */
export interface RecipeStepRow {
  order: number
  content: string
}

/** 菜谱详情（含食材 / 步骤全量） */
export interface RecipeDetail {
  id?: number
  name: string
  description?: string
  status?: RecipeStatus
  quantified?: boolean
  version?: number
  updated_at?: string
  ingredients: RecipeIngredientRow[]
  steps: RecipeStepRow[]
}

/** 菜谱新建 / 编辑入参 */
export interface RecipePayload {
  name: string
  description?: string
  ingredients: RecipeIngredientRow[]
  steps: RecipeStepRow[]
}

/** 批量导入结果 */
export interface RecipeImportResult {
  imported: number
  failed: number
  errors: ValidationErrorItem[]
}

/** 批量导入支持格式 */
export type ImportFormat = 'json' | 'csv' | 'md'

// ==================== 食材 ====================

/** 食材别名项（id 字段名以后端实际返回为准，二者取其一） */
export interface IngredientAlias {
  id?: number
  alias_id?: number
  alias: string
}

/** 食材 */
export interface Ingredient {
  id: number
  name: string
  category?: string
  allergen_codes: string[]
  verified: boolean
}

/** 食材新增 / 编辑入参 */
export interface IngredientPayload {
  name: string
  category?: string
  allergen_codes: string[]
  verified: boolean
}

// ==================== 营养 ====================

/** 营养数据（per100g），data_source 必填 */
export interface NutritionInfo {
  ingredient_id?: number
  kcal: number | null
  protein: number | null
  fat: number | null
  carb: number | null
  sodium: number | null
  data_source: string
}

// ==================== 风控 ====================

/** 风控规则 */
export interface RiskRule {
  id: number
  rule_type: string
  pattern: string
  message_id?: string
  enabled: boolean
  created_at?: string
  updated_at?: string
}

/** 风控规则新增 / 编辑入参 */
export interface RiskRulePayload {
  rule_type: string
  pattern: string
  message_id?: string
  enabled: boolean
}

// ==================== 违禁词 ====================

/** 违禁词 */
export interface SensitiveWord {
  id: number
  word: string
  created_at?: string
}

// ==================== Agent 日志 ====================

/** Agent 调用日志（脱敏展示 user_id_hash） */
export interface TraceLogItem {
  id: number | string
  created_at?: string
  user_id_hash?: string
  node_name?: string
  status?: string
  rule_hit?: string | null
  duration_ms?: number | null
  nodes?: unknown
  [key: string]: unknown
}

// ==================== 操作日志 ====================

/** 操作日志（前后快照对比，只读展示） */
export interface OperationLog {
  id: number | string
  module: string
  action: string
  operator: string
  before_snapshot?: unknown
  after_snapshot?: unknown
  ip?: string
  created_at?: string
}

// ==================== 反馈工单 ====================

/** 反馈工单状态：待处理 / 处理中 / 已解决 */
export type FeedbackStatus = 'pending' | 'processing' | 'resolved'

/** 反馈工单 */
export interface FeedbackTicket {
  id: number | string
  status: FeedbackStatus
  content: string
  type?: string
  user_id_hash?: string
  created_at?: string
}

// ==================== 看板 ====================

/** 成本看板按日数据 */
export interface CostDay {
  date: string
  tokens: number
  cost_cents: number
  requests: number
}

/** 规则命中统计 */
export interface RiskRuleStat {
  rule_id: string
  count: number
}

/** 风控告警按日数据 */
export interface RiskDay {
  date: string
  total: number
  blocked: number
  by_rule: RiskRuleStat[]
}

// ==================== 远程开关 ====================

/** 五大远程开关状态 */
export interface SwitchesState {
  recommend: boolean
  vision: boolean
  qa: boolean
  payment: boolean
  innovation: boolean
}

/** 开关兜底默认值（后端字段缺失时使用） */
export const SWITCH_DEFAULTS: SwitchesState = {
  recommend: true,
  vision: true,
  qa: true,
  payment: true,
  innovation: true,
}

// ==================== 订单 ====================

/** 订单项（补发权益用） */
export interface OrderItem {
  order_no: string
  status: string
  amount_cents?: number | null
  user_id_hash?: string
  created_at?: string
}

// ==================== 创新中心 ====================

/** 搭配关系三选：协同 / 冲突 / 替代 */
export type PairingRelation = 'pair' | 'conflict' | 'replace'

/** 创新搭配规则 */
export interface InnovationRule {
  id: number
  ingredient_a: string
  ingredient_b: string
  relation: PairingRelation
  weight: number
  signed_by_expert: boolean
  created_at?: string
}

/** 创新搭配规则新增 / 编辑入参 */
export interface InnovationRulePayload {
  ingredient_a: string
  ingredient_b: string
  relation: PairingRelation
  weight: number
  signed_by_expert: boolean
}

/** 创新菜（巡检 / 下架管理对象） */
export interface InnovationRecipe {
  id: number
  name: string
  status: string
  created_at?: string
  last_inspected_at?: string
}

// ==================== axios 实例与拦截器 ====================

/** 统一 axios 实例：相对路径请求，开发环境经 Vite 代理转发后端 */
const instance: AxiosInstance = axios.create({
  baseURL: '/',
  timeout: 20000,
})

// 请求拦截器：注入 Bearer Token
instance.interceptors.request.use((config: InternalAxiosRequestConfig) => {
  const token = localStorage.getItem(TOKEN_KEY)
  if (token) {
    config.headers.Authorization = `Bearer ${token}`
  }
  return config
})

// 响应拦截器：401 统一清理登录态并跳转登录页
instance.interceptors.response.use(
  (response) => response,
  (error: AxiosError<ApiErrorData>) => {
    if (error.response?.status === 401) {
      localStorage.removeItem(TOKEN_KEY)
      localStorage.removeItem(ROLE_KEY)
      localStorage.removeItem(USERNAME_KEY)
      if (!window.location.pathname.startsWith('/login')) {
        ElMessage.error('登录已过期，请重新登录')
        window.location.href = '/login'
      }
    }
    return Promise.reject(error)
  },
)

// ==================== 请求封装与错误归一 ====================

/**
 * GET 请求封装。
 * @param url 请求地址
 * @param params 查询参数（undefined 字段会被 axios 忽略）
 * @returns 后端返回数据
 */
async function requestGet<T>(url: string, params?: Record<string, unknown>): Promise<T> {
  const resp = await instance.get<unknown>(url, { params })
  return resp.data as T
}

/**
 * POST 请求封装。
 * @param url 请求地址
 * @param data 请求体
 * @returns 后端返回数据
 */
async function requestPost<T>(url: string, data?: unknown): Promise<T> {
  const resp = await instance.post<unknown>(url, data)
  return resp.data as T
}

/**
 * PUT 请求封装。
 * @param url 请求地址
 * @param data 请求体
 * @returns 后端返回数据
 */
async function requestPut<T>(url: string, data?: unknown): Promise<T> {
  const resp = await instance.put<unknown>(url, data)
  return resp.data as T
}

/**
 * DELETE 请求封装。
 * @param url 请求地址
 * @returns 后端返回数据
 */
async function requestDelete<T>(url: string): Promise<T> {
  const resp = await instance.delete<unknown>(url)
  return resp.data as T
}

/**
 * 将后端返回归一化为 {items,total} 分页结构（兼容数组 / {items,total} / {list,total} 等形态）。
 * @param data 后端原始返回
 * @returns 归一化后的分页结果
 */
export function unwrapPage<T>(data: unknown): PageResult<T> {
  if (Array.isArray(data)) {
    return { items: data as T[], total: data.length }
  }
  if (data && typeof data === 'object') {
    const obj = data as Record<string, unknown>
    const rawItems = obj.items ?? obj.list ?? obj.data ?? obj.results
    if (Array.isArray(rawItems)) {
      return {
        items: rawItems as T[],
        total: typeof obj.total === 'number' ? obj.total : rawItems.length,
      }
    }
  }
  return { items: [], total: 0 }
}

/**
 * 将后端返回归一化为数组（别名等非分页列表接口）。
 * @param data 后端原始返回
 * @returns 数组；无法识别时为空数组
 */
export function unwrapArray<T>(data: unknown): T[] {
  if (Array.isArray(data)) return data as T[]
  if (data && typeof data === 'object') {
    const items = (data as Record<string, unknown>).items
    if (Array.isArray(items)) return items as T[]
  }
  return []
}

/**
 * 提取错误对应的 HTTP 状态码（用于区分 404 等特殊场景）。
 * @param error 任意抛出的错误对象
 * @returns HTTP 状态码；非 axios 错误返回 null
 */
export function getApiStatus(error: unknown): number | null {
  if (axios.isAxiosError(error)) {
    return error.response?.status ?? null
  }
  return null
}

/**
 * 错误信息归一化：优先取后端 message，其次 detail，按状态码兜底。
 * @param error 抛出的错误
 * @param fallback 无法解析时的兜底文案
 * @returns 可展示给用户的错误文案
 */
export function getErrorMessage(error: unknown, fallback = '请求失败，请稍后重试'): string {
  if (axios.isAxiosError<ApiErrorData>(error)) {
    const status = error.response?.status
    const data = error.response?.data
    if (status === 401) return '登录已过期，请重新登录'
    if (status === 403) return data?.message ?? '当前角色无权限执行该操作'
    if (data?.message) return data.message
    if (typeof data?.detail === 'string') return data.detail
    if (status === 404) return '请求的资源不存在'
    return fallback
  }
  if (error instanceof Error) return error.message
  return fallback
}

/**
 * 统一以 ElMessage.error 展示后端错误（写操作失败提示归一出口）。
 * @param error 抛出的错误
 * @param fallback 兜底文案
 */
export function notifyApiError(error: unknown, fallback = '请求失败，请稍后重试'): void {
  ElMessage.error(getErrorMessage(error, fallback))
}

/**
 * 提取后端校验错误明细（发布 422 / 导入失败等 errors 数组）。
 * @param error 抛出的错误
 * @returns 校验错误数组；无明细时返回空数组
 */
export function getValidationErrors(error: unknown): ValidationErrorItem[] {
  if (axios.isAxiosError<ApiErrorData>(error)) {
    const errors = error.response?.data?.errors
    if (Array.isArray(errors)) return errors
  }
  return []
}

// ==================== 鉴权 ====================

/**
 * 管理员登录。
 * @param payload 用户名与密码
 * @returns 令牌与角色信息
 */
export async function login(payload: { username: string; password: string }): Promise<LoginResult> {
  return requestPost<LoginResult>('/admin/v1/auth/login', payload)
}

/**
 * 获取当前登录用户信息。
 * @returns 用户名与角色
 */
export async function fetchMe(): Promise<MeInfo> {
  return requestGet<MeInfo>('/admin/v1/auth/me')
}

// ==================== 成员权限 ====================

/**
 * 获取管理员成员列表。
 * @returns 分页成员列表
 */
export async function listAdminUsers(): Promise<PageResult<AdminUser>> {
  return unwrapPage<AdminUser>(await requestGet<unknown>('/admin/v1/admin-users'))
}

/**
 * 新增管理员成员。
 * @param payload 用户名 / 初始密码 / 角色
 * @returns 新增后的成员
 */
export async function createAdminUser(payload: CreateAdminUserPayload): Promise<AdminUser> {
  return requestPost<AdminUser>('/admin/v1/admin-users', payload)
}

/**
 * 编辑管理员成员（角色 / 状态 / 重置密码）。
 * @param id 成员 ID
 * @param payload 变更字段（password 缺省表示不重置密码）
 * @returns 更新后的成员
 */
export async function updateAdminUser(id: number, payload: UpdateAdminUserPayload): Promise<AdminUser> {
  return requestPut<AdminUser>(`/admin/v1/admin-users/${id}`, payload)
}

// ==================== 菜谱 ====================

/**
 * 分页检索菜谱。
 * @param params 关键词 / 状态 / 页码 / 页大小
 * @returns 分页菜谱列表
 */
export async function listRecipes(params: {
  keyword?: string
  status?: string
  page?: number
  size?: number
}): Promise<PageResult<RecipeListItem>> {
  return unwrapPage<RecipeListItem>(await requestGet<unknown>('/admin/v1/recipes', params))
}

/**
 * 获取菜谱详情（含食材 / 步骤全量）。
 * @param id 菜谱 ID
 * @returns 菜谱详情
 */
export async function getRecipe(id: number): Promise<RecipeDetail> {
  return requestGet<RecipeDetail>(`/admin/v1/recipes/${id}`)
}

/**
 * 新建菜谱。
 * @param payload 基本信息 + 食材用量 + 步骤
 * @returns 创建后的菜谱详情
 */
export async function createRecipe(payload: RecipePayload): Promise<RecipeDetail> {
  return requestPost<RecipeDetail>('/admin/v1/recipes', payload)
}

/**
 * 编辑菜谱。
 * @param id 菜谱 ID
 * @param payload 基本信息 + 食材用量 + 步骤
 * @returns 更新后的菜谱详情
 */
export async function updateRecipe(id: number, payload: RecipePayload): Promise<RecipeDetail> {
  return requestPut<RecipeDetail>(`/admin/v1/recipes/${id}`, payload)
}

/**
 * 发布菜谱（后端做量化校验，422 返回逐条 errors）。
 * @param id 菜谱 ID
 */
export async function publishRecipe(id: number): Promise<void> {
  await requestPost<unknown>(`/admin/v1/recipes/${id}/publish`)
}

/**
 * 下架菜谱。
 * @param id 菜谱 ID
 */
export async function unpublishRecipe(id: number): Promise<void> {
  await requestPost<unknown>(`/admin/v1/recipes/${id}/unpublish`)
}

/**
 * 菜谱版本回滚。
 * @param id 菜谱 ID
 * @param toVersion 目标版本号
 */
export async function rollbackRecipe(id: number, toVersion: number): Promise<void> {
  await requestPost<unknown>(`/admin/v1/recipes/${id}/rollback`, { to_version: toVersion })
}

/**
 * 菜谱批量导入（multipart 文件上传）。
 * @param file 上传文件
 * @param format 文件格式：json / csv / md
 * @returns 导入结果（成功数 / 失败数 / 错误明细）
 */
export async function importRecipes(file: File, format: ImportFormat): Promise<RecipeImportResult> {
  const form = new FormData()
  form.append('file', file)
  form.append('format', format)
  const resp = await instance.post<unknown>('/admin/v1/recipes/batch-import', form)
  const data = (resp.data ?? {}) as Record<string, unknown>
  return {
    imported: Number(data.imported ?? 0),
    failed: Number(data.failed ?? 0),
    errors: Array.isArray(data.errors) ? (data.errors as ValidationErrorItem[]) : [],
  }
}

// ==================== 食材 ====================

/**
 * 检索食材列表。
 * @param params 关键词 / 页码 / 页大小（可选）
 * @returns 分页食材列表
 */
export async function listIngredients(params?: {
  keyword?: string
  page?: number
  size?: number
}): Promise<PageResult<Ingredient>> {
  return unwrapPage<Ingredient>(await requestGet<unknown>('/admin/v1/ingredients', params))
}

/**
 * 新增食材。
 * @param payload 名称 / 分类 / 致敏原 / 认证标记
 * @returns 新增后的食材
 */
export async function createIngredient(payload: IngredientPayload): Promise<Ingredient> {
  return requestPost<Ingredient>('/admin/v1/ingredients', payload)
}

/**
 * 编辑食材。
 * @param id 食材 ID
 * @param payload 名称 / 分类 / 致敏原 / 认证标记
 * @returns 更新后的食材
 */
export async function updateIngredient(id: number, payload: IngredientPayload): Promise<Ingredient> {
  return requestPut<Ingredient>(`/admin/v1/ingredients/${id}`, payload)
}

/**
 * 删除食材。
 * @param id 食材 ID
 */
export async function deleteIngredient(id: number): Promise<void> {
  await requestDelete<unknown>(`/admin/v1/ingredients/${id}`)
}

/**
 * 获取食材别名列表。
 * @param ingredientId 食材 ID
 * @returns 别名数组
 */
export async function listAliases(ingredientId: number): Promise<IngredientAlias[]> {
  return unwrapArray<IngredientAlias>(await requestGet<unknown>(`/admin/v1/ingredients/${ingredientId}/aliases`))
}

/**
 * 新增食材别名。
 * @param ingredientId 食材 ID
 * @param alias 别名
 */
export async function addAlias(ingredientId: number, alias: string): Promise<void> {
  await requestPost<unknown>(`/admin/v1/ingredients/${ingredientId}/aliases`, { alias })
}

/**
 * 删除食材别名。
 * @param ingredientId 食材 ID
 * @param aliasId 别名 ID
 */
export async function deleteAlias(ingredientId: number, aliasId: number): Promise<void> {
  await requestDelete<unknown>(`/admin/v1/ingredients/${ingredientId}/aliases/${aliasId}`)
}

// ==================== 营养 ====================

/**
 * 获取食材营养数据（未录入时后端可能返回 404，调用方按需兜底）。
 * @param ingredientId 食材 ID
 * @returns 营养数据（per100g）
 */
export async function getNutrition(ingredientId: number): Promise<NutritionInfo> {
  return requestGet<NutritionInfo>(`/admin/v1/nutrition/${ingredientId}`)
}

/**
 * 保存食材营养数据（data_source 必填，前端已做校验）。
 * @param ingredientId 食材 ID
 * @param payload 营养字段 + 数据来源
 */
export async function updateNutrition(ingredientId: number, payload: NutritionInfo): Promise<void> {
  await requestPut<unknown>(`/admin/v1/nutrition/${ingredientId}`, payload)
}

// ==================== 风控规则 ====================

/**
 * 获取风控规则列表。
 * @returns 分页规则列表
 */
export async function listRiskRules(): Promise<PageResult<RiskRule>> {
  return unwrapPage<RiskRule>(await requestGet<unknown>('/admin/v1/risk-rules'))
}

/**
 * 新增风控规则。
 * @param payload 类型 / 模式 / 提示消息 / 启用标记
 * @returns 新增后的规则
 */
export async function createRiskRule(payload: RiskRulePayload): Promise<RiskRule> {
  return requestPost<RiskRule>('/admin/v1/risk-rules', payload)
}

/**
 * 编辑风控规则。
 * @param id 规则 ID
 * @param payload 类型 / 模式 / 提示消息 / 启用标记
 * @returns 更新后的规则
 */
export async function updateRiskRule(id: number, payload: RiskRulePayload): Promise<RiskRule> {
  return requestPut<RiskRule>(`/admin/v1/risk-rules/${id}`, payload)
}

/**
 * 启停风控规则。
 * @param id 规则 ID
 */
export async function toggleRiskRule(id: number): Promise<void> {
  await requestPost<unknown>(`/admin/v1/risk-rules/${id}/toggle`)
}

/**
 * 按操作日志回滚风控规则（应用该日志的 before_snapshot）。
 * @param logId 操作日志 ID
 */
export async function rollbackRiskRules(logId: number | string): Promise<void> {
  await requestPost<unknown>('/admin/v1/risk-rules/rollback', { log_id: logId })
}

// ==================== 违禁词 ====================

/**
 * 获取违禁词列表。
 * @returns 分页违禁词列表
 */
export async function listSensitiveWords(): Promise<PageResult<SensitiveWord>> {
  return unwrapPage<SensitiveWord>(await requestGet<unknown>('/admin/v1/sensitive-words'))
}

/**
 * 新增违禁词。
 * @param payload 词内容
 * @returns 新增后的违禁词
 */
export async function createSensitiveWord(payload: { word: string }): Promise<SensitiveWord> {
  return requestPost<SensitiveWord>('/admin/v1/sensitive-words', payload)
}

/**
 * 编辑违禁词。
 * @param id 违禁词 ID
 * @param payload 词内容
 * @returns 更新后的违禁词
 */
export async function updateSensitiveWord(id: number, payload: { word: string }): Promise<SensitiveWord> {
  return requestPut<SensitiveWord>(`/admin/v1/sensitive-words/${id}`, payload)
}

/**
 * 删除违禁词。
 * @param id 违禁词 ID
 */
export async function deleteSensitiveWord(id: number): Promise<void> {
  await requestDelete<unknown>(`/admin/v1/sensitive-words/${id}`)
}

// ==================== Agent 日志 ====================

/**
 * 四维检索 Agent 调用日志（时间范围 / 节点 / 状态 / 规则命中）。
 * @param params 检索条件 + 分页
 * @returns 分页日志列表
 */
export async function listTraceLogs(params: {
  start?: string
  end?: string
  node_name?: string
  status?: string
  rule_hit?: string
  page?: number
  size?: number
}): Promise<PageResult<TraceLogItem>> {
  return unwrapPage<TraceLogItem>(await requestGet<unknown>('/admin/v1/trace-logs', params))
}

// ==================== 操作日志 ====================

/**
 * 分页获取操作日志（自动产生，只读展示）。
 * @param params 页码 / 页大小
 * @returns 分页操作日志
 */
export async function listOperationLogs(params?: { page?: number; size?: number }): Promise<PageResult<OperationLog>> {
  return unwrapPage<OperationLog>(await requestGet<unknown>('/admin/v1/operation-logs', params))
}

// ==================== 反馈工单 ====================

/**
 * 按状态获取反馈工单列表。
 * @param params 状态（可缺省查全部）
 * @returns 分页工单列表
 */
export async function listFeedbacks(params?: { status?: string }): Promise<PageResult<FeedbackTicket>> {
  return unwrapPage<FeedbackTicket>(await requestGet<unknown>('/admin/v1/feedbacks', params))
}

/**
 * 反馈工单流转：start（pending→processing）或 resolve（processing→resolved）。
 * @param id 工单 ID
 * @param action 流转动作
 */
export async function transitionFeedback(id: number | string, action: 'start' | 'resolve'): Promise<void> {
  await requestPost<unknown>(`/admin/v1/feedbacks/${id}/transition`, { action })
}

// ==================== 看板 ====================

/**
 * 获取成本看板（按日 token / 费用 / 请求数）。
 * @returns 按日数据数组
 */
export async function getDashboardCost(): Promise<{ days: CostDay[] }> {
  const data = await requestGet<unknown>('/admin/v1/dashboard/cost')
  const days = (data as { days?: unknown })?.days
  return { days: Array.isArray(days) ? (days as CostDay[]) : [] }
}

/**
 * 获取风控告警看板（按日拦截数与规则命中分布）。
 * @returns 按日数据数组
 */
export async function getDashboardRisk(): Promise<{ days: RiskDay[] }> {
  const data = await requestGet<unknown>('/admin/v1/dashboard/risk')
  const days = (data as { days?: unknown })?.days
  return { days: Array.isArray(days) ? (days as RiskDay[]) : [] }
}

// ==================== 远程开关 ====================

/**
 * 获取远程开关状态（字段缺失时以默认值兜底）。
 * @returns 五大开关状态
 */
export async function getSwitches(): Promise<SwitchesState> {
  const data = (await requestGet<unknown>('/admin/v1/config/switches')) as { switches?: Partial<SwitchesState> } | undefined
  return { ...SWITCH_DEFAULTS, ...(data?.switches ?? {}) }
}

/**
 * 保存远程开关状态。
 * @param switches 完整开关状态
 * @returns 保存后的开关状态
 */
export async function updateSwitches(switches: SwitchesState): Promise<SwitchesState> {
  const data = await requestPut<unknown>('/admin/v1/config/switches', { switches })
  const inner = (data as { switches?: Partial<SwitchesState> } | undefined)?.switches
  return { ...SWITCH_DEFAULTS, ...(inner ?? {}) }
}

/**
 * 一键回滚远程开关（恢复上一份快照）。
 */
export async function rollbackSwitches(): Promise<void> {
  await requestPost<unknown>('/admin/v1/config/switches/rollback')
}

// ==================== 订单 ====================

/**
 * 按状态获取订单列表。
 * @param params 状态（可缺省查全部）
 * @returns 分页订单列表
 */
export async function listOrders(params?: { status?: string }): Promise<PageResult<OrderItem>> {
  return unwrapPage<OrderItem>(await requestGet<unknown>('/admin/v1/orders', params))
}

/**
 * 人工修正补发订单权益。
 * @param orderNo 订单号
 * @param reason 补发原因（必填）
 */
export async function compensateOrder(orderNo: string, reason: string): Promise<void> {
  await requestPost<unknown>(`/admin/v1/orders/${orderNo}/compensate`, { reason })
}

// ==================== 创新中心 ====================

/**
 * 获取创新搭配规则列表。
 * @returns 分页规则列表
 */
export async function listInnovationRules(): Promise<PageResult<InnovationRule>> {
  return unwrapPage<InnovationRule>(await requestGet<unknown>('/admin/v1/innovation/rules'))
}

/**
 * 新增创新搭配规则。
 * @param payload 食材对 / 关系 / 权重 / 专家签字标记
 * @returns 新增后的规则
 */
export async function createInnovationRule(payload: InnovationRulePayload): Promise<InnovationRule> {
  return requestPost<InnovationRule>('/admin/v1/innovation/rules', payload)
}

/**
 * 编辑创新搭配规则。
 * @param id 规则 ID
 * @param payload 食材对 / 关系 / 权重 / 专家签字标记
 * @returns 更新后的规则
 */
export async function updateInnovationRule(id: number, payload: InnovationRulePayload): Promise<InnovationRule> {
  return requestPut<InnovationRule>(`/admin/v1/innovation/rules/${id}`, payload)
}

/**
 * 删除创新搭配规则。
 * @param id 规则 ID
 */
export async function deleteInnovationRule(id: number): Promise<void> {
  await requestDelete<unknown>(`/admin/v1/innovation/rules/${id}`)
}

/**
 * 获取创新菜列表。
 * @param params 状态筛选（可缺省查全部）
 * @returns 分页创新菜列表
 */
export async function listInnovationRecipes(params?: { status?: string }): Promise<PageResult<InnovationRecipe>> {
  return unwrapPage<InnovationRecipe>(await requestGet<unknown>('/admin/v1/innovation/recipes', params))
}

/**
 * 对创新菜执行巡检。
 * @param id 创新菜 ID
 * @returns 巡检结果（结构以后端为准，前端 JSON 展示）
 */
export async function inspectInnovationRecipe(id: number): Promise<unknown> {
  return requestPost<unknown>(`/admin/v1/innovation/recipes/${id}/inspect`)
}

/**
 * 下架创新菜（status → removed）。
 * @param id 创新菜 ID
 */
export async function removeInnovationRecipe(id: number): Promise<void> {
  await requestPost<unknown>(`/admin/v1/innovation/recipes/${id}/remove`)
}
