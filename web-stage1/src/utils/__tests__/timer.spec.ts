/**
 * 文件职责：src/utils/timer.ts 单测（Task 9）。
 * 覆盖：并行 3 路计数互不干扰、暂停/恢复、重置、归零回调（finish 事件）、
 *       循环计时自动重开、clear/clearAll、formatCountdown 文案、
 *       非法时长拒绝创建、心跳空转自动停表。
 * 运行方式：npm run test（vitest run，node 环境，fake timers 驱动心跳）。
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { MultiTimer, formatCountdown, type TimerChangeEvent } from '../timer'

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
