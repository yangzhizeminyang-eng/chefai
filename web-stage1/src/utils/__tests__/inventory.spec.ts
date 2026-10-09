/**
 * 文件职责：src/utils/inventory.ts 纯函数单测（P0 修复 H1 / L4-2 配套测试）。
 * 覆盖：位置枚举 ↔ 中文标签映射（四枚举逐项）、LOCATION_OPTIONS 双值结构
 *       （value 为后端枚举、label 为中文）、locationLabel（空值兜底 / 未知值原样）。
 * 运行方式：npm run test（vitest run，node 环境，不挂载组件）。
 */
import { describe, expect, it } from 'vitest'
import { LOCATION_LABELS, LOCATION_OPTIONS, locationLabel } from '../inventory'

describe('LOCATION_LABELS 位置枚举映射', () => {
  it('四个枚举值逐项映射为中文标签', () => {
    expect(LOCATION_LABELS.fridge).toBe('冷藏')
    expect(LOCATION_LABELS.freezer).toBe('冷冻')
    expect(LOCATION_LABELS.room).toBe('常温')
    expect(LOCATION_LABELS.dry).toBe('阴凉干燥')
  })

  it('恰好覆盖后端 StorageLocation 四值，不含中文标签键', () => {
    expect(Object.keys(LOCATION_LABELS).sort()).toEqual(['dry', 'freezer', 'fridge', 'room'])
  })
})

describe('LOCATION_OPTIONS 双值选项结构', () => {
  it('每项为 {label, value}：value 为后端枚举、label 为对应中文', () => {
    expect(LOCATION_OPTIONS).toEqual([
      { label: '冷藏', value: 'fridge' },
      { label: '冷冻', value: 'freezer' },
      { label: '常温', value: 'room' },
      { label: '阴凉干燥', value: 'dry' },
    ])
  })

  it('label 与 value 一一对应（label 必须来自 LOCATION_LABELS，防止两处文案漂移）', () => {
    for (const opt of LOCATION_OPTIONS) {
      expect(LOCATION_LABELS[opt.value]).toBe(opt.label)
    }
  })
})

describe('locationLabel 位置展示文案', () => {
  it('已知枚举返回中文标签', () => {
    expect(locationLabel('fridge')).toBe('冷藏')
    expect(locationLabel('freezer')).toBe('冷冻')
    expect(locationLabel('room')).toBe('常温')
    expect(locationLabel('dry')).toBe('阴凉干燥')
  })

  it('空值返回「位置未记录」兜底', () => {
    expect(locationLabel('')).toBe('位置未记录')
    expect(locationLabel(null)).toBe('位置未记录')
    expect(locationLabel(undefined)).toBe('位置未记录')
  })

  it('未知值原样返回（兼容历史脏数据，不吞异常内容）', () => {
    expect(locationLabel('balcony')).toBe('balcony')
  })
})
