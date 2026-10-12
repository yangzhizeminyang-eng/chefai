/**
 * 文件职责：src/utils/seasonal.ts 纯函数单测（时令页选中集合增删 + 月份副标题文案）。
 * 覆盖：toggleSeasonalId 增/删/幂等/不可变（不改原集合）；seasonalSubtitle 合法月份带数字、
 *       未加载与越界/非整数回退为无月份数字文案。
 * 运行方式：npm run test（vitest run，node 环境）。
 */
import { describe, expect, it } from 'vitest'
import { seasonalSubtitle, toggleSeasonalId } from '../seasonal'

describe('toggleSeasonalId 选中集合增删', () => {
  it('未选 → 加入：返回包含该 id 的新集合', () => {
    const next = toggleSeasonalId(new Set([1, 2]), 3)
    expect(next.has(3)).toBe(true)
    expect([...next].sort()).toEqual([1, 2, 3])
  })

  it('已选 → 移除：返回不含该 id 的新集合', () => {
    const next = toggleSeasonalId(new Set([1, 2, 3]), 2)
    expect(next.has(2)).toBe(false)
    expect([...next].sort()).toEqual([1, 3])
  })

  it('幂等：对同一 id 连续两次 toggle 回到初始集合', () => {
    const init = new Set([7, 8])
    const once = toggleSeasonalId(init, 7)
    expect(once.has(7)).toBe(false)
    const twice = toggleSeasonalId(once, 7)
    expect([...twice].sort()).toEqual([7, 8])
  })

  it('不可变：原集合不被修改（返回新 Set）', () => {
    const init = new Set([1])
    const next = toggleSeasonalId(init, 1)
    expect(init.has(1)).toBe(true)
    expect(next).not.toBe(init)
  })
})

describe('seasonalSubtitle 月份副标题文案', () => {
  it('合法月份 1~12 显示「N 月 · 当季食材」', () => {
    expect(seasonalSubtitle(1)).toBe('1 月 · 当季食材')
    expect(seasonalSubtitle(10)).toBe('10 月 · 当季食材')
    expect(seasonalSubtitle(12)).toBe('12 月 · 当季食材')
  })

  it('未加载（null/undefined）不显示月份数字', () => {
    expect(seasonalSubtitle(null)).toBe('当季食材')
    expect(seasonalSubtitle(undefined)).toBe('当季食材')
  })

  it('越界（0/13）与非整数（10.5/NaN）回退为无月份数字文案', () => {
    expect(seasonalSubtitle(0)).toBe('当季食材')
    expect(seasonalSubtitle(13)).toBe('当季食材')
    expect(seasonalSubtitle(10.5)).toBe('当季食材')
    expect(seasonalSubtitle(Number.NaN)).toBe('当季食材')
  })
})
