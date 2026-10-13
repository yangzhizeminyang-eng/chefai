/**
 * 文件职责：innovation store generate 异步 job 轮询单测（M-01 创新生成异步化；
 * 自 web-stage1/src/stores/__tests__/innovation.spec.ts 迁移，原断言全部保留）。
 * 覆盖：precheck 命中拦截（不提交 job）、提交 job 后首轮轮询即 succeeded 取 recipe、
 *       failed 归一 GENERATION_FAILED（含 error 缺省兜底文案）、blocked 映射为
 *       precheck 拦截卡结构、一直 pending 直到轮询超上限抛 TIMEOUT、
 *       中途 pending 转 succeeded（继续轮询直至终态）。
 * 阶段二新增用例：pausePolling 暂停轮询（暂停窗口内不查询）、resumePolling 窗口内恢复、
 *                stopPolling 未终态收尾（promise 立即 resolve、generating 复位）。
 * 运行方式：npx vitest run（node 环境；endpoints 以 vi.mock 模拟 +
 *           vi.useFakeTimers 控制轮询节奏，advanceTimersByTimeAsync 推进 2.5s 间隔）。
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'

/** 模拟存储容器（store 链路加载需要 storage mock；本 spec 不直接断言持久化） */
const mem = vi.hoisted(() => new Map<string, string>())
const memMem = vi.hoisted(() => new Map<string, unknown>())

// endpoints 模块工厂 mock：store 全部消费的端点一并提供，避免真实导入未定义成员
vi.mock('@/api/endpoints', () => ({
  postInnovationPrecheck: vi.fn(),
  postInnovationJobCreate: vi.fn(),
  getInnovationJob: vi.fn(),
  postInnovationAdopt: vi.fn(),
  postInnovationFeedback: vi.fn(),
  postInnovationReuse: vi.fn(),
  getInnovationRecipe: vi.fn(),
}))

// storage 内存 Map 模拟（与真实封装同签名子集）
vi.mock('@/utils/storage', () => ({
  ANONYMOUS_ID_KEY: 'aicook_anonymous_id',
  SCHEMA_VERSION: '1',
  get: (key: string): unknown => {
    const raw = mem.get(key)
    if (raw === undefined || raw === '') return undefined
    try {
      return JSON.parse(raw)
    } catch {
      return undefined
    }
  },
  set: (key: string, value: unknown): void => {
    mem.set(key, JSON.stringify(value))
  },
  remove: (key: string): void => {
    mem.delete(key)
  },
  clear: (): void => {
    mem.clear()
  },
  memGet: (key: string): unknown => (memMem.has(key) ? memMem.get(key) : undefined),
  memSet: (key: string, value: unknown): void => {
    memMem.set(key, value)
  },
  memRemove: (key: string): void => {
    memMem.delete(key)
  },
}))

import {
  getInnovationJob,
  postInnovationJobCreate,
  postInnovationPrecheck,
} from '@/api/endpoints'
import type {
  InnovationJobStatusResponse,
  InnovationPrecheckResponse,
  InnovationRecipe,
} from '@shared/types'
import { useInnovationStore } from '@/stores/innovation'

/**
 * 构造最小创新菜谱实体（succeeded 轮询返回体复用；结构对齐 InnovationRecipe 契约）。
 * @returns 最小合法 InnovationRecipe
 */
function makeRecipe(): InnovationRecipe {
  return {
    id: 1,
    name: 'AI 创新菜',
    ingredients: [],
    steps: [],
    basis: { pairings: [], properties: [] },
    nutrition: { kcal: null, protein: null, fat: null, carb: null, excluded: [] },
    status: 'generated',
    is_ai_innovated: true,
    disclaimer: '本菜谱由 AI 生成，仅供参考',
  } as InnovationRecipe
}

/** 预检通过响应体（默认 mock 返回，命中拦截的用例内覆盖） */
const PRECHECK_OK: InnovationPrecheckResponse = { ok: true, blocked: false }

beforeEach(() => {
  setActivePinia(createPinia())
  // fake timers：控制轮询节奏（vitest fake timers 默认同时接管 Date.now）
  vi.useFakeTimers()
  vi.mocked(postInnovationPrecheck).mockReset()
  vi.mocked(postInnovationJobCreate).mockReset()
  vi.mocked(getInnovationJob).mockReset()
  vi.mocked(postInnovationPrecheck).mockResolvedValue(PRECHECK_OK)
  vi.mocked(postInnovationJobCreate).mockResolvedValue({ job_id: 'job-1', status: 'pending' })
})

afterEach(() => {
  vi.useRealTimers()
  vi.restoreAllMocks()
})

describe('innovation store generate 异步 job 轮询（M-01）', () => {
  it('precheck 命中拦截：不提交 job，拦截卡数据写入 precheck', async () => {
    vi.mocked(postInnovationPrecheck).mockResolvedValue({
      ok: false,
      blocked: true,
      message: '这组食材不能创新',
    })
    const store = useInnovationStore()
    await store.generate(['河豚', '豆腐'])
    expect(postInnovationJobCreate).not.toHaveBeenCalled()
    expect(store.precheck?.blocked).toBe(true)
    expect(store.precheck?.message).toBe('这组食材不能创新')
    expect(store.current).toBeNull()
    expect(store.error).toBeNull()
    expect(store.generating).toBe(false)
  })

  it('提交 job 后首轮轮询即 succeeded：recipe 写入 current，generating 复位', async () => {
    const recipe = makeRecipe()
    vi.mocked(getInnovationJob).mockResolvedValue({
      job_id: 'job-1',
      status: 'succeeded',
      recipe,
    })
    const store = useInnovationStore()
    const promise = store.generate(['鸡蛋', '西红柿'])
    await vi.advanceTimersByTimeAsync(0) // 让 precheck / 提交 job 的微任务先落地
    await vi.advanceTimersByTimeAsync(2500) // 触发第一轮轮询 → succeeded
    await promise
    expect(store.current).toEqual(recipe)
    expect(store.error).toBeNull()
    expect(store.generating).toBe(false)
  })

  it('轮询到 failed：归一为 GENERATION_FAILED 走 error 态', async () => {
    vi.mocked(getInnovationJob).mockResolvedValue({
      job_id: 'job-1',
      status: 'failed',
      error: '上游模型异常',
    })
    const store = useInnovationStore()
    const promise = store.generate(['鸡蛋'])
    await vi.advanceTimersByTimeAsync(0)
    await vi.advanceTimersByTimeAsync(2500)
    await promise
    expect(store.error?.code).toBe('GENERATION_FAILED')
    expect(store.error?.message).toBe('上游模型异常')
    expect(store.current).toBeNull()
    expect(store.generating).toBe(false)
  })

  it('轮询到 failed 且无 error 字段：使用兜底文案「生成失败，请重试」', async () => {
    vi.mocked(getInnovationJob).mockResolvedValue({
      job_id: 'job-1',
      status: 'failed',
    })
    const store = useInnovationStore()
    const promise = store.generate(['鸡蛋'])
    await vi.advanceTimersByTimeAsync(0)
    await vi.advanceTimersByTimeAsync(2500)
    await promise
    expect(store.error?.code).toBe('GENERATION_FAILED')
    expect(store.error?.message).toBe('生成失败，请重试')
  })

  it('轮询到 blocked：映射为 precheck 拦截卡结构（不写 error / current）', async () => {
    vi.mocked(getInnovationJob).mockResolvedValue({
      job_id: 'job-1',
      status: 'blocked',
      issues: [{ type: 'high_risk', message: '这组食材暂时不能创新', rule_id: 'FS-018' }],
    })
    const store = useInnovationStore()
    const promise = store.generate(['鸡蛋'])
    await vi.advanceTimersByTimeAsync(0)
    await vi.advanceTimersByTimeAsync(2500)
    await promise
    expect(store.precheck).toEqual({
      ok: false,
      blocked: true,
      rule_id: 'FS-018',
      message: '这组食材暂时不能创新',
    })
    expect(store.current).toBeNull()
    expect(store.error).toBeNull()
    expect(store.generating).toBe(false)
  })

  it('一直 pending 直到轮询超上限：归一为 TIMEOUT 走 error 态', async () => {
    vi.mocked(getInnovationJob).mockResolvedValue({
      job_id: 'job-1',
      status: 'pending',
    } as InnovationJobStatusResponse)
    const store = useInnovationStore()
    const promise = store.generate(['鸡蛋'])
    await vi.advanceTimersByTimeAsync(0)
    // 反复推进一个轮询间隔直至终态（guard 防死循环；上限 100s ≈ 40 轮）
    let guard = 0
    while (!store.error && guard < 60) {
      await vi.advanceTimersByTimeAsync(2500)
      guard++
    }
    await promise
    expect(store.error?.code).toBe('TIMEOUT')
    expect(store.error?.message).toBe('生成超时，请重试')
    expect(store.current).toBeNull()
    expect(store.generating).toBe(false)
  })

  it('中途 pending 转 succeeded：继续轮询直至拿到 recipe', async () => {
    const recipe = makeRecipe()
    let calls = 0
    vi.mocked(getInnovationJob).mockImplementation(async () => {
      calls++
      if (calls < 3) {
        return { job_id: 'job-1', status: 'pending' } as InnovationJobStatusResponse
      }
      return { job_id: 'job-1', status: 'succeeded', recipe }
    })
    const store = useInnovationStore()
    const promise = store.generate(['鸡蛋'])
    await vi.advanceTimersByTimeAsync(0)
    let guard = 0
    while (!store.current && guard < 20) {
      await vi.advanceTimersByTimeAsync(2500)
      guard++
    }
    await promise
    expect(store.current).toEqual(recipe)
    expect(calls).toBe(3)
  })
})

describe('innovation store 轮询暂停/恢复（阶段二新增：页面 onHide 可暂停）', () => {
  it('pausePolling 暂停轮询：暂停窗口内不查询任务；resumePolling 恢复后继续', async () => {
    let calls = 0
    vi.mocked(getInnovationJob).mockImplementation(async () => {
      calls++
      return { job_id: 'job-1', status: 'pending' } as InnovationJobStatusResponse
    })
    const store = useInnovationStore()
    const promise = store.generate(['鸡蛋'])
    await vi.advanceTimersByTimeAsync(0)
    await vi.advanceTimersByTimeAsync(2500) // 第一轮轮询（calls=1，pending）
    expect(calls).toBe(1)
    store.pausePolling()
    await vi.advanceTimersByTimeAsync(20000) // 暂停窗口：不调度、不查询
    expect(calls).toBe(1)
    store.resumePolling()
    await vi.advanceTimersByTimeAsync(2500) // 恢复后一轮轮询（calls=2）
    expect(calls).toBe(2)
    // 收尾：任务转 succeeded 结束轮询，避免 promise 悬挂
    vi.mocked(getInnovationJob).mockResolvedValue({
      job_id: 'job-1',
      status: 'succeeded',
      recipe: makeRecipe(),
    })
    let guard = 0
    while (!store.current && guard < 20) {
      await vi.advanceTimersByTimeAsync(2500)
      guard++
    }
    await promise
    expect(store.current).not.toBeNull()
    expect(store.generating).toBe(false)
  })

  it('stopPolling 未终态停止：轮询 promise 立即收尾，不再查询任务', async () => {
    let calls = 0
    vi.mocked(getInnovationJob).mockImplementation(async () => {
      calls++
      return { job_id: 'job-1', status: 'pending' } as InnovationJobStatusResponse
    })
    const store = useInnovationStore()
    const promise = store.generate(['鸡蛋'])
    await vi.advanceTimersByTimeAsync(0)
    await vi.advanceTimersByTimeAsync(2500)
    expect(store.generating).toBe(true)
    store.stopPolling()
    await promise
    const callsAfterStop = calls
    await vi.advanceTimersByTimeAsync(20000) // 停止后不再有任何轮询
    expect(calls).toBe(callsAfterStop)
    expect(store.generating).toBe(false)
    expect(store.error).toBeNull()
    expect(store.current).toBeNull()
  })
})
