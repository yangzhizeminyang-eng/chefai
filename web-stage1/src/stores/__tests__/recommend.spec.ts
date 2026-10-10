/**
 * 文件职责：recommend store applyAskResults 的 request_id 串联单测（W-02 遗留修复验证）。
 * 覆盖：ask 路径第 4 参 requestId 透传写入 store（W-02「查看调度详情」跳 /trace?request_id=
 *       取证串联的数据前提）；缺省调用兼容置空；连续调用以最新值覆盖不残留。
 * 运行方式：npm run test（vitest run，node 环境；getRecipe / recipeDetailToAskItem 以 vi.mock 模拟）。
 */
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'

// endpoints 模块工厂 mock：applyAskResults 仅消费 getRecipe；postRecommend 一并提供，避免真实导入未定义成员
vi.mock('@/api/endpoints', () => ({
  getRecipe: vi.fn(),
  postRecommend: vi.fn(),
}))

// askFlow 映射函数 mock：本 spec 聚焦 request_id 串联，不耦合真实菜谱字段映射细节
vi.mock('@/utils/askFlow', () => ({
  recipeDetailToAskItem: (detail: { id: number }, question: string) => ({
    recipe_id: detail.id,
    rank_reasons: [`来自你的提问「${question}」`],
  }),
}))

import { getRecipe } from '@/api/endpoints'
import type { RecipeDetail } from '@/api/types'
import { useRecommendStore } from '../recommend'

/**
 * 构造最小菜谱详情（getRecipe mock 返回值工厂）。
 * @param id 菜谱 ID
 * @returns 仅含标识字段的 RecipeDetail（映射已 mock，无需完整字段）
 */
function makeDetail(id: number): RecipeDetail {
  return { id, title: `菜谱${id}` } as unknown as RecipeDetail
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
    vi.mocked(getRecipe).mockResolvedValue(makeDetail(1))
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
    vi.mocked(getRecipe).mockResolvedValue(makeDetail(2))
    const store = useRecommendStore()
    await store.applyAskResults([2], '红烧肉', 'trace-2')
    expect(store.requestId).toBe('')
    expect(store.traceId).toBe('trace-2')
  })

  it('连续两次 applyAskResults 以最新 request_id 覆盖（不留旧值）', async () => {
    vi.mocked(getRecipe).mockResolvedValue(makeDetail(3))
    const store = useRecommendStore()
    await store.applyAskResults([3], '问题一', 'trace-3', 'req-old')
    await store.applyAskResults([3], '问题二', 'trace-4', 'req-new')
    expect(store.requestId).toBe('req-new')
    expect(store.traceId).toBe('trace-4')
  })
})
