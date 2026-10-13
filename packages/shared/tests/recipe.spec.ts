/**
 * 文件职责：src/utils/recipe.ts 纯函数单测（Task 11.1）。
 * 覆盖：用量线性缩放（小数/边界）、量化展示（单值/区间/勺参照/null）、
 *       数字难度映射（1~5 与越界回退）、推荐结果三档分组（含未知档过滤、顺序保持、空数组）、
 *       覆盖率计算（正常/空分母/全缺失/全覆盖）、GB7718 致敏原映射（八类与未知编码）、
 *       成本分→元格式化（0/精度/null）。
 * 运行方式：npm run test（vitest run，node 环境，不挂载组件）。
 * 从 web-stage1/src/utils/__tests__/recipe.spec.ts 零改造迁移（仅本文件级注释追加迁移说明、
 * 导入路径改为 ../src/types/api 与 ../src/utils/recipe），用例与断言保持原样。
 */
import { describe, expect, it } from 'vitest'
import type { RecommendResultItem } from '../src/types/api'
import {
  allergenLabel,
  amountText,
  coveragePercent,
  difficultyLabel,
  formatCost,
  groupResults,
  scaleAmount,
} from '../src/utils/recipe'

/** 构造推荐结果条目的最小工厂（仅填分组相关字段，其余给默认值） */
function makeItem(overrides: Partial<RecommendResultItem>): RecommendResultItem {
  return {
    recipe_id: 1,
    title: '测试菜',
    match_level: 'can_cook_now',
    covered_ingredients: ['鸡蛋'],
    missing_ingredients: [],
    time_minutes: 10,
    difficulty: 'easy',
    calories_kcal: 100,
    allergens: [],
    required_equipment: [],
    rank_score: 1,
    rank_reasons: ['用掉 1 样你现有的食材'],
    source: 'HowToCook',
    ...overrides,
  }
}

describe('scaleAmount 用量线性缩放', () => {
  it('整数用量按系数翻倍', () => {
    expect(scaleAmount(100, 2)).toBe(200)
  })

  it('null 透传为 null（不按 0 计）', () => {
    expect(scaleAmount(null, 2)).toBeNull()
  })

  it('缩放结果保留 1 位小数（规避浮点误差）', () => {
    expect(scaleAmount(0.3, 3)).toBe(0.9)
    expect(scaleAmount(2.35, 2)).toBe(4.7)
  })

  it('系数为 1 时原值不变，系数为 0 时归零', () => {
    expect(scaleAmount(150, 1)).toBe(150)
    expect(scaleAmount(150, 0)).toBe(0)
  })
})

describe('amountText 量化展示', () => {
  it('单值 + 单位 → 「100g」', () => {
    expect(amountText({ amount_value: 100, amount_unit: 'g' })).toBe('100g')
  })

  it('区间用量 → 「300–500g」（en dash 连接）', () => {
    expect(amountText({ amount_min: 300, amount_max: 500, amount_unit: 'g' })).toBe('300–500g')
  })

  it('区间 min==max 时按单值展示', () => {
    expect(amountText({ amount_min: 50, amount_max: 50, amount_unit: 'g' })).toBe('50g')
  })

  it('单值 + 勺单位 + 勺参照说明 → 「2 勺（1 勺 ≈ 15ml）」', () => {
    expect(
      amountText({ amount_value: 2, amount_unit: '勺', amount_note: '1 勺 ≈ 15ml' }),
    ).toBe('2 勺（1 勺 ≈ 15ml）')
  })

  it('无单位时仅展示数值，无说明时不追加括号', () => {
    expect(amountText({ amount_value: 3 })).toBe('3')
  })

  it('全部字段为 null/缺省 → 空串', () => {
    expect(amountText({})).toBe('')
    expect(amountText({ amount_value: null, amount_min: null, amount_max: null })).toBe('')
  })
})

describe('difficultyLabel 数字难度映射', () => {
  it('1~5 逐档映射正确', () => {
    expect(difficultyLabel(1)).toBe('简单')
    expect(difficultyLabel(2)).toBe('容易')
    expect(difficultyLabel(3)).toBe('中等')
    expect(difficultyLabel(4)).toBe('较难')
    expect(difficultyLabel(5)).toBe('困难')
  })

  it('越界（0 / 6 / 非整数档位）回退「中等」', () => {
    expect(difficultyLabel(0)).toBe('中等')
    expect(difficultyLabel(6)).toBe('中等')
    expect(difficultyLabel(3.7)).toBe('中等')
  })
})

describe('groupResults 三档分组', () => {
  it('按 match_level 分入对应三档且档内保持原顺序', () => {
    const a = makeItem({ recipe_id: 1, match_level: 'need_more' })
    const b = makeItem({ recipe_id: 2, match_level: 'can_cook_now' })
    const c = makeItem({ recipe_id: 3, match_level: 'missing_1_2' })
    const d = makeItem({ recipe_id: 4, match_level: 'can_cook_now' })
    const grouped = groupResults([a, b, c, d])
    expect(grouped.can_cook_now.map((r) => r.recipe_id)).toEqual([2, 4])
    expect(grouped.missing_1_2.map((r) => r.recipe_id)).toEqual([3])
    expect(grouped.need_more.map((r) => r.recipe_id)).toEqual([1])
  })

  it('未知 match_level 条目被过滤，不落入任何档', () => {
    // 类型适配：ghost 的 'unknown' 档位不在联合类型内，strict 下经 as unknown as 双跳（运行时语义不变）
    const ghost = { ...makeItem({ recipe_id: 9 }), match_level: 'unknown' } as unknown as RecommendResultItem
    const grouped = groupResults([ghost, makeItem({ recipe_id: 1 })])
    expect(grouped.can_cook_now).toHaveLength(1)
    expect(grouped.missing_1_2).toHaveLength(0)
    expect(grouped.need_more).toHaveLength(0)
  })

  it('空数组 → 三档均为空数组', () => {
    expect(groupResults([])).toEqual({
      can_cook_now: [],
      missing_1_2: [],
      need_more: [],
    })
  })
})

describe('coveragePercent 覆盖率', () => {
  it('常规比例四舍五入为整数（3/4 → 75）', () => {
    expect(coveragePercent(['a', 'b', 'c'], ['d'])).toBe(75)
  })

  it('两个列表均空（分母为 0）→ 返回 0', () => {
    expect(coveragePercent([], [])).toBe(0)
  })

  it('全部缺失 → 0%；全部覆盖 → 100%', () => {
    expect(coveragePercent([], ['a', 'b'])).toBe(0)
    expect(coveragePercent(['a', 'b', 'c'], [])).toBe(100)
  })

  it('非整除时四舍五入（1/3 → 33）', () => {
    expect(coveragePercent(['a'], ['b', 'c'])).toBe(33)
  })
})

describe('allergenLabel GB7718 致敏原映射', () => {
  it('八类编码逐项映射正确', () => {
    expect(allergenLabel('gluten')).toBe('含麸质谷物')
    expect(allergenLabel('crustacean')).toBe('甲壳类')
    expect(allergenLabel('fish')).toBe('鱼类')
    expect(allergenLabel('egg')).toBe('蛋类')
    expect(allergenLabel('peanut')).toBe('花生')
    expect(allergenLabel('soybean')).toBe('大豆')
    expect(allergenLabel('milk')).toBe('乳制品')
    expect(allergenLabel('nuts')).toBe('坚果')
  })

  it('未知编码原样返回', () => {
    expect(allergenLabel('sesame')).toBe('sesame')
  })
})

describe('formatCost 成本分→元', () => {
  it('21 分 → ¥0.2100（保留 4 位）', () => {
    expect(formatCost(21)).toBe('¥0.2100')
  })

  it('0 分 → ¥0.0000；小数值精度正确', () => {
    expect(formatCost(0)).toBe('¥0.0000')
    expect(formatCost(1)).toBe('¥0.0100')
  })

  it('null → 「-」', () => {
    expect(formatCost(null)).toBe('-')
  })
})
