/**
 * 文件职责：stores/ingredients.ts 已选食材 sessionStorage 持久化单测（S10/L2 修复验证）。
 * 覆盖：store 初始化恢复（正常 / 无数据 / JSON 损坏 / 脏数据过滤）、
 *       toggle 写回 sessionStorage、clear 写回空对象、恢复后 selectedCount 直通（/recommend 守卫前提）。
 * 运行方式：npm run test（vitest run，node 环境；sessionStorage 以 stubGlobal 模拟）。
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { useIngredientsStore } from '../ingredients'
import type { Ingredient } from '@/api/types'

/** sessionStorage 持久化键（须与 store 内 SELECTED_KEY 一致） */
const SELECTED_KEY = 'aicook_selected_ingredients_v1'

/**
 * 构造可编程的 sessionStorage 模拟对象（node 环境无 Web Storage API）。
 * @param initial 初始键值对（默认空）
 * @returns 含 getItem/setItem 的最小 Storage 模拟
 */
function createSessionStorageMock(initial: Record<string, string> = {}) {
  const map = new Map(Object.entries(initial))
  return {
    getItem: (key: string): string | null => (map.has(key) ? (map.get(key) as string) : null),
    setItem: (key: string, value: string): void => {
      map.set(key, value)
    },
    removeItem: (key: string): void => {
      map.delete(key)
    },
    clear: (): void => {
      map.clear()
    },
  }
}

/**
 * 构造食材实体（toggle 入参最小工厂）。
 * @param id 食材 ID
 * @param name 食材名
 * @returns Ingredient 实体
 */
function makeIngredient(id: number, name: string): Ingredient {
  return { id, name, category: 'veg' }
}

beforeEach(() => {
  // 每个用例先挂载干净的 sessionStorage 模拟，再建全新 Pinia（store state 在首次 use 时初始化）
  vi.stubGlobal('sessionStorage', createSessionStorageMock())
  setActivePinia(createPinia())
})

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('ingredients store 已选食材持久化（S10/L2）', () => {
  it('初始化时从 sessionStorage 恢复已选食材', () => {
    vi.stubGlobal(
      'sessionStorage',
      createSessionStorageMock({
        [SELECTED_KEY]: JSON.stringify({
          1: { id: 1, name: '鸡蛋' },
          3: { id: 3, name: '番茄' },
        }),
      }),
    )
    setActivePinia(createPinia())
    const store = useIngredientsStore()
    expect(store.selectedCount).toBe(2)
    expect(store.selected[1]).toEqual({ id: 1, name: '鸡蛋' })
    expect(store.selected[3]).toEqual({ id: 3, name: '番茄' })
  })

  it('恢复后 selectedCount > 0（/recommend 路由守卫刷新后可直通）', () => {
    vi.stubGlobal(
      'sessionStorage',
      createSessionStorageMock({ [SELECTED_KEY]: JSON.stringify({ 7: { id: 7, name: '土豆' } }) }),
    )
    setActivePinia(createPinia())
    const store = useIngredientsStore()
    expect(store.selectedCount).toBeGreaterThan(0)
    expect(store.selectedList.map((s) => s.id)).toContain(7)
  })

  it('sessionStorage 无数据时初始化为空选择', () => {
    const store = useIngredientsStore()
    expect(store.selectedCount).toBe(0)
  })

  it('持久化 JSON 损坏时回退空选择且不抛异常', () => {
    vi.stubGlobal('sessionStorage', createSessionStorageMock({ [SELECTED_KEY]: 'not-valid-json{{' }))
    setActivePinia(createPinia())
    const store = useIngredientsStore()
    expect(store.selectedCount).toBe(0)
  })

  it('持久化数据结构非法（数组/标量）时回退空选择', () => {
    // 数组：非普通对象 → 回退空
    vi.stubGlobal('sessionStorage', createSessionStorageMock({ [SELECTED_KEY]: '[1,2,3]' }))
    setActivePinia(createPinia())
    expect(useIngredientsStore().selectedCount).toBe(0)

    // 标量字符串：JSON.parse 结果非对象 → 回退空
    vi.stubGlobal('sessionStorage', createSessionStorageMock({ [SELECTED_KEY]: '"str"' }))
    setActivePinia(createPinia())
    expect(useIngredientsStore().selectedCount).toBe(0)
  })

  it('持久化条目脏数据（id 非 number / name 非 string）被逐条过滤', () => {
    vi.stubGlobal(
      'sessionStorage',
      createSessionStorageMock({
        [SELECTED_KEY]: JSON.stringify({
          1: { id: 'bad', name: '假数据' },
          2: { id: 2 },
          3: { id: 3, name: '小葱' },
        }),
      }),
    )
    setActivePinia(createPinia())
    const store = useIngredientsStore()
    expect(store.selectedCount).toBe(1)
    expect(store.selected[3]).toEqual({ id: 3, name: '小葱' })
  })

  it('toggle 选中后立即写回 sessionStorage', () => {
    const storage = createSessionStorageMock()
    vi.stubGlobal('sessionStorage', storage)
    setActivePinia(createPinia())
    const store = useIngredientsStore()
    store.toggle(makeIngredient(5, '青椒'))
    const raw = storage.getItem(SELECTED_KEY)
    expect(raw).not.toBeNull()
    expect(JSON.parse(raw as string)).toEqual({ 5: { id: 5, name: '青椒' } })
  })

  it('toggle 取消选中后同步写回（条目移除）', () => {
    const storage = createSessionStorageMock({
      [SELECTED_KEY]: JSON.stringify({ 5: { id: 5, name: '青椒' } }),
    })
    vi.stubGlobal('sessionStorage', storage)
    setActivePinia(createPinia())
    const store = useIngredientsStore()
    store.toggle(makeIngredient(5, '青椒'))
    expect(JSON.parse(storage.getItem(SELECTED_KEY) as string)).toEqual({})
  })

  it('clear 后 sessionStorage 写回空对象', () => {
    const storage = createSessionStorageMock({
      [SELECTED_KEY]: JSON.stringify({
        1: { id: 1, name: '鸡蛋' },
        2: { id: 2, name: '番茄' },
      }),
    })
    vi.stubGlobal('sessionStorage', storage)
    setActivePinia(createPinia())
    const store = useIngredientsStore()
    expect(store.selectedCount).toBe(2)
    store.clear()
    expect(store.selectedCount).toBe(0)
    expect(JSON.parse(storage.getItem(SELECTED_KEY) as string)).toEqual({})
  })
})
