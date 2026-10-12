/**
 * 文件职责：src/utils/cover.ts 纯函数单测（程序化占位封面色板稳定映射）。
 * 覆盖：同 id 同色（稳定映射）、id 0~15 按 8 色 0~7 循环、负数 id 安全（等同绝对值取模）、
 *       返回的 bg/fg 为成对非空合法 CSS 颜色字符串（对比度可读的前提）。
 * 运行方式：npm run test（vitest run，node 环境）。
 */
import { describe, expect, it } from 'vitest'
import { coverPalette } from '../cover'

describe('coverPalette 占位封面色板映射', () => {
  it('同 id 多次调用返回同色（稳定映射）', () => {
    expect(coverPalette(42)).toEqual(coverPalette(42))
    expect(coverPalette(0)).toEqual(coverPalette(0))
  })

  it('id 0~15 按 8 色循环（i 与 i+8 同色，0~7 八色互不相同）', () => {
    for (let i = 0; i < 8; i++) {
      expect(coverPalette(i)).toEqual(coverPalette(i + 8))
    }
    // 0~7 覆盖 8 种不同色板（bg+fg 成对去重）
    const distinct = new Set(
      Array.from({ length: 8 }, (_, i) => JSON.stringify(coverPalette(i))),
    )
    expect(distinct.size).toBe(8)
  })

  it('负数 id 安全：等同其绝对值取模', () => {
    expect(coverPalette(-3)).toEqual(coverPalette(3))
    expect(coverPalette(-11)).toEqual(coverPalette(3)) // |-11| % 8 = 3
    expect(coverPalette(-8)).toEqual(coverPalette(8)) // |-8| % 8 = 0
    expect(coverPalette(-1)).toEqual(coverPalette(1)) // |-1| % 8 = 1
  })

  it('返回的 bg 与 fg 成对且为非空合法 CSS 颜色字符串', () => {
    for (let id = -16; id < 16; id++) {
      const { bg, fg } = coverPalette(id)
      expect(typeof bg).toBe('string')
      expect(typeof fg).toBe('string')
      expect(bg.length).toBeGreaterThan(0)
      expect(fg.length).toBeGreaterThan(0)
      // 合法 CSS 颜色格式：#hex 或 rgb()/rgba() 函数式
      expect(bg.startsWith('#') || bg.startsWith('rgb')).toBe(true)
      expect(fg.startsWith('#') || fg.startsWith('rgb')).toBe(true)
    }
  })
})
