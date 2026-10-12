/**
 * 文件职责：src/utils/today.ts 纯函数单测（add-home-entries-and-covers /today 页面）。
 * 覆盖：耗时口径三档分组（≤15 → fast / 16~30 → medium / >30 与 null → prep）、
 *       空档不返回、组内顺序保持、整体顺序固定 fast → medium → prep、
 *       输入空数组返回空数组、标题常量文案。
 * 运行方式：npm run test（vitest run，node 环境，不挂载组件）。
 */
import { describe, expect, it } from 'vitest'
import type { RecommendResultItem } from '@/api/types'
import { groupDayMenuByTime } from '../today'

/** 构造推荐结果条目的最小工厂（仅填分组相关字段，其余给默认值） */
function makeItem(overrides: Partial<RecommendResultItem>): RecommendResultItem {
  return {
    recipe_id: 1,
    title: '测试菜',
    match_level: 'can_cook_now',
    covered_ingredients: [],
    missing_ingredients: [],
    time_minutes: 10,
    difficulty: 'easy',
    calories_kcal: 100,
    allergens: [],
    required_equipment: [],
    rank_score: 1,
    rank_reasons: ['今天就可以安排上桌'],
    source: 'HowToCook',
    ...overrides,
  }
}

describe('groupDayMenuByTime 耗时口径三档分组', () => {
  it('≤15 分钟归入 fast 档', () => {
    const groups = groupDayMenuByTime([makeItem({ recipe_id: 1, time_minutes: 10 })])
    expect(groups).toHaveLength(1)
    expect(groups[0].key).toBe('fast')
    expect(groups[0].title).toBe('⏱ ≤15 分钟')
    expect(groups[0].items.map((i) => i.recipe_id)).toEqual([1])
  })

  it('15 分钟边界值归入 fast 档', () => {
    const groups = groupDayMenuByTime([makeItem({ recipe_id: 2, time_minutes: 15 })])
    expect(groups[0].key).toBe('fast')
  })

  it('16~30 分钟归入 medium 档', () => {
    const groups = groupDayMenuByTime([
      makeItem({ recipe_id: 3, time_minutes: 16 }),
      makeItem({ recipe_id: 4, time_minutes: 30 }),
    ])
    expect(groups).toHaveLength(1)
    expect(groups[0].key).toBe('medium')
    expect(groups[0].title).toBe('⏱ 15–30 分钟')
    expect(groups[0].items.map((i) => i.recipe_id)).toEqual([3, 4])
  })

  it('31 分钟以上归入 prep 档', () => {
    const groups = groupDayMenuByTime([makeItem({ recipe_id: 5, time_minutes: 31 })])
    expect(groups[0].key).toBe('prep')
    expect(groups[0].title).toBe('🛒 需备料')
  })

  it('time_minutes 为 null（未标注耗时）归入 prep 档，不误入 fast/medium', () => {
    const groups = groupDayMenuByTime([makeItem({ recipe_id: 6, time_minutes: null })])
    expect(groups).toHaveLength(1)
    expect(groups[0].key).toBe('prep')
    expect(groups[0].items.map((i) => i.recipe_id)).toEqual([6])
  })

  it('空档不返回：仅出现非空分组', () => {
    const groups = groupDayMenuByTime([
      makeItem({ recipe_id: 1, time_minutes: 5 }),
      makeItem({ recipe_id: 2, time_minutes: 45 }),
    ])
    expect(groups.map((g) => g.key)).toEqual(['fast', 'prep'])
  })

  it('整体顺序固定 fast → medium → prep', () => {
    // 故意按 prep → medium → fast 的输入顺序传入，验证输出仍按固定顺序
    const groups = groupDayMenuByTime([
      makeItem({ recipe_id: 7, time_minutes: 60 }),
      makeItem({ recipe_id: 8, time_minutes: 20 }),
      makeItem({ recipe_id: 9, time_minutes: 10 }),
    ])
    expect(groups.map((g) => g.key)).toEqual(['fast', 'medium', 'prep'])
  })

  it('组内条目保持原数组顺序', () => {
    const groups = groupDayMenuByTime([
      makeItem({ recipe_id: 11, time_minutes: 12 }),
      makeItem({ recipe_id: 10, time_minutes: 8 }),
    ])
    expect(groups[0].items.map((i) => i.recipe_id)).toEqual([11, 10])
  })

  it('输入空数组返回空数组', () => {
    expect(groupDayMenuByTime([])).toEqual([])
  })
})
