/**
 * 文件职责：埋点采集与批量上报——缓冲队列 + 阈值/时间双触发 flush。
 * 事件名清单与 web-stage1 埋点口径逐字一致（38 个）；本端通过 postTrackEvents 上报。
 * 触发策略：
 * - 缓冲 ≥10 条 或 距上次 flush >15s 时，trackEvent 内自动触发 flush；
 * - 安全类三事件（safety_block / medical_refuse / innovation_blocked）立即 flush
 *   （合规举证优先，绝不与普通事件同批等待）；
 * - flush 失败一律静默丢弃缓冲：埋点永不阻断主流程（后端 /v1/track/events 本期
 *   未实现属预期，调用方无需感知）；
 * - 模块加载时不注册任何全局定时器（避免 App 级常驻）：页面 onHide 调 flushOnHide()
 *   或 trackEvent 内阈值触发兜底。
 */
import { postTrackEvents, type TrackEventPayload } from '@/api/endpoints'
import { generateRequestId } from '@/api/request'

/** 埋点事件名（与 web-stage1 38 个事件逐字一致，禁止新增/改名破坏口径） */
export type TrackEventName =
  | 'app_enter'
  | 'disclaimer_agree'
  | 'ingredient_manual_select'
  | 'ingredient_photo_upload'
  | 'ingredient_recognize_result'
  | 'ingredient_recognize_correct'
  | 'recommend_request'
  | 'recommend_impression'
  | 'recommend_click'
  | 'filtered_by_allergen'
  | 'recipe_detail_view'
  | 'cook_start'
  | 'cook_step_next'
  | 'cook_voice_command'
  | 'cook_help_request'
  | 'cook_complete'
  | 'cook_abandon'
  | 'cook_rating'
  | 'nutrition_view'
  | 'inventory_add'
  | 'inventory_expiring_click'
  | 'safety_block'
  | 'medical_refuse'
  | 'search_no_result'
  | 'subscribe_click'
  | 'purchase_success'
  | 'feedback_submit'
  | 'innovation_enter'
  | 'innovation_precheck'
  | 'innovation_blocked'
  | 'innovation_generate'
  | 'innovation_result'
  | 'innovation_reason_view'
  | 'innovation_adopt'
  | 'innovation_cook'
  | 'innovation_feedback'
  | 'innovation_index'
  | 'innovation_reuse'

/** 安全类事件集合：合规举证优先，立即 flush（不进普通批） */
export const SAFETY_EVENTS: readonly TrackEventName[] = ['safety_block', 'medical_refuse', 'innovation_blocked']

/** 缓冲上限（条）：达到即 flush */
const BUFFER_LIMIT = 10

/** 距上次 flush 的时间阈值（毫秒）：超过即 flush */
const FLUSH_INTERVAL_MS = 15000

/** 事件缓冲队列（模块级；flushOnHide / 阈值触发时整批取出上报） */
let buffer: TrackEventPayload[] = []

/** 上次 flush 尝试时间（毫秒时间戳；初始化为模块加载时刻，避免加载即误触发） */
let lastFlushAt = Date.now()

/**
 * 埋点通道不可用标记：上报接口返回 404（后端 /v1/track/events 本期未实现，文档 §11.3 #5）
 * 时置位，本会话内事件直接丢弃、不再发起请求——避免每次 flush 都产生 404 红色报错刷屏
 * （🔴 历史缺陷：曾反复 POST 404 刷屏控制台；接口就绪后新会话自动恢复上报，勿回退）。
 */
let channelUnavailable = false

/**
 * 记录一个埋点事件（进入缓冲；满足条件自动 flush）。
 * @param name 事件名（TrackEventName 枚举内）
 * @param props 事件属性（可选，结构随事件定义；不含个人信息由调用方保证）
 * @returns 无
 * @throws 不抛出（flush 为 fire-and-forget，内部静默）
 */
export function trackEvent(name: TrackEventName, props?: Record<string, unknown>): void {
  // 通道不可用（接口 404 已置位）：事件直接丢弃，不入缓冲防内存增长、不再触发请求
  if (channelUnavailable) return
  buffer.push({ name, props, ts: Date.now(), request_id: generateRequestId() })
  const isSafety = SAFETY_EVENTS.includes(name)
  const sizeFull = buffer.length >= BUFFER_LIMIT
  const stale = Date.now() - lastFlushAt > FLUSH_INTERVAL_MS
  if (isSafety || sizeFull || stale) {
    void flushTrack()
  }
}

/**
 * 将缓冲整批上报：取出全部事件调 postTrackEvents；任何失败静默丢弃（缓冲已清空）。
 * 上报返回 404（接口未实现）时置位 channelUnavailable，本会话停止后续上报。
 * @returns 成功 / 失败均 resolve（失败不抛出——埋点永不阻断主流程）
 * @throws 不抛出（postTrackEvents 异常被捕获吞掉）
 */
export async function flushTrack(): Promise<void> {
  if (buffer.length === 0) return
  if (channelUnavailable) {
    buffer.length = 0
    return
  }
  const events = buffer.splice(0, buffer.length)
  try {
    await postTrackEvents(events)
  } catch (err) {
    // 上报失败：网络类失败静默丢弃缓冲；404（接口本期未实现）置位不可用标记停止后续请求
    const code = (err as { code?: unknown } | null)?.code
    if (code === 404 || code === '404') channelUnavailable = true
  }
  // 无论成败都推进时间戳：失败不立即重试，避免失败风暴
  lastFlushAt = Date.now()
}

/**
 * 页面 onHide 钩子入口：离开页面时尽力上报残余缓冲。
 * @returns 无
 * @throws 不抛出
 */
export function flushOnHide(): void {
  void flushTrack()
}

/**
 * 重置模块内部状态（仅供单测使用：清空缓冲并重置时间戳）。
 * @returns 无
 * @throws 不抛出
 */
export function resetTrackStateForTest(): void {
  buffer = []
  lastFlushAt = Date.now()
  channelUnavailable = false
}
