/**
 * 文件职责：src/utils/unit.ts 纯函数单测（DEF-09 回归）。
 * 覆盖：formatAmount 三模式（克 / 毫升 / 勺）与换算边界（半档、茶匙档、
 *       大体积上限、0/负数、未知单位、非有限数值）、
 *       formatAmountText 文本片段转换（spoon 模式换算 ml、克/毫升模式原样、
 *       g 类与未知单位保持）、migrateUnitSetting 键迁移（metric→gram、
 *       imperial→milliliter、新值直通、未知值兜底）。
 * 运行方式：npm run test（vitest run，node 环境，不挂载组件）。
 */
import { describe, expect, it } from 'vitest'
import { formatAmount, formatAmountText, migrateUnitSetting } from '../unit'

describe('formatAmount 克 / 毫升模式（原值展示）', () => {
  it('gram 模式 g 类原值展示', () => {
    expect(formatAmount(100, 'g', 'gram')).toBe('100g')
  })

  it('gram 模式中文单位数值间补空格', () => {
    expect(formatAmount(2, '勺', 'gram')).toBe('2 勺')
  })

  it('milliliter 模式 ml 类原值展示', () => {
    expect(formatAmount(200, 'ml', 'milliliter')).toBe('200ml')
  })

  it('gram 模式 ml 类同样按原值展示（不跨类别换算）', () => {
    expect(formatAmount(30, 'ml', 'gram')).toBe('30ml')
  })
})

describe('formatAmount 勺模式（ml → 勺 / 茶匙就近半档）', () => {
  it('15ml → 1 勺并附注参照', () => {
    expect(formatAmount(15, 'ml', 'spoon')).toBe('1 勺（1 勺 ≈ 15ml）')
  })

  it('22.5ml → 1.5 勺（就近半档）', () => {
    expect(formatAmount(22.5, 'ml', 'spoon')).toBe('1.5 勺（1 勺 ≈ 15ml）')
  })

  it('5ml → 1 茶匙（小于半勺走茶匙档）', () => {
    expect(formatAmount(5, 'ml', 'spoon')).toBe('1 茶匙（1 勺 ≈ 15ml）')
  })

  it('2.5ml → 0.5 茶匙（茶匙档半档）', () => {
    expect(formatAmount(2.5, 'ml', 'spoon')).toBe('0.5 茶匙（1 勺 ≈ 15ml）')
  })

  it('升换算：0.02L(20ml) → 1.5 勺', () => {
    expect(formatAmount(0.02, 'L', 'spoon')).toBe('1.5 勺（1 勺 ≈ 15ml）')
  })

  it('大体积保持原值（≥10 勺不换算）', () => {
    expect(formatAmount(500, 'ml', 'spoon')).toBe('500ml')
  })

  it('g 类在 spoon 模式保持克展示', () => {
    expect(formatAmount(100, 'g', 'spoon')).toBe('100g')
  })
})

describe('formatAmount 边界兜底', () => {
  it('未知单位原样返回', () => {
    expect(formatAmount(2, '个', 'spoon')).toBe('2 个')
  })

  it('0 值原样返回（不产出「0 勺」）', () => {
    expect(formatAmount(0, 'ml', 'spoon')).toBe('0ml')
  })

  it('负数原样返回', () => {
    expect(formatAmount(-10, 'g', 'gram')).toBe('-10g')
  })

  it('非有限数值返回空串', () => {
    expect(formatAmount(Number.NaN, 'g', 'gram')).toBe('')
    expect(formatAmount(Number.POSITIVE_INFINITY, 'ml', 'spoon')).toBe('')
  })

  it('空单位仅返回数值', () => {
    expect(formatAmount(100, '', 'gram')).toBe('100')
  })
})

describe('formatAmountText 文本片段转换', () => {
  it('spoon 模式仅换算 ml 类片段，g 类与未知单位保持原样', () => {
    expect(formatAmountText('盐 2g；水 30ml；葱花 1 个', 'spoon')).toBe(
      '盐 2g；水 2 勺（1 勺 ≈ 15ml）；葱花 1 个',
    )
  })

  it('gram / milliliter 模式文本原样返回', () => {
    expect(formatAmountText('盐 2g；水 30ml', 'gram')).toBe('盐 2g；水 30ml')
    expect(formatAmountText('盐 2g；水 30ml', 'milliliter')).toBe('盐 2g；水 30ml')
  })

  it('空文本原样返回', () => {
    expect(formatAmountText('', 'spoon')).toBe('')
  })
})

describe('migrateUnitSetting 设置键迁移', () => {
  it('历史值 metric → gram', () => {
    expect(migrateUnitSetting('metric')).toBe('gram')
  })

  it('历史值 imperial → milliliter', () => {
    expect(migrateUnitSetting('imperial')).toBe('milliliter')
  })

  it('新值直通（gram / milliliter / spoon）', () => {
    expect(migrateUnitSetting('gram')).toBe('gram')
    expect(migrateUnitSetting('milliliter')).toBe('milliliter')
    expect(migrateUnitSetting('spoon')).toBe('spoon')
  })

  it('空值 / 未知值兜底默认 gram', () => {
    expect(migrateUnitSetting('')).toBe('gram')
    expect(migrateUnitSetting('unknown')).toBe('gram')
    expect(migrateUnitSetting(null)).toBe('gram')
    expect(migrateUnitSetting(undefined)).toBe('gram')
  })
})
