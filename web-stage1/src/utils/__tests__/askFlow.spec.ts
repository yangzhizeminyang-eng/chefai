/**
 * 文件职责：src/utils/askFlow.ts 纯函数单测（修复「问厨娘闭环断裂」Task 2）。
 * 覆盖意图分流三主路径与边界：
 * - 空输入守卫（isBlankQuestion：空输入不发请求，仅提示）；
 * - blocked 短路分流（保持既有 W-05 跳转行为）；
 * - recipe_search 落 store 分流（recipe_ids 透传；ids 缺失/为空归入 chat 兜底）；
 * - chat 就地展示分流（free_qa 带 answer / 无 answer / 未知意图兜底）；
 * - recipeDetailToAskItem 详情→推荐卡片映射（字段映射与溯源问句）。
 * 运行方式：npm run test（vitest run，node 环境，不挂载组件）。
 */
import { describe, expect, it } from 'vitest'
import type { AskResponse, BlockedResponse, RecipeDetail } from '@/api/types'
import {
  EMPTY_ANSWER,
  NO_RECIPE_ANSWER,
  isBlankQuestion,
  recipeDetailToAskItem,
  resolveAskAction,
} from '../askFlow'

/** 构造 AskResponse 的最小工厂（默认 recipe_search 正常体，测试按需覆盖字段） */
function makeAskResponse(overrides: Partial<AskResponse>): AskResponse {
  return {
    request_id: 'req_test',
    intent: 'recipe_search',
    trace_id: 'trace_test',
    disclaimer_id: 'DISCLAIMER_V1',
    ...overrides,
  }
}

/** 构造 BlockedResponse 的最小工厂（仅 blocked 分流所需字段） */
function makeBlocked(): BlockedResponse {
  return {
    request_id: 'req_blocked',
    blocked: true,
    overrides_all: true,
    risk: {
      category: 'food_safety_high_risk',
      rule_code: 'FS-018',
      risk_level: 'high',
      message_id: 'M_FS_018',
      title: '风险提示',
      body: '正文',
      correct_action: '正确做法',
      after_consumption_advice: '就医引导',
      evidence_ref: ['FS-018@rules-v1.2'],
    },
    disclaimer_id: 'DISCLAIMER_V1',
    trace_id: 'trace_blocked',
  }
}

/** 构造 RecipeDetail 的最小工厂（仅映射所需字段，其余给默认空值） */
function makeDetail(overrides: Partial<RecipeDetail>): RecipeDetail {
  return {
    id: 1,
    title: '西红柿炒鸡蛋',
    difficulty: 'easy',
    time_minutes: 10,
    servings: 2,
    calories_kcal: 150,
    allergen_codes: ['egg'],
    equipment: ['炒锅'],
    main_ingredients: [],
    side_ingredients: [],
    seasoning_ingredients: [],
    steps: [],
    substitutes: [],
    tips: [],
    source_label: 'HowToCook',
    ...overrides,
  }
}

describe('isBlankQuestion 空输入守卫', () => {
  it('空串与纯空白 → true（不发请求，仅提示「请输入内容」）', () => {
    expect(isBlankQuestion('')).toBe(true)
    expect(isBlankQuestion('   ')).toBe(true)
    expect(isBlankQuestion('\t\n')).toBe(true)
  })

  it('非空白输入 → false（允许发起 ask 请求）', () => {
    expect(isBlankQuestion('家里有鸡蛋和西红柿能做什么菜')).toBe(false)
    expect(isBlankQuestion(' 鸡蛋 ')).toBe(false)
  })
})

describe('resolveAskAction 意图分流', () => {
  it('blocked 短路体 → blocked 分流，payload 透传（保持 W-05 跳转行为）', () => {
    const blocked = makeBlocked()
    const action = resolveAskAction(makeAskResponse({ intent: 'blocked', blocked }))
    expect(action).toEqual({ type: 'blocked', payload: blocked })
  })

  it('recipe_search 且有 recipe_ids → recipe_search 分流，ids 顺序透传', () => {
    const ids = [1, 397, 2129, 33, 2130, 2074, 2020, 2118]
    const action = resolveAskAction(makeAskResponse({ intent: 'recipe_search', recipe_ids: ids }))
    expect(action).toEqual({ type: 'recipe_search', recipeIds: ids })
  })

  it('recipe_search 但 recipe_ids 为 undefined → chat 兜底（搜索无结果文案）', () => {
    const action = resolveAskAction(makeAskResponse({ intent: 'recipe_search', recipe_ids: undefined }))
    expect(action).toEqual({ type: 'chat', answer: NO_RECIPE_ANSWER })
  })

  it('recipe_search 但 recipe_ids 为空数组 → chat 兜底（搜索无结果文案）', () => {
    const action = resolveAskAction(makeAskResponse({ intent: 'recipe_search', recipe_ids: [] }))
    expect(action).toEqual({ type: 'chat', answer: NO_RECIPE_ANSWER })
  })

  it('free_qa 且有 answer → chat 就地展示（answer 原文透传）', () => {
    const action = resolveAskAction(
      makeAskResponse({ intent: 'free_qa', answer: '生鸡蛋不建议直接吃，有沙门氏菌风险。' }),
    )
    expect(action).toEqual({ type: 'chat', answer: '生鸡蛋不建议直接吃，有沙门氏菌风险。' })
  })

  it('free_qa 但 answer 缺失 → chat 通用兜底文案', () => {
    const action = resolveAskAction(makeAskResponse({ intent: 'free_qa', answer: undefined }))
    expect(action).toEqual({ type: 'chat', answer: EMPTY_ANSWER })
  })

  it('未知意图（recommend 等，无消费负载）→ chat 兜底，不做跳转', () => {
    const action = resolveAskAction(makeAskResponse({ intent: 'recommend' }))
    expect(action).toEqual({ type: 'chat', answer: EMPTY_ANSWER })
  })
})

describe('recipeDetailToAskItem 详情→推荐卡片映射', () => {
  it('核心展示字段正确映射，溯源问句写入 rank_reasons', () => {
    const item = recipeDetailToAskItem(makeDetail({ id: 397, title: '西红柿炒鸡蛋' }), '鸡蛋和西红柿做什么')
    expect(item.recipe_id).toBe(397)
    expect(item.title).toBe('西红柿炒鸡蛋')
    expect(item.match_level).toBe('can_cook_now')
    expect(item.time_minutes).toBe(10)
    expect(item.difficulty).toBe('easy')
    expect(item.calories_kcal).toBe(150)
    expect(item.allergens).toEqual(['egg'])
    expect(item.required_equipment).toEqual(['炒锅'])
    expect(item.source).toBe('HowToCook')
    expect(item.rank_reasons).toEqual(['来自你的提问「鸡蛋和西红柿做什么」'])
  })

  it('ask 链路无食材匹配信息：covered/missing 置空（卡片不展示覆盖率）', () => {
    const item = recipeDetailToAskItem(makeDetail(), '随便')
    expect(item.covered_ingredients).toEqual([])
    expect(item.missing_ingredients).toEqual([])
    expect(item.rank_score).toBe(0)
  })

  it('热量为 null（未纳入统计）时原样透传', () => {
    const item = recipeDetailToAskItem(makeDetail({ calories_kcal: null }), '随便')
    expect(item.calories_kcal).toBeNull()
  })
})
