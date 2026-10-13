/**
 * 文件职责：src/utils/timer.ts 单测（Task 9）。
 * 覆盖：并行 3 路计数互不干扰、暂停/恢复、重置、归零回调（finish 事件）、
 *       循环计时自动重开、clear/clearAll、formatCountdown 文案、
 *       非法时长拒绝创建、心跳空转自动停表。
 * 运行方式：npm run test（vitest run，node 环境，fake timers 驱动心跳）。
 * 从 web-stage1/src/utils/__tests__/timer.spec.ts 零改造迁移（仅本文件级注释追加迁移说明、
 * 被测模块导入路径改为 ../src/utils/timer），原用例与断言保持原样；
 * 文件末尾追加阶段二增强用例（getRemainingMs / formatRemainingMs 绝对到期时间戳校准）。
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import {
  MultiTimer,
  formatCountdown,
  formatRemainingMs,
  getRemainingMs,
  type TimerChangeEvent,
} from '../src/utils/timer'

beforeEach(() => {
  vi.useFakeTimers()
})

afterEach(() => {
  vi.useRealTimers()
})

/** 收集事件的最小监听器工厂 */
function makeCollector(): { events: TimerChangeEvent[]; onChange: (e: TimerChangeEvent) => void } {
  const events: TimerChangeEvent[] = []
  return { events, onChange: (e) => events.push(e) }
}

describe('MultiTimer 并行多路计时', () => {
  it('3 路并行倒计时互不干扰（各按各自剩余量递减）', () => {
    const timer = new MultiTimer()
    const a = timer.start('焖煮', 60)
    const b = timer.start('焯水', 30)
    const c = timer.start('腌制', 120)
    expect(a).not.toBeNull()
    expect(b).not.toBeNull()
    expect(c).not.toBeNull()

    vi.advanceTimersByTime(5000)
    expect(timer.remaining(a!)).toBe(55)
    expect(timer.remaining(b!)).toBe(25)
    expect(timer.remaining(c!)).toBe(115)

    vi.advanceTimersByTime(20000)
    expect(timer.remaining(a!)).toBe(35)
    expect(timer.remaining(b!)).toBe(5)
    expect(timer.remaining(c!)).toBe(95)
  })

  it('暂停后不再递减，恢复后继续', () => {
    const timer = new MultiTimer()
    const id = timer.start('计时', 30)
    vi.advanceTimersByTime(3000)
    expect(timer.remaining(id!)).toBe(27)

    expect(timer.pause(id!)).toBe(true)
    vi.advanceTimersByTime(10000)
    // 暂停期间不走表
    expect(timer.remaining(id!)).toBe(27)

    expect(timer.resume(id!)).toBe(true)
    vi.advanceTimersByTime(2000)
    expect(timer.remaining(id!)).toBe(25)
  })

  it('reset 恢复满量并回到运行态', () => {
    const timer = new MultiTimer()
    const id = timer.start('计时', 20)
    vi.advanceTimersByTime(15000)
    expect(timer.remaining(id!)).toBe(5)

    expect(timer.reset(id!)).toBe(true)
    expect(timer.remaining(id!)).toBe(20)
    // 重置后仍在走表
    vi.advanceTimersByTime(1000)
    expect(timer.remaining(id!)).toBe(19)
  })

  it('归零触发 finish 事件且状态变为 finished', () => {
    const { events, onChange } = makeCollector()
    const timer = new MultiTimer(onChange)
    const id = timer.start('短计时', 3)
    vi.advanceTimersByTime(3000)

    const finishEvents = events.filter((e) => e.type === 'finish' && e.id === id)
    expect(finishEvents.length).toBe(1)
    const snap = timer.list().find((t) => t.id === id)
    expect(snap?.status).toBe('finished')
    expect(snap?.remainingSec).toBe(0)
  })

  it('repeat=true 归零后自动重开下一轮', () => {
    const timer = new MultiTimer()
    const id = timer.start('循环计时', 2, true)
    vi.advanceTimersByTime(2000)
    // 第一轮归零瞬间自动重开为满量
    expect(timer.remaining(id!)).toBe(2)
    vi.advanceTimersByTime(1000)
    expect(timer.remaining(id!)).toBe(1)
  })

  it('clear 移除单路，clearAll 清空全部', () => {
    const timer = new MultiTimer()
    const a = timer.start('A', 10)
    const b = timer.start('B', 20)
    expect(timer.clear(a!)).toBe(true)
    expect(timer.remaining(a!)).toBeNull()
    expect(timer.list().length).toBe(1)

    timer.clearAll()
    expect(timer.list().length).toBe(0)
    expect(timer.hasRunning()).toBe(false)
    // 清空后 b 也不存在
    expect(timer.remaining(b!)).toBeNull()
  })

  it('非正时长 / 非法值拒绝创建（返回 null）', () => {
    const timer = new MultiTimer()
    expect(timer.start('零秒', 0)).toBeNull()
    expect(timer.start('负数', -5)).toBeNull()
    expect(timer.start('NaN', Number.NaN)).toBeNull()
    expect(timer.list().length).toBe(0)
  })

  it('对不存在 / 非法状态的计时器操作返回 false', () => {
    const timer = new MultiTimer()
    expect(timer.pause(999)).toBe(false)
    expect(timer.resume(999)).toBe(false)
    expect(timer.reset(999)).toBe(false)
    expect(timer.clear(999)).toBe(false)

    const id = timer.start('A', 10)
    // 运行中不能 resume；清除后不能再 pause
    expect(timer.resume(id!)).toBe(false)
    timer.clear(id!)
    expect(timer.pause(id!)).toBe(false)
  })

  it('全部计时暂停/完成后心跳停表（无空转），恢复后重新起跳', () => {
    const timer = new MultiTimer()
    const id = timer.start('A', 10)
    timer.pause(id!)
    // 暂停后经过很长时间（fake timer 下不会报错，说明 interval 已清）
    vi.advanceTimersByTime(60000)
    expect(timer.remaining(id!)).toBe(10)
    timer.resume(id!)
    vi.advanceTimersByTime(1000)
    expect(timer.remaining(id!)).toBe(9)
  })
})

describe('formatCountdown 倒计时文案', () => {
  it('常规分秒补零展示', () => {
    expect(formatCountdown(0)).toBe('00:00')
    expect(formatCountdown(5)).toBe('00:05')
    expect(formatCountdown(330)).toBe('05:30')
  })

  it('超一小时进位为 h:mm:ss', () => {
    expect(formatCountdown(3723)).toBe('1:02:03')
  })

  it('负数按 0 处理，小数向下取整', () => {
    expect(formatCountdown(-3)).toBe('00:00')
    expect(formatCountdown(59.9)).toBe('00:59')
  })
})

describe('getRemainingMs / formatRemainingMs 绝对到期时间戳校准（阶段二小程序增强）', () => {
  it('dueAt 绝对时间戳在模拟时钟前进后正确衰减（后台回前台校准语义）', () => {
    vi.setSystemTime(1_000_000)
    const dueAt = Date.now() + 30_000
    expect(getRemainingMs(dueAt)).toBe(30_000)
    // 模拟切后台 10 秒：fake timers 同步推进 Date.now()，剩余量按真实墙钟差值衰减
    vi.advanceTimersByTime(10_000)
    expect(getRemainingMs(dueAt)).toBe(20_000)
  })

  it('直接传入过去时刻 dueAt 返回 0 或负值（校准语义）', () => {
    vi.setSystemTime(2_000_000)
    expect(getRemainingMs(1_900_000)).toBeLessThanOrEqual(0)
  })

  it('MultiTimer 生命周期维护 dueAt：start 记录、pause 清除、resume 按剩余量重算', () => {
    vi.setSystemTime(3_000_000)
    const timer = new MultiTimer()
    const id = timer.start('计时', 30)
    // start 即记录绝对到期点：now(3_000_000) + 30s = 3_030_000
    expect(timer.list().find((t) => t.id === id)?.dueAt).toBe(3_030_000)
    // 暂停中无绝对到期点
    timer.pause(id!)
    expect(timer.list().find((t) => t.id === id)?.dueAt).toBeUndefined()
    // 恢复后按当前剩余量（满量 30s）重算
    timer.resume(id!)
    expect(timer.list().find((t) => t.id === id)?.dueAt).toBe(3_030_000)
  })

  it('formatRemainingMs 剩余毫秒 → mm:ss（负数按 0，小数毫秒向上取整）', () => {
    expect(formatRemainingMs(30_000)).toBe('00:30')
    expect(formatRemainingMs(29_500)).toBe('00:30')
    expect(formatRemainingMs(-1)).toBe('00:00')
  })
})
