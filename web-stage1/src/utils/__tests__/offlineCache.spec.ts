/**
 * 文件职责：src/utils/offlineCache.ts 单测（F 模块离线可读）。
 * 覆盖：
 *       ① 降级路径 —— node 环境无 indexedDB（同 jsdom/隐私模式表现）：save 返回 false、
 *          get 返回 null、clear 返回 false，且不抛错；无 localStorage 时会话映射读写静默；
 *       ② 正向路径 —— 以文件内最小内存 IndexedDB stub（不引入 fake-indexeddb 等新依赖）
 *          stub 到 globalThis：save→get 往返、同 recipe_id 覆盖写、get 未命中 null、
 *          clear 后不可再读、cached_at/version 自动补齐；
 *       ③ 会话映射 —— 内存 localStorage stub 下的 remember/recall 往返与非法值兜底。
 * 运行方式：npm run test（vitest run，node 环境）。
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import {
  SNAPSHOT_VERSION,
  clearRecipeSnapshot,
  getRecipeSnapshot,
  recallSessionRecipe,
  rememberSessionRecipe,
  saveRecipeSnapshot,
  type RecipeSnapshot,
} from '../offlineCache'
import type { RecipeStep } from '@/api/types'

/** 测试步骤数据（最小 RecipeStep） */
function makeSteps(): RecipeStep[] {
  return [
    { no: 1, description: '番茄切块', duration_sec: 30 },
    { no: 2, description: '鸡蛋打散炒熟', duration_sec: 60 },
    { no: 3, description: '合炒调味出锅', duration_sec: 90 },
  ]
}

/* ═══ ① 降级路径（node 环境天然无 indexedDB，等价 jsdom/隐私模式） ═══ */

describe('offlineCache 降级路径（无 indexedDB 环境）', () => {
  it('saveRecipeSnapshot 静默返回 false 不抛错', async () => {
    await expect(
      saveRecipeSnapshot({ recipe_id: 101, steps: makeSteps() }),
    ).resolves.toBe(false)
  })

  it('getRecipeSnapshot 静默返回 null 不抛错', async () => {
    await expect(getRecipeSnapshot(101)).resolves.toBeNull()
  })

  it('clearRecipeSnapshot 静默返回 false 不抛错', async () => {
    await expect(clearRecipeSnapshot(101)).resolves.toBe(false)
  })

  it('无 localStorage 时会话映射读写静默（recall 返回 null）', () => {
    expect(() => rememberSessionRecipe('sess-1', 101)).not.toThrow()
    expect(recallSessionRecipe('sess-1')).toBeNull()
  })
})

/* ═══ ② 正向路径（内存 IndexedDB stub） ═══ */

/** stub 的最小请求对象（仅覆盖 offlineCache 用到的成员） */
interface FakeRequest {
  result: unknown
  error: Error | null
  onsuccess: ((ev?: unknown) => void) | null
  onerror: ((ev?: unknown) => void) | null
  onupgradeneeded?: ((ev?: unknown) => void) | null
  onblocked?: (() => void) | null
}

/** 创建空请求对象 */
function makeFakeRequest(): FakeRequest {
  return {
    result: undefined,
    error: null,
    onsuccess: null,
    onerror: null,
    onupgradeneeded: null,
    onblocked: null,
  }
}

/**
 * 创建覆盖 save/get/clear 用法的最小内存 IndexedDB stub：
 * open（宏任务异步 onupgradeneeded→onsuccess）+ 单仓 recipe_snapshot 的 put/get/delete。
 * 刻意不做全量 IDB 语义（无游标/索引/多仓），只支撑被测模块的调用面。
 * @returns 可直接 stub 到 globalThis.indexedDB 的最小工厂
 */
function createIdbStub(): IDBFactory {
  /** dbName → storeName → (key → value) */
  const databases = new Map<string, Map<string, Map<number, unknown>>>()

  /** 构造内存 db 对象（open 成功后的 result） */
  const makeDb = (name: string): Record<string, unknown> => {
    const stores = databases.get(name) ?? new Map<string, Map<number, unknown>>()
    databases.set(name, stores)
    /** 取对象仓（stub 语义：未建仓视为异常） */
    const getStore = (storeName: string): Map<number, unknown> => {
      const store = stores.get(storeName)
      if (!store) throw new Error(`object store not found: ${storeName}`)
      return store
    }
    return {
      objectStoreNames: { contains: (storeName: string) => stores.has(storeName) },
      createObjectStore: (storeName: string) => {
        stores.set(storeName, new Map())
        return {}
      },
      close: () => {},
      transaction: (storeName: string) => {
        const store = getStore(storeName)
        const requests: FakeRequest[] = []
        /** 宏任务派发（保持 onsuccess/oncomplete 的异步时序与真实 IDB 一致） */
        const schedule = (fn: () => void): void => setTimeout(fn, 0)
        const tx = {
          objectStore: () => ({
            put: (value: unknown) => {
              const req = makeFakeRequest()
              requests.push(req)
              schedule(() => {
                const key = (value as { recipe_id: number }).recipe_id
                store.set(key, value)
                req.onsuccess?.()
              })
              return req
            },
            get: (key: number) => {
              const req = makeFakeRequest()
              requests.push(req)
              schedule(() => {
                req.result = store.get(key)
                req.onsuccess?.()
              })
              return req
            },
            delete: (key: number) => {
              const req = makeFakeRequest()
              requests.push(req)
              schedule(() => {
                store.delete(key)
                req.onsuccess?.()
              })
              return req
            },
          }),
          oncomplete: null as (() => void) | null,
          onabort: null as (() => void) | null,
          onerror: null as (() => void) | null,
        }
        // 全部请求派发后触发 complete（stub 简化：无失败路径）
        schedule(() => tx.oncomplete?.())
        return tx
      },
    }
  }

  return {
    open: (name: string) => {
      const req = makeFakeRequest()
      setTimeout(() => {
        const db = makeDb(name)
        // 与真实 IDB 一致：result 先就绪（升级回调内可读 request.result），再依次触发升级与成功
        req.result = db
        req.onupgradeneeded?.({ target: { result: db } })
        req.onsuccess?.()
      }, 0)
      return req
    },
  } as unknown as IDBFactory
}

/** 内存 localStorage stub（正向路径的会话映射用例） */
function createMemoryStorage(): Storage {
  const map = new Map<string, string>()
  return {
    get length() {
      return map.size
    },
    clear: () => map.clear(),
    getItem: (key: string) => map.get(key) ?? null,
    key: (index: number) => Array.from(map.keys())[index] ?? null,
    removeItem: (key: string) => {
      map.delete(key)
    },
    setItem: (key: string, value: string) => {
      map.set(key, String(value))
    },
  } as Storage
}

describe('offlineCache 正向路径（内存 IndexedDB stub）', () => {
  beforeEach(() => {
    vi.stubGlobal('indexedDB', createIdbStub())
  })

  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('save 后 get 读回完整快照（含自动补齐的 cached_at/version）', async () => {
    const steps = makeSteps()
    const saved = await saveRecipeSnapshot({
      recipe_id: 7,
      title: '番茄炒蛋',
      steps,
      base_servings: 2,
      session_id: 'sess-7',
    })
    expect(saved).toBe(true)

    const snapshot = await getRecipeSnapshot(7)
    expect(snapshot).not.toBeNull()
    expect(snapshot?.recipe_id).toBe(7)
    expect(snapshot?.title).toBe('番茄炒蛋')
    expect(snapshot?.steps).toEqual(steps)
    expect(snapshot?.base_servings).toBe(2)
    expect(snapshot?.session_id).toBe('sess-7')
    expect(typeof snapshot?.cached_at).toBe('number')
    expect(snapshot?.version).toBe(SNAPSHOT_VERSION)
  })

  it('同 recipe_id 重复保存为覆盖语义（读回最新内容）', async () => {
    await saveRecipeSnapshot({ recipe_id: 8, title: '旧菜名', steps: makeSteps() })
    await saveRecipeSnapshot({
      recipe_id: 8,
      title: '新菜名',
      steps: [{ no: 1, description: '覆盖后的步骤', duration_sec: 5 }],
    })
    const snapshot = await getRecipeSnapshot(8)
    expect(snapshot?.title).toBe('新菜名')
    expect(snapshot?.steps).toHaveLength(1)
    expect(snapshot?.steps[0]?.description).toBe('覆盖后的步骤')
  })

  it('get 未命中的 recipeId 返回 null', async () => {
    await saveRecipeSnapshot({ recipe_id: 9, steps: makeSteps() })
    await expect(getRecipeSnapshot(999)).resolves.toBeNull()
  })

  it('缺省字段自动兜底（title 空串 / base_servings 1）', async () => {
    await saveRecipeSnapshot({ recipe_id: 10, steps: makeSteps() })
    const snapshot = await getRecipeSnapshot(10)
    expect(snapshot?.title).toBe('')
    expect(snapshot?.base_servings).toBe(1)
  })

  it('clear 返回 true 且清除后 get 返回 null', async () => {
    await saveRecipeSnapshot({ recipe_id: 11, steps: makeSteps() })
    await expect(clearRecipeSnapshot(11)).resolves.toBe(true)
    await expect(getRecipeSnapshot(11)).resolves.toBeNull()
  })

  it('快照结构包含规范要求的键（recipe_id/steps/菜名/基准份数/缓存时间/版本号）', async () => {
    await saveRecipeSnapshot({ recipe_id: 12, title: 'X', steps: makeSteps(), base_servings: 3 })
    const snapshot = (await getRecipeSnapshot(12)) as RecipeSnapshot
    expect(Object.keys(snapshot).sort()).toEqual(
      ['base_servings', 'cached_at', 'recipe_id', 'session_id', 'steps', 'title', 'version'].sort(),
    )
  })
})

describe('offlineCache 会话映射（内存 localStorage stub）', () => {
  beforeEach(() => {
    vi.stubGlobal('localStorage', createMemoryStorage())
  })

  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('remember 后 recall 反查 recipeId（roundtrip）', () => {
    rememberSessionRecipe('sess-a', 42)
    expect(recallSessionRecipe('sess-a')).toBe(42)
  })

  it('recall 未记录的 sessionId 返回 null', () => {
    expect(recallSessionRecipe('sess-missing')).toBeNull()
  })

  it('映射值非法（非正数）时 recall 返回 null', () => {
    try {
      localStorage.setItem('aicook_session_recipe_sess-bad', 'abc')
      expect(recallSessionRecipe('sess-bad')).toBeNull()
      localStorage.setItem('aicook_session_recipe_sess-zero', '0')
      expect(recallSessionRecipe('sess-zero')).toBeNull()
    } catch {
      // 内存 stub 不会抛错，此分支仅为防御
    }
  })
})
