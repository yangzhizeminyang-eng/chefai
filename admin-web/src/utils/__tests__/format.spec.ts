/**
 * 文件职责：format.ts 纯函数单测（金额分转元、日期格式化、千分位）。
 */
import { describe, expect, it } from 'vitest'

import { formatCents, formatDate, formatNumber, formatYuan } from '../format'

describe('formatCents 金额分转元', () => {
  it('常规金额', () => {
    expect(formatCents(12345)).toBe('123.45')
  })

  it('零元', () => {
    expect(formatCents(0)).toBe('0.00')
  })

  it('不足一元补前导零', () => {
    expect(formatCents(5)).toBe('0.05')
  })

  it('负数金额', () => {
    expect(formatCents(-12345)).toBe('-123.45')
  })

  it('小数分四舍五入', () => {
    expect(formatCents(1234.6)).toBe('12.35')
  })

  it('非法输入返回 0.00', () => {
    expect(formatCents(null)).toBe('0.00')
    expect(formatCents(undefined)).toBe('0.00')
    expect(formatCents(Number.NaN)).toBe('0.00')
  })
})

describe('formatYuan 金额展示', () => {
  it('带人民币符号', () => {
    expect(formatYuan(12345)).toBe('¥123.45')
  })
})

describe('formatDate 日期格式化', () => {
  it('默认 YYYY-MM-DD HH:mm:ss（本地时区构造，避免时区依赖）', () => {
    expect(formatDate(new Date(2026, 0, 5, 3, 7, 9))).toBe('2026-01-05 03:07:09')
  })

  it('自定义模板 YYYY/MM/DD', () => {
    expect(formatDate(new Date(2026, 10, 9), 'YYYY/MM/DD')).toBe('2026/11/09')
  })

  it('支持时间戳输入（本地时区构造）', () => {
    const ts = new Date(2024, 5, 1, 12, 0, 0).getTime()
    expect(formatDate(ts, 'YYYY-MM-DD HH:mm')).toBe('2024-06-01 12:00')
  })

  it('空值与非法值返回 -', () => {
    expect(formatDate(null)).toBe('-')
    expect(formatDate(undefined)).toBe('-')
    expect(formatDate('')).toBe('-')
    expect(formatDate('not-a-date')).toBe('-')
  })
})

describe('formatNumber 千分位', () => {
  it('千分位分隔', () => {
    expect(formatNumber(1234567)).toBe('1,234,567')
  })

  it('非法输入按 0 处理', () => {
    expect(formatNumber(null)).toBe('0')
    expect(formatNumber(undefined)).toBe('0')
  })
})
