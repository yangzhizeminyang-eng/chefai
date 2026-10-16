/**
 * 文件职责：axios 实例与拦截器封装。
 * - 请求拦截器：为 POST 请求自动生成 request_id（req_ + 时间戳 + 随机短串，已带则不覆盖），
 *   并统一携带 X-Anonymous-Id（匿名会话）与 X-Request-Id（链路追踪）请求头；
 * - 响应拦截器：将 HTTP/网络错误归一为 { code, message } 结构抛出，
 *   超时与网络不可用给出固定中文提示。
 * - 按请求超时覆盖（P1 DEF-01）：本模块导出的 apiClient 即 axios 实例，
 *   请求方法天然透传第三参 config（如 apiClient.post(url, data, { timeout })），
 *   per-request timeout 会覆盖实例默认超时；未覆盖时走 DEFAULT_TIMEOUT_MS（12s）。
 *   长耗时接口（如创新生成 LLM 表达 10–30s）应显式传更大的 timeout。
 */
import axios, { type AxiosError, type AxiosInstance, type InternalAxiosRequestConfig } from 'axios'
import type { ApiError } from './types'

/** 全局默认超时（毫秒）：普通请求口径不变 */
export const DEFAULT_TIMEOUT_MS = 12000

/** 创新生成专用超时（毫秒）：后端 LLM 表达带 25s 硬超时 + 模板降级兜底，60s 内必回响应 */
export const INNOVATION_GENERATE_TIMEOUT_MS = 60000

/** 携带自定义头的请求配置类型（扩展 InternalAxiosRequestConfig） */
interface RequestConfigWithHeaders extends InternalAxiosRequestConfig {
  /** 标记该请求是否已生成 request_id（防止重试时重复生成） */
  _hasRequestId?: boolean
}

/** 生成幂等键：req_ + 时间戳 + 4 位随机短串 */
function generateRequestId(): string {
  const ts = Date.now().toString(36)
  const rand = Math.random().toString(36).slice(2, 6)
  return `req_${ts}${rand}`
}

/** 读取 localStorage 中的匿名 ID（无则返回空串，由 session store 懒获取） */
function getAnonymousId(): string {
  try {
    return localStorage.getItem('aicook_anonymous_id') ?? ''
  } catch {
    return ''
  }
}

/** 用户登录 token 持久化键（auth store 与本模块共用） */
export const USER_TOKEN_KEY = 'aicook_user_token'

/** 读取 localStorage 中的登录 token（未登录返回空串） */
export function getUserToken(): string {
  try {
    return localStorage.getItem(USER_TOKEN_KEY) ?? ''
  } catch {
    return ''
  }
}

/** 创建并配置 axios 实例（含拦截器装配） */
function createApiClient(): AxiosInstance {
  const client = axios.create({
    // 统一走相对路径，由 vite 代理转发到 http://localhost:8000
    baseURL: '/',
    // 默认超时 12s：可被单个请求的 config.timeout 覆盖（见文件头「按请求超时覆盖」）；
    // 超时统一归一为「加载超时，请重试」
    timeout: DEFAULT_TIMEOUT_MS,
  })

  // ── 请求拦截器：request_id + 匿名头 ──
  client.interceptors.request.use((config: RequestConfigWithHeaders) => {
    // 仅 POST 需要幂等键（GET 幂等天然成立）
    if (config.method?.toLowerCase() === 'post' && !config._hasRequestId) {
      const rid = generateRequestId()
      config._hasRequestId = true
      // 请求体为 JSON 时注入 request_id；FormData 等场景仅放请求头。
      // 注意顺序：显式传入的非空 request_id 优先保留（幂等重试场景）；
      // 调用方用空串占位（如 recommend store）时注入生成的 rid，避免 spread 覆盖导致幂等键断链。
      if (config.data && typeof config.data === 'object' && !(config.data instanceof FormData)) {
        const body = config.data as Record<string, unknown>
        config.data = { ...body, request_id: (body.request_id as string) || rid }
      }
      config.headers.set('X-Request-Id', rid)
    } else if (config.headers.get('X-Request-Id')) {
      // 已显式传入 X-Request-Id（如 trace 查询），保持不动
    }
    // 匿名会话头（存在才携带）
    const anonId = getAnonymousId()
    if (anonId) {
      config.headers.set('X-Anonymous-Id', anonId)
    }
    // 登录态（JWT）：存在即携带，后端 JWT 优先于匿名头解析身份
    const token = getUserToken()
    if (token) {
      config.headers.set('Authorization', `Bearer ${token}`)
    }
    return config
  })

  // ── 响应拦截器：成功直接返回 data；失败归一为 ApiError ──
  client.interceptors.response.use(
    (response) => response.data,
    (error: AxiosError) => {
      const apiError: ApiError = normalizeError(error)
      return Promise.reject(apiError)
    },
  )

  return client
}

/**
 * 将 axios 错误归一为统一的 { code, message } 结构。
 * @param error axios 捕获的原始错误
 * @returns 归一化后的 ApiError
 */
function normalizeError(error: AxiosError): ApiError {
  // 请求已发出但后端返回了非 2xx 状态码
  if (error.response) {
    const status = error.response.status
    const payload = error.response.data as { message?: string; detail?: string } | undefined
    const msg = payload?.message ?? payload?.detail ?? `请求失败（${status}）`
    // 透传后端原始 detail（422 校验错误时由 format422Detail 解析为可读文案）
    return { code: status, message: msg, detail: payload?.detail }
  }
  // 请求已发出但未收到响应：区分超时与网络不可用
  if (error.code === 'ECONNABORTED' || error.message.includes('timeout')) {
    return { code: 'TIMEOUT', message: '加载超时，请重试' }
  }
  return { code: 'NETWORK', message: '网络连接不可用，请检查网络后重试' }
}

/** 全局唯一 axios 实例（模块级单例） */
const apiClient = createApiClient()

export default apiClient
