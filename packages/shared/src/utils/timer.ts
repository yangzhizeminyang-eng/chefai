/**
 * 文件职责：多路计时器工具（Task 9 / W-04 烹饪引导页「并行倒计时」数据源）。
 * - MultiTimer 管理多条并行倒计时（如「焖 8 分钟」与「焯 2 分钟」同时跑）；
 * - 每路计时独立 start / pause / resume / reset / clear，支持 once 与循环（repeat）；
 * - 以 1s 心跳（setInterval 单例）驱动全部计时递减，无活动计时器时自动停表；
 * - 状态变化（tick / finish / add / clear）通过 onChange 回调广播，供 UI 订阅刷新。
 * 纯 TypeScript 实现，无 Vue / DOM 依赖（仅 setTimeout/setInterval 计时器 API），
 * 可被 vitest 在 node 环境用 vi.useFakeTimers 直接单测。
 * 从 web-stage1/src/utils/timer.ts 向后兼容增强迁移：保留既有全部导出与行为不变，
 * 新增绝对到期时间戳能力——① TimerSnapshot 增加可选字段 dueAt（Date.now() 口径的
 * 绝对到期毫秒时间戳，start 记录、resume/reset/循环重开时重算、pause/完成时清除，
 * 供小程序切后台回前台后校准剩余时间）；② 模块级导出 getRemainingMs（基于
 * dueAt − Date.now() 差值计算剩余毫秒）与 formatRemainingMs（剩余毫秒 → mm:ss 文案）。
 * 供小程序端（web-mini，经 vite alias @shared 引用）与 Web 端共用。
 */

/** 单路计时器状态 */
export type TimerStatus = 'running' | 'paused' | 'finished'

/** 单路计时器快照（onChange 回调与 UI 展示数据源） */
export interface TimerSnapshot {
  /** 计时器唯一 ID（MultiTimer 内部自增） */
  id: number
  /** 展示名（如「焖煮」） */
  name: string
  /** 总时长（秒） */
  durationSec: number
  /** 剩余秒数（归零后为 0） */
  remainingSec: number
  /** 当前状态 */
  status: TimerStatus
  /** 是否循环计时（结束后自动重开） */
  repeat: boolean
  /**
   * 绝对到期时间戳（毫秒，Date.now() 口径；向后兼容增强新增的可选字段）。
   * running 态有效（start 记录、resume/reset/循环重开时重算）；pause 与 finished 时为 undefined。
   * 小程序切后台回前台后可用 getRemainingMs(dueAt) 校准真实剩余毫秒。
   */
  dueAt?: number
}

/** 变更事件类型（onChange 回调参数） */
export type TimerChangeType = 'add' | 'tick' | 'finish' | 'clear'

/** 变更事件负载 */
export interface TimerChangeEvent {
  /** 事件类型 */
  type: TimerChangeType
  /** 事件关联的计时器 ID（clear 事件为被清空那条；tick 广播时为触发心跳的计时器） */
  id: number | null
  /** 事件触发后全部计时器快照（UI 直接渲染用） */
  timers: TimerSnapshot[]
}

/** 心跳间隔（毫秒）：1 秒 */
const TICK_MS = 1000

/** 多路计时器管理类 */
export class MultiTimer {
  /** 全部计时器内部状态（id → 记录） */
  private records: Map<number, TimerSnapshot> = new Map()
  /** 自增 ID 发生器 */
  private nextId = 1
  /** 心跳定时器句柄（null = 已停表） */
  private heartbeat: ReturnType<typeof setInterval> | null = null
  /** 状态变化回调（构造时注入） */
  private readonly onChange: (event: TimerChangeEvent) => void

  /**
   * 构造多路计时器。
   * @param onChange 状态变化回调（add/tick/finish/clear 四类事件；可为空）
   */
  constructor(onChange?: (event: TimerChangeEvent) => void) {
    this.onChange = onChange ?? (() => {})
  }

  /**
   * 新增一路倒计时并立即开始计时。
   * @param name 展示名
   * @param durationSec 总时长（秒，须 > 0；非正值不创建）
   * @param repeat 是否循环（结束后自动重开，默认 false）
   * @returns 新计时器 ID（参数非法时返回 null）
   */
  start(name: string, durationSec: number, repeat = false): number | null {
    if (!Number.isFinite(durationSec) || durationSec <= 0) return null
    const id = this.nextId++
    this.records.set(id, {
      id,
      name,
      durationSec: Math.round(durationSec),
      remainingSec: Math.round(durationSec),
      status: 'running',
      repeat,
      // 绝对到期时间戳（向后兼容增强）：创建即记录，供后台回前台校准剩余时间
      dueAt: Date.now() + Math.round(durationSec) * 1000,
    })
    this.ensureHeartbeat()
    this.emit('add', id)
    return id
  }

  /**
   * 暂停某路计时（运行中才有效）。
   * @param id 计时器 ID
   * @returns 是否操作成功
   */
  pause(id: number): boolean {
    const rec = this.records.get(id)
    if (!rec || rec.status !== 'running') return false
    rec.status = 'paused'
    // 暂停中无绝对到期点（向后兼容增强）：清除 dueAt，恢复时按剩余量重算
    rec.dueAt = undefined
    this.emit('tick', id)
    return true
  }

  /**
   * 恢复某路计时（暂停中才有效）。
   * @param id 计时器 ID
   * @returns 是否操作成功
   */
  resume(id: number): boolean {
    const rec = this.records.get(id)
    if (!rec || rec.status !== 'paused') return false
    rec.status = 'running'
    // 恢复时按当前剩余量重算绝对到期时间戳（向后兼容增强）
    rec.dueAt = Date.now() + rec.remainingSec * 1000
    this.ensureHeartbeat()
    this.emit('tick', id)
    return true
  }

  /**
   * 重置某路计时：剩余量恢复为总时长并回到运行态。
   * @param id 计时器 ID
   * @returns 是否操作成功
   */
  reset(id: number): boolean {
    const rec = this.records.get(id)
    if (!rec) return false
    rec.remainingSec = rec.durationSec
    rec.status = 'running'
    // 重置即恢复满量：按总时长重算绝对到期时间戳（向后兼容增强）
    rec.dueAt = Date.now() + rec.durationSec * 1000
    this.ensureHeartbeat()
    this.emit('tick', id)
    return true
  }

  /**
   * 清除某路计时（从列表移除）。
   * @param id 计时器 ID
   * @returns 是否操作成功
   */
  clear(id: number): boolean {
    if (!this.records.has(id)) return false
    this.records.delete(id)
    this.stopHeartbeatIfIdle()
    this.emit('clear', id)
    return true
  }

  /**
   * 查询某路剩余秒数（不存在返回 null）。
   * @param id 计时器 ID
   * @returns 剩余秒数
   */
  remaining(id: number): number | null {
    return this.records.get(id)?.remainingSec ?? null
  }

  /**
   * 查询全部计时器快照（按加入顺序）。
   * @returns 快照数组
   */
  list(): TimerSnapshot[] {
    return Array.from(this.records.values()).map((rec) => ({ ...rec }))
  }

  /**
   * 是否存在运行中的计时器。
   * @returns 有运行中计时器则为 true
   */
  hasRunning(): boolean {
    for (const rec of this.records.values()) {
      if (rec.status === 'running') return true
    }
    return false
  }

  /**
   * 清空全部计时器并停表（页面卸载时调用）。
   */
  clearAll(): void {
    this.records.clear()
    this.stopHeartbeatIfIdle()
    this.emit('clear', null)
  }

  /**
   * 心跳一跳：全部运行中计时器递减 1s；归零触发 finish（循环计时自动重开）。
   */
  private tick(): void {
    const finishedIds: number[] = []
    for (const rec of this.records.values()) {
      if (rec.status !== 'running') continue
      rec.remainingSec -= 1
      if (rec.remainingSec <= 0) {
        rec.remainingSec = 0
        finishedIds.push(rec.id)
        if (rec.repeat) {
          // 循环计时：归零即重开下一轮
          rec.remainingSec = rec.durationSec
          // 重开下一轮：按满量重算绝对到期时间戳（向后兼容增强）
          rec.dueAt = Date.now() + rec.durationSec * 1000
        } else {
          rec.status = 'finished'
          // 已完成无到期点（向后兼容增强）：清除 dueAt
          rec.dueAt = undefined
        }
      }
    }
    // 逐条广播 finish（UI 侧做提示音/通知），再广播一次 tick 快照
    for (const fid of finishedIds) {
      this.emit('finish', fid)
    }
    if (finishedIds.length > 0 || this.hasRunning()) {
      this.emit('tick', finishedIds[0] ?? null)
    }
    this.stopHeartbeatIfIdle()
  }

  /**
   * 确保心跳在跑（有运行中计时器时启动单例 setInterval）。
   */
  private ensureHeartbeat(): void {
    if (this.heartbeat) return
    this.heartbeat = setInterval(() => this.tick(), TICK_MS)
  }

  /**
   * 无运行中计时器时停表（保留暂停/已完成记录，节省空转）。
   */
  private stopHeartbeatIfIdle(): void {
    if (this.heartbeat && !this.hasRunning()) {
      clearInterval(this.heartbeat)
      this.heartbeat = null
    }
  }

  /**
   * 广播变更事件（回调异常就地吞掉，不影响计时主流程）。
   * @param type 事件类型
   * @param id 关联计时器 ID
   */
  private emit(type: TimerChangeType, id: number | null): void {
    try {
      this.onChange({ type, id, timers: this.list() })
    } catch {
      // 回调异常不影响计时器本身
    }
  }
}

/**
 * 秒数 → 「mm:ss」展示文案（超 1 小时进位为 h:mm:ss）。
 * @param totalSec 秒数（负数按 0 处理）
 * @returns 形如 「05:30」/「1:02:03」的文案
 */
export function formatCountdown(totalSec: number): string {
  const sec = Math.max(0, Math.floor(totalSec))
  const h = Math.floor(sec / 3600)
  const m = Math.floor((sec % 3600) / 60)
  const s = sec % 60
  const pad = (n: number): string => String(n).padStart(2, '0')
  if (h > 0) return `${h}:${pad(m)}:${pad(s)}`
  return `${pad(m)}:${pad(s)}`
}

/**
 * 基于绝对到期时间戳计算剩余毫秒数（向后兼容增强新增；后台回前台校准语义）。
 * 小程序切后台期间 setInterval 心跳被冻结，回前台后以 dueAt − Date.now() 差值
 * 直接得到真实剩余时间，无需依赖心跳累计。
 * @param dueAt 绝对到期时间戳（毫秒，Date.now() 口径；如 TimerSnapshot.dueAt）
 * @returns 剩余毫秒数（= dueAt − Date.now()；dueAt 已过返回 0 或负值，
 *          调用方自行决定按 0 收敛或提示已超时）

 * 异常：
 *     不抛出（非有限入参返回 NaN，由调用方兜底；与 formatCountdown 的负数收敛策略互补）。
 */
export function getRemainingMs(dueAt: number): number {
  return dueAt - Date.now()
}

/**
 * 剩余毫秒数 → 「mm:ss」展示文案（超 1 小时进位为 h:mm:ss；向后兼容增强新增）。
 * 与 getRemainingMs 配套使用：getRemainingMs(dueAt) 得到真实剩余毫秒后格式化展示。
 * @param remainingMs 剩余毫秒数（负数 / 已过期按 0 处理；小数毫秒向上取整到秒，
 *                    如 29500ms 展示「00:30」避免「还剩 29 秒」的显示性提前归零）
 * @returns 形如「00:30」/「1:02:03」的文案（复用 formatCountdown）

 * 异常：
 *     不抛出（非有限入参经 Math.ceil → NaN 后由 formatCountdown 按 0 兜底）。
 */
export function formatRemainingMs(remainingMs: number): string {
  return formatCountdown(Math.ceil(remainingMs / 1000))
}
