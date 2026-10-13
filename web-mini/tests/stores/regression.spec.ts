/**
 * 文件职责：历史修复回归用例（阶段二迁移回归防线；对应阶段一 E2E 缺陷 NEW-01 / NEW-02）。
 * - NEW-01 孤儿匿名用户（T8 复测发现）：profile store 的全部读写 action 前必须先
 *   ensureAnonReady（匿名 ID 懒获取），否则请求层不带 X-Anonymous-Id，后端为该请求
 *   临时新建匿名用户，过敏原档案被挂到「孤儿用户」——硬过滤失效（RL-6 回归风险）。
 *   本 spec 断言：读（loadAll）与写（saveFamily）链路中 postAnonymous 先于档案端点被调用。
 * - NEW-02 askMode 覆写（T8 系统复测发现）：问厨娘结果被手选推荐重拉覆盖，两次不同
 *   问句显示同一份旧结果。修复=askMode 一律跳过初始重拉（视图守卫 if(askMode) return，
 *   数据前提为 store 的 askMode 状态与 ask 专属指纹 lastRequestKey='ask:{ids}'）。
 *   本 spec 断言：applyAskResults 落地后 askMode 置位 + ask 专属指纹（不被手选指纹
 *   误判）；双次问句结果独立（验收标准原文）；显式手选意图（fetchRecommend force）为
 *   设计内的接管路径（askMode 清除，摘要栏「改手选」入口）。
 */
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'

/** 模拟存储容器（store 链路加载需要 storage mock；本 spec 不直接断言持久化） */
const mem = vi.hoisted(() => new Map<string, string>())
const memMem = vi.hoisted(() => new Map<string, unknown>())

// endpoints 模块工厂 mock：覆盖 recommend / profile / ingredients / session 四个 store 的全部依赖导出
vi.mock('@/api/endpoints', () => ({
  getRecipe: vi.fn(),
  postRecommend: vi.fn(),
  postRecommendFiltered: vi.fn(),
  getIngredients: vi.fn(),
  postAnonymous: vi.fn(),
  postConsent: vi.fn(),
  getFamilyProfile: vi.fn(),
  putFamilyProfile: vi.fn(),
  postFamilyMember: vi.fn(),
  putFamilyMember: vi.fn(),
  deleteFamilyMember: vi.fn(),
  getSkillProfile: vi.fn(),
  putSkillProfile: vi.fn(),
  getDietGoal: vi.fn(),
  putDietGoal: vi.fn(),
}))

// storage 内存 Map 模拟（与真实封装同签名子集，get/set 走 JSON 序列化往返）
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
  getFamilyProfile,
  getRecipe,
  getSkillProfile,
  getDietGoal,
  postAnonymous,
  postRecommend,
  putFamilyProfile,
} from '@/api/endpoints'
import type {
  FamilyMember,
  RecommendResponse,
  SkillProfile,
} from '@shared/types'
import { useProfileStore } from '@/stores/profile'
import { useRecommendStore } from '@/stores/recommend'

/** 端点调用顺序记录（NEW-01 时序断言数据源） */
const callOrder: string[] = []

/**
 * 构造最小家庭成员（profile mock 数据工厂）。
 * @param id 成员 ID
 * @returns FamilyMember
 */
function makeMember(id: number): FamilyMember {
  return {
    id,
    name: `成员${id}`,
    relation: '本人',
    allergen_codes: [],
    custom_allergens: [],
    no_known_allergen: false,
    taste_spicy: 0,
    taste_salt: 0,
    taste_sweet: 0,
    dietary_restrictions: [],
    special_diet: [],
    special_population: [],
  }
}

/**
 * 构造主推荐正常响应（postRecommend mock 返回值，results 取最小结构）。
 * @returns RecommendResponse
 */
function makeRecommendResponse(): RecommendResponse {
  return {
    request_id: 'req-1',
    safe_mode: false,
    results: [
      {
        recipe_id: 1,
        title: '醋溜土豆丝',
        match_level: 'can_cook_now',
        covered_ingredients: ['土豆'],
        missing_ingredients: [],
        time_minutes: 15,
        difficulty: 'easy',
        calories_kcal: 120,
        allergens: [],
        required_equipment: ['炒锅'],
        rank_score: 0.8,
        rank_reasons: ['食材匹配度高'],
        source: '',
      },
    ],
    filtered_by: {},
    disclaimer_id: 'DISCLAIMER_V1',
    trace_id: 'trace-1',
  }
}

/**
 * 构造最小菜谱详情（getRecipe mock 返回值工厂）。
 * @param id 菜谱 ID
 * @returns 最小 RecipeDetail（ask 映射仅消费标识与展示字段）
 */
function makeDetail(id: number): Record<string, unknown> {
  return {
    id,
    title: `菜谱${id}`,
    time_minutes: 15,
    difficulty: 'easy',
    calories_kcal: 100,
    allergen_codes: [],
    equipment: [],
    source_label: '',
  }
}

beforeEach(() => {
  setActivePinia(createPinia())
  callOrder.length = 0
  // 存储隔离（测试隔离修复）：mem/memMem 为模块级共享 Map，跨用例残留会让后续用例
  // 的 ensureAnonymousId 命中缓存 ID 而跳过 postAnonymous，破坏调用时序断言前提
  mem.clear()
  memMem.clear()
  for (const fn of [getRecipe, postRecommend, getFamilyProfile, getSkillProfile, getDietGoal, putFamilyProfile]) {
    vi.mocked(fn).mockReset()
  }
  vi.mocked(postAnonymous).mockReset()
})

describe('NEW-01 档案读写前 ensureAnonReady（孤儿匿名用户防御）', () => {
  it('未初始化匿名 ID 时 loadAll 先获取匿名 ID 再读档案（postAnonymous 先于 getFamilyProfile）', async () => {
    vi.mocked(postAnonymous).mockImplementation(async () => {
      callOrder.push('postAnonymous')
      return { anonymous_id: 'anon-1' }
    })
    vi.mocked(getFamilyProfile).mockImplementation(async () => {
      callOrder.push('getFamilyProfile')
      return { family_id: 1, name: '我家', members: [makeMember(1)] }
    })
    vi.mocked(getSkillProfile).mockResolvedValue({ cooking_level: 2, equipment: [] } as SkillProfile)
    vi.mocked(getDietGoal).mockResolvedValue({ goal: 'balanced', note: '' })

    const store = useProfileStore()
    await store.loadAll()

    expect(callOrder.indexOf('postAnonymous')).toBeGreaterThanOrEqual(0)
    expect(callOrder.indexOf('postAnonymous')).toBeLessThan(callOrder.indexOf('getFamilyProfile'))
    expect(store.family).not.toBeNull()
  })

  it('写操作（saveFamily）前同样先就绪匿名 ID（putFamilyProfile 后于 postAnonymous）', async () => {
    vi.mocked(postAnonymous).mockImplementation(async () => {
      callOrder.push('postAnonymous')
      return { anonymous_id: 'anon-1' }
    })
    vi.mocked(putFamilyProfile).mockImplementation(async () => {
      callOrder.push('putFamilyProfile')
      return { family_id: 1, name: '我家', members: [makeMember(1)] }
    })

    const store = useProfileStore()
    await store.saveFamily('我家', [makeMember(1)])

    expect(callOrder.indexOf('postAnonymous')).toBeGreaterThanOrEqual(0)
    expect(callOrder.indexOf('postAnonymous')).toBeLessThan(callOrder.indexOf('putFamilyProfile'))
  })
})

describe('NEW-02 askMode 守卫（问厨娘结果不被手选推荐重拉覆盖）', () => {
  it('applyAskResults 落地后 askMode 置位 + ask 专属指纹（视图守卫跳过初始重拉的数据前提）', async () => {
    vi.mocked(getRecipe).mockResolvedValue(makeDetail(1) as never)
    const store = useRecommendStore()
    await store.applyAskResults([1], '番茄炒蛋怎么做', 'trace-1')

    // 视图守卫 if (askMode) return 的数据前提：askMode 状态 + ask 专属指纹（与手选指纹格式区分）
    expect(store.askMode).toBe(true)
    expect(store.lastRequestKey).toBe('ask:1')
    expect(store.askQuestion).toBe('番茄炒蛋怎么做')
    // ask 结果已落地（守卫生效时初始重拉不发生，问句结果保持不被覆写）
    expect(store.results).toHaveLength(1)
    expect(store.results[0].recipe_id).toBe(1)
  })

  it('双次问句结果独立：第二次 applyAskResults 完整覆盖且 askMode 保持（验收标准原文）', async () => {
    vi.mocked(getRecipe).mockImplementation(async (id) => makeDetail(id as number) as never)
    const store = useRecommendStore()
    await store.applyAskResults([1], '问句一', 'trace-1')
    await store.applyAskResults([2], '问句二', 'trace-2')

    expect(store.askMode).toBe(true)
    expect(store.askQuestion).toBe('问句二')
    expect(store.traceId).toBe('trace-2')
    expect(store.results.map((r) => r.recipe_id)).toEqual([2])
    expect(store.lastRequestKey).toBe('ask:2')
  })

  it('显式手选意图（fetchRecommend force）接管：askMode 清除为设计行为（摘要栏「改手选」路径）', async () => {
    vi.mocked(getRecipe).mockResolvedValue(makeDetail(9) as never)
    vi.mocked(postRecommend).mockResolvedValue(makeRecommendResponse())
    const store = useRecommendStore()
    await store.applyAskResults([9], '问句', 'trace-1')
    expect(store.askMode).toBe(true)

    const { useIngredientsStore } = await import('@/stores/ingredients')
    useIngredientsStore().selected = { 5: { id: 5, name: '土豆' } }
    await store.fetchRecommend(true)

    // 手选接管（设计内路径）：askMode 清除，results 来自手选推荐响应
    expect(store.askMode).toBe(false)
    expect(store.askQuestion).toBe('')
    expect(store.results[0].recipe_id).toBe(1)
  })
})
