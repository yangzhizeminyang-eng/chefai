/**
 * 文件职责：recommend store applyAskResults 的 request_id 串联单测（W-02 遗留修复验证；
 * 自 web-stage1/src/stores/__tests__/recommend.spec.ts 迁移，断言值与用例语义保持一致）。
 * 覆盖：ask 路径第 4 参 requestId 透传写入 store（「查看调度详情」跳 trace 查询
 *       取证串联的数据前提）；缺省调用兼容置空；连续调用以最新值覆盖不残留。
 * 适配说明：endpoints 以 vi.mock('@/api/endpoints') 模拟；askFlow 映射函数改从
 *           @shared/utils 桶文件 mock；storage 以内存 Map 模拟（node 环境无 uni API）。
 */
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'

/** 模拟存储容器（store 链路加载需要 storage mock；本 spec 不直接断言持久化） */
const mem = vi.hoisted(() => new Map<string, string>())
const memMem = vi.hoisted(() => new Map<string, unknown>())

// endpoints 模块工厂 mock：applyAskResults 仅消费 getRecipe；postRecommend 一并提供，避免真实导入未定义成员
vi.mock('@/api/endpoints', () => ({
  getRecipe: vi.fn(),
  postRecommend: vi.fn(),
}))

// askFlow 映射函数 mock：本 spec 聚焦 request_id 串联，不耦合真实菜谱字段映射细节
// （store 自 @shared/utils 桶文件导入，故 mock 桶路径）
vi.mock('@shared/utils', () => ({
  recipeDetailToAskItem: (detail: { id: number }, question: string) => ({
    recipe_id: detail.id,
    rank_reasons: [`来自你的提问「${question}」`],
  }),
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

import { getRecipe } from '@/api/endpoints'
import { useRecommendStore } from '@/stores/recommend'

/**
 * 构造最小菜谱详情（getRecipe mock 返回值工厂）。
 * @param id 菜谱 ID
 * @returns 仅含标识字段的 RecipeDetail（映射已 mock，无需完整字段）
 */
function makeDetail(id: number): { id: number; title: string } {
  return { id, title: `菜谱${id}` }
}

/**
 * 提取推荐项的菜谱 ID（results 映射断言辅助）。
 * @param item 推荐结果条目
 * @returns 菜谱 ID
 */
function idOf(item: { recipe_id: number }): number {
  return item.recipe_id
}

beforeEach(() => {
  setActivePinia(createPinia())
  vi.mocked(getRecipe).mockReset()
})

describe('recommend store applyAskResults 的 request_id 串联（W-02 遗留）', () => {
  it('第 4 参 requestId 透传写入 store（/trace?request_id= 串联前提）', async () => {
    vi.mocked(getRecipe).mockResolvedValue(makeDetail(1) as never)
    const store = useRecommendStore()
    await store.applyAskResults([1], '番茄炒蛋怎么做', 'trace-1', 'req-abc-123')
    expect(store.requestId).toBe('req-abc-123')
    expect(store.traceId).toBe('trace-1')
    expect(store.askMode).toBe(true)
    expect(store.askQuestion).toBe('番茄炒蛋怎么做')
    expect(store.results.map(idOf)).toEqual([1])
    expect(store.lastRequestKey).toBe('ask:1')
  })

  it('缺省第 4 参时 requestId 置空（旧调用兼容，不误串历史幂等键）', async () => {
    vi.mocked(getRecipe).mockResolvedValue(makeDetail(2) as never)
    const store = useRecommendStore()
    await store.applyAskResults([2], '红烧肉', 'trace-2')
    expect(store.requestId).toBe('')
    expect(store.traceId).toBe('trace-2')
  })

  it('连续两次 applyAskResults 以最新 request_id 覆盖（不留旧值）', async () => {
    vi.mocked(getRecipe).mockResolvedValue(makeDetail(3) as never)
    const store = useRecommendStore()
    await store.applyAskResults([3], '问题一', 'trace-3', 'req-old')
    await store.applyAskResults([3], '问题二', 'trace-4', 'req-new')
    expect(store.requestId).toBe('req-new')
    expect(store.traceId).toBe('trace-4')
  })
})
