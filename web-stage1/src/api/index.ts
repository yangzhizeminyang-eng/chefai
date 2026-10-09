/**
 * 文件职责：axios 实例与拦截器封装。
 * - 请求拦截器：为 POST 请求自动生成 request_id（req_ + 时间戳 + 随机短串，已带则不覆盖），
 *   并统一携带 X-Anonymous-Id（匿名会话）与 X-Request-Id（链路追踪）请求头；
 * - 响应拦截器：将 HTTP/网络错误归一为 { code, message } 结构抛出，
 *   超时（>12s）与网络不可用给出固定中文提示。
 */
import axios, { type AxiosError, type AxiosInstance, type InternalAxiosRequestConfig } from 'axios'
import type { ApiError } from './types'

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

/** 创建并配置 axios 实例（含拦截器装配） */
function createApiClient(): AxiosInstance {
  const client = axios.create({
    // 统一走相对路径，由 vite 代理转发到 http://localhost:8000
    baseURL: '/',
    // 超时 12s：超时归一为「加载超时，请重试」
    timeout: 12000,
  })

  // ── 请求拦截器：request_id + 匿名头 ──
  client.interceptors.request.use((config: RequestConfigWithHeaders) => {
    // 仅 POST 需要幂等键（GET 幂等天然成立）
    if (config.method?.toLowerCase() === 'post' && !config._hasRequestId) {
      const rid = generateRequestId()
      config._hasRequestId = true
      // 请求体为 JSON 时注入 request_id；FormData 等场景仅放请求头
      if (config.data && typeof config.data === 'object' && !(config.data instanceof FormData)) {
        config.data = { request_id: rid, ...config.data }
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
    return { code: status, message: msg }
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
