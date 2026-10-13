/**
 * 文件职责：stores/ingredients.ts 已选食材持久化单测（S10/L2 修复验证；自
 * web-stage1/src/stores/__tests__/ingredients.spec.ts 迁移，断言值与用例语义保持一致）。
 * 覆盖：store 初始化恢复（正常 / 无数据 / JSON 损坏 / 脏数据过滤）、
 *       toggle 写回持久化、clear 写回空对象、恢复后 selectedCount 直通（/recommend 守卫前提）。
 * 适配说明：原 sessionStorage stubGlobal 改为 vi.mock('@/utils/storage') 内存 Map 实现
 * （set 内部 JSON 序列化、get 内部 JSON 反序列化与失败兜底，语义与真实 storage.ts 一致）；
 * 原断言 storage.getItem(JSON.parse) 相应改为 mem.get(JSON.parse)。
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { useIngredientsStore } from '@/stores/ingredients'

/** 持久化存储模拟容器（vi.hoisted 保证在 vi.mock 工厂执行前可用；值为 JSON 串，对齐真实落盘形态） */
const mem = vi.hoisted(() => new Map<string, string>())

/** 内存态存储模拟容器（profile 等敏感内存态用；本 spec 不直接断言） */
const memMem = vi.hoisted(() => new Map<string, unknown>())

/** 以内存 Map 模拟 @/utils/storage（get/set 走 JSON 序列化往返，语义与真实封装一致） */
vi.mock('@/utils/storage', () => ({
  ANONYMOUS_ID_KEY: 'aicook_anonymous_id',
  SCHEMA_VERSION: '1',
  get: (key: string): unknown => {
    const raw = mem.get(key)
    if (raw === undefined || raw === '') return undefined
    try {
      return JSON.parse(raw)
    } catch {
      // 损坏数据：与真实 storage.get 一致按缺失处理
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

/** 持久化键（须与 store 内 SELECTED_KEY 一致） */
const SELECTED_KEY = 'aicook_selected_ingredients_v1'

/**
 * 构造食材实体（toggle 入参最小工厂）。
 * @param id 食材 ID
 * @param name 食材名
 * @returns Ingredient 实体
 */
function makeIngredient(id: number, name: string): { id: number; name: string; category: string } {
  return { id, name, category: 'veg' }
}

beforeEach(() => {
  // 每个用例先清空存储模拟，再建全新 Pinia（store state 在首次 use 时初始化并读存储）
  mem.clear()
  memMem.clear()
  setActivePinia(createPinia())
})

afterEach(() => {
  vi.restoreAllMocks()
})

describe('ingredients store 已选食材持久化（S10/L2）', () => {
  it('初始化时从持久化存储恢复已选食材', () => {
    mem.set(
      SELECTED_KEY,
      JSON.stringify({
        1: { id: 1, name: '鸡蛋' },
        3: { id: 3, name: '番茄' },
      }),
    )
    setActivePinia(createPinia())
    const store = useIngredientsStore()
    expect(store.selectedCount).toBe(2)
    expect(store.selected[1]).toEqual({ id: 1, name: '鸡蛋' })
    expect(store.selected[3]).toEqual({ id: 3, name: '番茄' })
  })

  it('恢复后 selectedCount > 0（/recommend 路由守卫刷新后可直通）', () => {
    mem.set(SELECTED_KEY, JSON.stringify({ 7: { id: 7, name: '土豆' } }))
    setActivePinia(createPinia())
    const store = useIngredientsStore()
    expect(store.selectedCount).toBeGreaterThan(0)
    expect(store.selectedList.map((s) => s.id)).toContain(7)
  })

  it('持久化存储无数据时初始化为空选择', () => {
    const store = useIngredientsStore()
    expect(store.selectedCount).toBe(0)
  })

  it('持久化 JSON 损坏时回退空选择且不抛异常', () => {
    mem.set(SELECTED_KEY, 'not-valid-json{{')
    setActivePinia(createPinia())
    const store = useIngredientsStore()
    expect(store.selectedCount).toBe(0)
  })

  it('持久化数据结构非法（数组/标量）时回退空选择', () => {
    // 数组：非普通对象 → 回退空
    mem.set(SELECTED_KEY, '[1,2,3]')
    setActivePinia(createPinia())
    expect(useIngredientsStore().selectedCount).toBe(0)

    // 标量字符串：JSON.parse 结果非对象 → 回退空
    mem.set(SELECTED_KEY, '"str"')
    setActivePinia(createPinia())
    expect(useIngredientsStore().selectedCount).toBe(0)
  })

  it('持久化条目脏数据（id 非 number / name 非 string）被逐条过滤', () => {
    mem.set(
      SELECTED_KEY,
      JSON.stringify({
        1: { id: 'bad', name: '假数据' },
        2: { id: 2 },
        3: { id: 3, name: '小葱' },
      }),
    )
    setActivePinia(createPinia())
    const store = useIngredientsStore()
    expect(store.selectedCount).toBe(1)
    expect(store.selected[3]).toEqual({ id: 3, name: '小葱' })
  })

  it('toggle 选中后立即写回持久化存储', () => {
    const store = useIngredientsStore()
    store.toggle(makeIngredient(5, '青椒'))
    const raw = mem.get(SELECTED_KEY)
    expect(raw).not.toBeUndefined()
    expect(JSON.parse(raw as string)).toEqual({ 5: { id: 5, name: '青椒' } })
  })

  it('toggle 取消选中后同步写回（条目移除）', () => {
    mem.set(SELECTED_KEY, JSON.stringify({ 5: { id: 5, name: '青椒' } }))
    setActivePinia(createPinia())
    const store = useIngredientsStore()
    store.toggle(makeIngredient(5, '青椒'))
    expect(JSON.parse(mem.get(SELECTED_KEY) as string)).toEqual({})
  })

  it('clear 后持久化存储写回空对象', () => {
    mem.set(
      SELECTED_KEY,
      JSON.stringify({
        1: { id: 1, name: '鸡蛋' },
        2: { id: 2, name: '番茄' },
      }),
    )
    setActivePinia(createPinia())
    const store = useIngredientsStore()
    expect(store.selectedCount).toBe(2)
    store.clear()
    expect(store.selectedCount).toBe(0)
    expect(JSON.parse(mem.get(SELECTED_KEY) as string)).toEqual({})
  })
})
