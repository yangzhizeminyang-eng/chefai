/**
 * 文件职责：DEF-03 被过滤清单重放契约单测（W-02「显示被我过滤掉的菜」明细修复验证）。
 * 覆盖：
 * - 开关打开 → fetchRecommend 主推荐成功后调用 POST /v1/recommend/filtered 重放接口，
 *   filteredItems 按 {recipe_name→title, reasons→filter_reasons} 契约映射填充；
 * - 重放请求体口径：ingredients 同主推荐、过敏原/忌口取家庭档案「全成员并集」去重、
 *   设备取 skill.equipment、不传 difficulty_cap（主推荐管线未启用难度上限）；
 * - 档案时序：family/skill 未加载时先 loadAll（档案端点先于重放接口被调用）；
 * - 空响应（filtered=[]）→ filteredItems 空数组（页面回退统计行语义）、不 toast；
 * - 重放失败（reject / 家庭档案缺失）→ filteredItems 清空 + toast「过滤明细加载失败，
 *   请重试」+ filteredLoadFailed=true，主推荐 results 不受影响；
 * - 原因 type→中文映射 filterReasonLabel（allergen/taboo/difficulty/equipment 与未知兜底）。
 * 运行方式：npm run test（vitest run，node 环境；endpoints/element-plus 以 vi.mock 模拟）。
 */
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'

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

// element-plus mock：store 内 ElMessage.error 为重放失败的统一降级提示，本 spec 断言其调用
vi.mock('element-plus', () => ({
  ElMessage: {
    error: vi.fn(),
    info: vi.fn(),
    success: vi.fn(),
    warning: vi.fn(),
  },
}))

import { ElMessage } from 'element-plus'
import {
  deleteFamilyMember,
  getDietGoal,
  getFamilyProfile,
  getIngredients,
  getRecipe,
  getSkillProfile,
  postAnonymous,
  postConsent,
  postFamilyMember,
  postRecommend,
  postRecommendFiltered,
  putDietGoal,
  putFamilyMember,
  putFamilyProfile,
  putSkillProfile,
} from '@/api/endpoints'
import type {
  FamilyMember,
  FamilyProfile,
  RecommendResponse,
  SkillProfile,
} from '@/api/types'
import { filterReasonLabel, useRecommendStore } from '../recommend'

/** 档案 / 重放端点的调用顺序记录（时序用例断言数据源） */
const callOrder: string[] = []

/**
 * 构造家庭成员档案（getFamilyProfile mock 数据工厂，缺省字段全空）。
 * @param overrides 成员字段覆盖（allergen_codes / dietary_restrictions 等）
 * @param id 成员 ID（默认 1）
 * @returns 完整 FamilyMember
 */
function makeMember(overrides: Partial<FamilyMember>, id = 1): FamilyMember {
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
    ...overrides,
  }
}

/**
 * 构造家庭档案响应（getFamilyProfile mock 返回值）。
 * @param members 成员列表
 * @returns FamilyProfile
 */
function makeFamilyProfile(members: FamilyMember[]): FamilyProfile {
  return { family_id: 1, name: '我家', members }
}

/**
 * 构造厨艺设备档案响应（getSkillProfile mock 返回值）。
 * @param equipment 设备清单
 * @returns SkillProfile
 */
function makeSkillProfile(equipment: string[]): SkillProfile {
  return { cooking_level: 2, equipment }
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
    filtered_by: { allergen: 2 },
    disclaimer_id: 'DISCLAIMER_V1',
    trace_id: 'trace-1',
  }
}

/**
 * 构造重放端点成功响应（postRecommendFiltered mock 返回值工厂）。
 * @param items filtered 元素列表
 * @returns 含 total_filtered 的重放响应体
 */
function makeFilteredResponse(items: Array<{ recipe_id: number; recipe_name: string; reason: string; reasons: Array<{ type: string; detail: string }> }>) {
  return { filtered: items, total_filtered: items.length }
}

/**
 * 设置档案端点成功 mock（并记录调用顺序；家庭档案默认含花生过敏成员）。
 * @param family 家庭档案（缺省单成员花生过敏）
 * @param skill 设备档案（缺省仅炒锅）
 */
function setupProfileMocks(
  family: FamilyProfile = makeFamilyProfile([
    makeMember({ allergen_codes: ['peanut'] }),
  ]),
  skill: SkillProfile = makeSkillProfile(['炒锅']),
): void {
  vi.mocked(getFamilyProfile).mockImplementation(async () => {
    callOrder.push('getFamilyProfile')
    return family
  })
  vi.mocked(getSkillProfile).mockImplementation(async () => {
    callOrder.push('getSkillProfile')
    return skill
  })
  vi.mocked(getDietGoal).mockImplementation(async () => {
    callOrder.push('getDietGoal')
    return { goal: 'balanced', note: '' }
  })
}

beforeEach(() => {
  setActivePinia(createPinia())
  callOrder.length = 0
  for (const fn of [getRecipe, postRecommend, postRecommendFiltered, getIngredients, postAnonymous, postConsent, getFamilyProfile, putFamilyProfile, postFamilyMember, putFamilyMember, deleteFamilyMember, getSkillProfile, putSkillProfile, getDietGoal, putDietGoal]) {
    vi.mocked(fn).mockReset()
  }
  vi.mocked(ElMessage.error).mockReset()
  vi.mocked(ElMessage.info).mockReset()
  // 匿名会话：fetchRecommend 内 ensureAnonymousId 依赖（失败可本地兜底，mock 保证干净）
  vi.mocked(postAnonymous).mockResolvedValue({ anonymous_id: 'anon-1' })
})

describe('DEF-03 被过滤清单重放（POST /v1/recommend/filtered）', () => {
  it('开关打开：主推荐成功后调用重放接口，filteredItems 按契约映射（recipe_name→title / reasons→filter_reasons）', async () => {
    setupProfileMocks()
    vi.mocked(postRecommend).mockResolvedValue(makeRecommendResponse())
    vi.mocked(postRecommendFiltered).mockResolvedValue(
      makeFilteredResponse([
        {
          recipe_id: 9,
          recipe_name: '青椒土豆丝',
          reason: 'allergen',
          reasons: [{ type: 'allergen', detail: '命中过敏原：花生' }],
        },
        {
          recipe_id: 12,
          recipe_name: '宫保鸡丁',
          reason: 'equipment',
          reasons: [
            { type: 'allergen', detail: '命中过敏原：花生' },
            { type: 'equipment', detail: '缺少设备：燃气灶' },
          ],
        },
      ]),
    )
    const store = useRecommendStore()
    store.showFilteredItems = true
    const { useIngredientsStore } = await import('../ingredients')
    useIngredientsStore().selected = { 5: { id: 5, name: '土豆' } }
    await store.fetchRecommend(true)

    expect(postRecommendFiltered).toHaveBeenCalledTimes(1)
    expect(store.filteredItems).toEqual([
      {
        recipe_id: 9,
        title: '青椒土豆丝',
        filter_reasons: [{ type: 'allergen', detail: '命中过敏原：花生' }],
      },
      {
        recipe_id: 12,
        title: '宫保鸡丁',
        filter_reasons: [
          { type: 'allergen', detail: '命中过敏原：花生' },
          { type: 'equipment', detail: '缺少设备：燃气灶' },
        ],
      },
    ])
    expect(store.filteredLoadFailed).toBe(false)
    expect(ElMessage.error).not.toHaveBeenCalled()
  })

  it('重放请求体口径：ingredients 同主推荐、过敏原/忌口取多成员并集去重、设备取 skill、不传 difficulty_cap', async () => {
    setupProfileMocks(
      makeFamilyProfile([
        makeMember({ allergen_codes: ['peanut', 'seafood'], dietary_restrictions: ['香菜'] }, 1),
        makeMember({ allergen_codes: ['peanut', 'mango'], dietary_restrictions: ['香菜', '内脏'] }, 2),
      ]),
      makeSkillProfile(['炒锅', '电饭煲']),
    )
    vi.mocked(postRecommend).mockResolvedValue(makeRecommendResponse())
    vi.mocked(postRecommendFiltered).mockResolvedValue(makeFilteredResponse([]))
    const store = useRecommendStore()
    store.showFilteredItems = true
    // 已选食材（W-01 语义：id + name），经 ingredients store 注入
    const { useIngredientsStore } = await import('../ingredients')
    const ingredientsStore = useIngredientsStore()
    ingredientsStore.selected = { 5: { id: 5, name: '土豆' }, 6: { id: 6, name: '青椒' } }

    await store.fetchRecommend(true)

    expect(postRecommendFiltered).toHaveBeenCalledTimes(1)
    const body = vi.mocked(postRecommendFiltered).mock.calls[0][0]
    expect(body.ingredients).toEqual([
      { ingredient_id: 5, quantity_level: 'enough' },
      { ingredient_id: 6, quantity_level: 'enough' },
    ])
    // 全成员并集 + 去重 + 首现顺序
    expect(body.allergen_codes).toEqual(['peanut', 'seafood', 'mango'])
    expect(body.dietary_restrictions).toEqual(['香菜', '内脏'])
    expect(body.equipment).toEqual(['炒锅', '电饭煲'])
    // 主推荐管线未启用难度上限，重放保持同口径不传
    expect(body.difficulty_cap).toBeUndefined()
  })

  it('档案时序：family/skill 未加载时先 loadAll（档案端点先于重放接口被调）', async () => {
    setupProfileMocks()
    vi.mocked(postRecommend).mockResolvedValue(makeRecommendResponse())
    vi.mocked(postRecommendFiltered).mockImplementation(async (body) => {
      callOrder.push('postRecommendFiltered')
      void body
      return makeFilteredResponse([])
    })
    const store = useRecommendStore()
    store.showFilteredItems = true
    const { useIngredientsStore } = await import('../ingredients')
    useIngredientsStore().selected = { 5: { id: 5, name: '土豆' } }

    await store.fetchRecommend(true)

    expect(callOrder.indexOf('getFamilyProfile')).toBeGreaterThanOrEqual(0)
    expect(callOrder.indexOf('postRecommendFiltered')).toBeGreaterThan(callOrder.indexOf('getFamilyProfile'))
    expect(callOrder.indexOf('postRecommendFiltered')).toBeGreaterThan(callOrder.indexOf('getSkillProfile'))
  })

  it('开关关闭：不调用重放接口（主推荐仅回 filtered_by 计数）', async () => {
    setupProfileMocks()
    vi.mocked(postRecommend).mockResolvedValue(makeRecommendResponse())
    const store = useRecommendStore()
    store.showFilteredItems = false
    const { useIngredientsStore } = await import('../ingredients')
    useIngredientsStore().selected = { 5: { id: 5, name: '土豆' } }

    await store.fetchRecommend(true)

    expect(postRecommendFiltered).not.toHaveBeenCalled()
    expect(store.filteredItems).toEqual([])
  })

  it('空响应（filtered=[]）：filteredItems 空数组（页面回退统计行）、不 toast', async () => {
    setupProfileMocks()
    vi.mocked(postRecommend).mockResolvedValue(makeRecommendResponse())
    vi.mocked(postRecommendFiltered).mockResolvedValue(makeFilteredResponse([]))
    const store = useRecommendStore()
    store.showFilteredItems = true
    const { useIngredientsStore } = await import('../ingredients')
    useIngredientsStore().selected = { 5: { id: 5, name: '土豆' } }

    await store.fetchRecommend(true)

    expect(store.filteredItems).toEqual([])
    expect(store.filteredLoadFailed).toBe(false)
    expect(ElMessage.error).not.toHaveBeenCalled()
  })

  it('重放失败：filteredItems 清空 + toast「过滤明细加载失败，请重试」+ filteredLoadFailed=true，主推荐 results 不受影响', async () => {
    setupProfileMocks()
    vi.mocked(postRecommend).mockResolvedValue(makeRecommendResponse())
    vi.mocked(postRecommendFiltered).mockRejectedValue({ code: 500, message: 'server error' })
    const store = useRecommendStore()
    store.showFilteredItems = true
    const { useIngredientsStore } = await import('../ingredients')
    useIngredientsStore().selected = { 5: { id: 5, name: '土豆' } }

    await store.fetchRecommend(true)

    expect(store.filteredItems).toEqual([])
    expect(store.filteredLoadFailed).toBe(true)
    expect(ElMessage.error).toHaveBeenCalledTimes(1)
    expect(vi.mocked(ElMessage.error).mock.calls[0][0]).toBe('过滤明细加载失败，请重试')
    // 主推荐结果不受重放失败影响（异常态不误触整页错误）
    expect(store.error).toBeNull()
    expect(store.results).toHaveLength(1)
  })

  it('家庭档案加载失败：loadAll 后 family 仍为空 → 视为重放失败走 toast 降级（过敏原口径缺失不静默）', async () => {
    vi.mocked(getFamilyProfile).mockRejectedValue({ code: 500, message: 'profile error' })
    vi.mocked(getSkillProfile).mockResolvedValue(makeSkillProfile(['炒锅']))
    vi.mocked(getDietGoal).mockResolvedValue({ goal: 'balanced', note: '' })
    vi.mocked(postRecommend).mockResolvedValue(makeRecommendResponse())
    const store = useRecommendStore()
    store.showFilteredItems = true
    const { useIngredientsStore } = await import('../ingredients')
    useIngredientsStore().selected = { 5: { id: 5, name: '土豆' } }

    await store.fetchRecommend(true)

    expect(postRecommendFiltered).not.toHaveBeenCalled()
    expect(store.filteredItems).toEqual([])
    expect(store.filteredLoadFailed).toBe(true)
    expect(ElMessage.error).toHaveBeenCalledWith('过滤明细加载失败，请重试')
    expect(store.results).toHaveLength(1)
  })

  it('无已选食材：直接清空明细回退统计，不调用重放接口（ingredients ≥1 契约）', async () => {
    setupProfileMocks()
    const store = useRecommendStore()
    await store.fetchFilteredItems()
    expect(postRecommendFiltered).not.toHaveBeenCalled()
    expect(store.filteredItems).toEqual([])
  })
})

describe('过滤原因 type→中文映射（filterReasonLabel）', () => {
  it('四类类型码映射中文标签', () => {
    expect(filterReasonLabel('allergen')).toBe('过敏原')
    expect(filterReasonLabel('taboo')).toBe('忌口')
    expect(filterReasonLabel('difficulty')).toBe('难度')
    expect(filterReasonLabel('equipment')).toBe('设备')
  })

  it('未知类型码兜底「其他」，不渲染原始英文码', () => {
    expect(filterReasonLabel('unknown_type')).toBe('其他')
    expect(filterReasonLabel('')).toBe('其他')
  })
})
