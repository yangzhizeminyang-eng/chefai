/**
 * 文件职责：uni.request 封装——小程序端统一 HTTP 入口（对齐 web-stage1/src/api/index.ts 语义）。
 * - 头注入：每个请求携带 X-Request-Id（req_ + 时间戳 + 随机短串，幂等键同值）与
 *   X-Anonymous-Id（storage aicook_anonymous_id，存在才携带）；
 * - 来源标识：POST/PUT/PATCH/DELETE 的 JSON body 自动注入 request_id 幂等键与
 *   client_type: 'miniprogram'（后端 pydantic schema 以可选字段透传记录，extra 默认忽略，
 *   注入安全）；GET 在 query 注入 client_type（FastAPI 对未声明的 query 参数忽略，仅作来源记录）；
 * - 错误归一：fail → fromUniFailure（TIMEOUT / NETWORK 两态，文案与 web-stage1 一致）；
 *   非 2xx → { code: statusCode, message, detail? }（422 时页面用 format422Detail 解析 detail）；
 *   成功 2xx 直接 resolve res.data（uni.request 的 data 即响应 body）；
 * - 重试：仅 GET 在网络失败 / 超时 / 5xx 时自动重试 1 次（指数退避 600ms）；写操作绝不重试；
 * - PATCH 平台风险：wx.request 官方 method 白名单不含 PATCH。H5 端 XHR 原生支持；
 *   mp-weixin 端依赖基础库透传（未承诺）。本层请求时附加 X-HTTP-Method-Override: PATCH
 *   头作为覆写提示；若目标宿主实测拒绝 PATCH，需后端为对应路由补 POST 别名（本任务不动后端）；
 * - 不做全局请求锁：页面层用按钮 loading 防并发（与 web 端口径一致，避免排队语义歧义）。
 */
import { fromUniFailure } from '@shared/utils/apiError'
import type { ApiError } from '@shared/types'
import { get as storageGet, ANONYMOUS_ID_KEY } from '@/utils/storage'

/** 全局默认超时（毫秒）：小程序网络环境按 15s 留余量（web 端 12s） */
export const DEFAULT_TIMEOUT_MS = 15000

/** 冰箱照片识别专用超时（毫秒）：真实视觉模型 P95 延迟可达 15~20s */
export const RECOGNIZE_TIMEOUT_MS = 30000

/** 创新生成专用超时（毫秒）：后端 LLM 表达 25s 硬超时 + 模板降级兜底，60s 内必回响应 */
export const INNOVATION_TIMEOUT_MS = 60000

/** GET 网络类失败自动重试次数（不含首次） */
const GET_RETRY_TIMES = 1

/** GET 重试退避基础延迟（毫秒）：仅重试 1 次，固定 600ms（指数退避预留） */
const GET_RETRY_DELAY_MS = 600

/** client_type 来源标识（文档 §11.2：小程序端固定 miniprogram，后端仅透传记录） */
const CLIENT_TYPE = 'miniprogram'

/**
 * API 基础地址：优先读取构建注入的 VITE_API_BASE_URL（生产部署时由 CI 注入正式备案域名）；
 * 未注入时缺省直连本地后端（127.0.0.1:8000），保证 build:mp-weixin 产物开箱可联调。
 * 🔴 历史缺陷：曾以 MODE==='development' 区分，导致 build 产物走 https://api.example.com
 * 占位域名（ERR_NAME_NOT_RESOLVED，全部请求失败），勿回退。
 */
export const API_BASE_URL: string = import.meta.env.VITE_API_BASE_URL || 'http://127.0.0.1:8000'

/** 请求方法联合类型（本工程逻辑方法；PATCH 见下方平台兼容说明） */
export type RequestMethod = 'GET' | 'POST' | 'PUT' | 'DELETE' | 'PATCH'

/** uni.request 官方 method 白名单（不含 PATCH：wx.request 合法值为 OPTIONS/GET/HEAD/POST/PUT/DELETE/TRACE/CONNECT） */
type UniRequestMethod = 'OPTIONS' | 'GET' | 'HEAD' | 'POST' | 'PUT' | 'DELETE' | 'TRACE' | 'CONNECT'

/**
 * 请求选项（对齐 web-stage1 apiClient 调用面）。
 */
export interface RequestOptions {
  /** 接口路径（以 /v1 开头，自动拼接 API_BASE_URL） */
  url: string
  /** 请求方法，缺省 GET */
  method?: RequestMethod
  /** 请求体 / 查询参数（GET 时序列化为 query，其余为 JSON body；object 以兼容各接口契约类型） */
  data?: object
  /** 超时毫秒数，缺省 DEFAULT_TIMEOUT_MS */
  timeout?: number
  /** 额外请求头（与注入头合并，同名以调用方为准） */
  header?: Record<string, string>
}

/**
 * 生成幂等键：req_ + 36 进制时间戳 + 4 位随机短串（与 web-stage1 同构）。
 * @returns 形如 req_mXXXXXXabcd 的请求标识
 * @throws 不抛出
 */
export function generateRequestId(): string {
  const ts = Date.now().toString(36)
  const rand = Math.random().toString(36).slice(2, 6)
  return `req_${ts}${rand}`
}

/**
 * 把未知 reject 原因归一为 ApiError（防御第三方/原生层抛出非结构化错误）。
 * @param error reject 原因
 * @returns ApiError 结构（非对象原因按 NETWORK 兜底）
 * @throws 不抛出
 */
function toApiError(error: unknown): ApiError {
  if (error && typeof error === 'object' && 'code' in error && 'message' in error) {
    return error as ApiError
  }
  return { code: 'NETWORK', message: '网络连接不可用，请检查网络后重试' }
}

/**
 * 判断错误是否可重试（仅 GET 使用）：超时 / 网络不可用 / 5xx 可重试，4xx 业务错误不重试。
 * @param error 归一化错误
 * @returns 可重试返回 true
 * @throws 不抛出
 */
function isRetryable(error: ApiError): boolean {
  if (error.code === 'TIMEOUT' || error.code === 'NETWORK') return true
  return typeof error.code === 'number' && error.code >= 500
}

/**
 * 等待指定毫秒（重试退避用）。
 * @param ms 等待毫秒数
 * @returns 到时后 resolve
 * @throws 不抛出
 */
function delay(ms: number): Promise<void> {
  return new Promise((resolve) => {
    setTimeout(resolve, ms)
  })
}

/**
 * 核心请求函数：注入追踪头与来源标识、归一错误、GET 自动重试一次。
 * @param options 请求选项
 * @returns 成功时 resolve 响应 body（2xx）
 * @throws 归一化 ApiError（对象形式 reject：{ code, message, detail? }），超时为 TIMEOUT、网络不可用为 NETWORK
 */
export async function request<T>(options: RequestOptions): Promise<T> {
  const method: RequestMethod = options.method ?? 'GET'
  const rid = generateRequestId()

  // ── 追踪头：X-Request-Id 恒携带；X-Anonymous-Id 存在才携带（幂等键同值）──
  const header: Record<string, string> = { ...(options.header ?? {}), 'X-Request-Id': rid }
  const anonId = storageGet<string>(ANONYMOUS_ID_KEY, '')
  if (anonId) header['X-Anonymous-Id'] = anonId
  // PATCH 平台兼容提示：官方 method 白名单不含 PATCH，附加覆写头供网关/后端扩展识别
  // （H5 端 XHR 原生支持 PATCH；mp-weixin 端依赖基础库透传，若宿主拒绝需后端补 POST 别名）
  if (method === 'PATCH') header['X-HTTP-Method-Override'] = 'PATCH'

  // ── 数据注入：GET 注 query；写操作注 JSON body（request_id 幂等键 + client_type 来源）──
  const source = (options.data ?? {}) as Record<string, unknown>
  let data: Record<string, unknown> | undefined
  if (method === 'GET') {
    // 🔴 过滤 undefined/null 参数：uni.request 会把 undefined 值序列化为字面量 "key=undefined"
    //    （与 axios 默认跳过 null/undefined 不同），曾导致 category=undefined&q=undefined
    //    使后端按字面量查询、食材库/收藏/营养等全部带可选参数的 GET 返回空列表（历史缺陷，勿回退）。
    //    空字符串保留（对齐 axios 语义，q='' 表示显式空词查询）。
    const filtered: Record<string, unknown> = {}
    for (const key of Object.keys(source)) {
      const value = source[key]
      if (value !== undefined && value !== null) filtered[key] = value
    }
    data = { ...filtered, client_type: CLIENT_TYPE }
  } else {
    const body = { ...source }
    // 显式传入的非空 request_id 优先保留（幂等重试场景，对齐 web-stage1 拦截器顺序）
    if (!body.request_id) body.request_id = rid
    if (!body.client_type) body.client_type = CLIENT_TYPE
    data = body
  }

  /**
   * 单次发送（Promise 化 uni.request）。
   * @returns 2xx 时 resolve body
   * @throws 非 2xx / fail 时以 ApiError 对象 reject
   */
  const sendOnce = (): Promise<T> =>
    new Promise<T>((resolve, reject) => {
      try {
        uni.request({
          url: `${API_BASE_URL}${options.url}`,
          // PATCH 不在 uni 官方白名单：H5 XHR 原生支持；mp-weixin 依赖透传（风险已在文件头标注）
          method: method as UniRequestMethod,
          data,
          timeout: options.timeout ?? DEFAULT_TIMEOUT_MS,
          header,
          success: (res) => {
            const status = res.statusCode
            if (status >= 200 && status < 300) {
              resolve(res.data as T)
              return
            }
            // 非 2xx：取后端 message（422 detail 由页面用 format422Detail 解析），兜底状态码文案
            const payload =
              res.data && typeof res.data === 'object' ? (res.data as { message?: string; detail?: unknown }) : {}
            const detailText = typeof payload.detail === 'string' ? payload.detail : undefined
            const message = payload.message ?? detailText ?? `请求失败（${status}）`
            reject({ code: status, message, detail: payload.detail })
          },
          fail: (err) => {
            // 网络失败 / 超时：按 errMsg 归一（timeout → TIMEOUT，其余 → NETWORK）
            reject(fromUniFailure(err?.errMsg ?? ''))
          },
        })
      } catch (e) {
        // uni.request 同步异常（参数非法等极端场景）：按网络不可用兜底
        reject(fromUniFailure(''))
        void e
      }
    })

  // GET 网络类失败重试 1 次；写操作绝不重试（幂等键虽在，重复写语义不安全）
  const maxAttempts = method === 'GET' ? 1 + GET_RETRY_TIMES : 1
  let lastError: ApiError | undefined
  for (let attempt = 0; attempt < maxAttempts; attempt++) {
    if (attempt > 0) {
      // 指数退避：600ms（本次仅一次重试，系数预留）
      await delay(GET_RETRY_DELAY_MS * attempt)
    }
    try {
      return await sendOnce()
    } catch (e) {
      lastError = toApiError(e)
      if (method !== 'GET') throw lastError
      if (!isRetryable(lastError)) throw lastError
    }
  }
  // 循环必有 lastError（maxAttempts ≥ 1 且失败路径必然赋值）；此处断言兜底
  throw lastError ?? { code: 'NETWORK', message: '网络连接不可用，请检查网络后重试' }
}

/**
 * GET 便捷方法（query 注入 client_type，自动重试一次）。
 * @param url 接口路径
 * @param data 查询参数（可选）
 * @returns 响应 body
 * @throws 归一化 ApiError
 */
export function get<T>(url: string, data?: object): Promise<T> {
  return request<T>({ url, method: 'GET', data })
}

/**
 * POST 便捷方法（body 注入 request_id 与 client_type）。
 * @param url 接口路径
 * @param data JSON body（可选）
 * @param timeout 超时毫秒数（可选，长耗时接口如创新生成传 INNOVATION_TIMEOUT_MS）
 * @returns 响应 body
 * @throws 归一化 ApiError
 */
export function post<T>(url: string, data?: object, timeout?: number): Promise<T> {
  return request<T>({ url, method: 'POST', data, timeout })
}

/**
 * PUT 便捷方法（body 注入 request_id 与 client_type）。
 * @param url 接口路径
 * @param data JSON body（可选）
 * @returns 响应 body
 * @throws 归一化 ApiError
 */
export function put<T>(url: string, data?: object): Promise<T> {
  return request<T>({ url, method: 'PUT', data })
}

/**
 * PATCH 便捷方法（body 注入 request_id 与 client_type；烹饪会话/库存增量更新用）。
 * @param url 接口路径
 * @param data JSON body（可选）
 * @returns 响应 body
 * @throws 归一化 ApiError
 */
export function patch<T>(url: string, data?: object): Promise<T> {
  return request<T>({ url, method: 'PATCH', data })
}

/**
 * DELETE 便捷方法（写操作不重试）。
 * @param url 接口路径
 * @param data JSON body（可选，本工程 DELETE 均无 body）
 * @returns 响应 body（无实体接口由调用方以 void 接收）
 * @throws 归一化 ApiError
 */
export function del<T = void>(url: string, data?: object): Promise<T> {
  return request<T>({ url, method: 'DELETE', data })
}
