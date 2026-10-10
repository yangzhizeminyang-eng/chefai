/**
 * 文件职责：离线菜谱快照（NFR-3.6 离线可读，F 模块烹饪引导配套）。
 * - 进入烹饪引导（会话建立成功）时把当前菜谱步骤写入 IndexedDB（DB: aicook_offline，
 *   对象仓库 recipe_snapshot，keyPath = recipe_id），断网/会话缓存被清时可读可渲染；
 * - API：saveRecipeSnapshot / getRecipeSnapshot / clearRecipeSnapshot；
 * - 另含 sessionId → recipeId 的 localStorage 映射（recallSessionRecipe）：
 *   断点续做恢复失败时路由里只有 sessionId，经该映射反查 recipeId 才能取回快照；
 * - 降级策略：IndexedDB 不可用（隐私模式/SSR/打开失败）时全部静默失败——
 *   save/clear 返回 false、get 返回 null，不抛错、不打断在线烹饪流程。
 */
import type { RecipeStep } from '@/api/types'

/** IndexedDB 数据库名 */
const DB_NAME = 'aicook_offline'

/** IndexedDB 数据库版本（v1 建仓；后续字段演进在此升版本并在 onupgradeneeded 迁移） */
const DB_VERSION = 1

/** 对象仓库名（keyPath = recipe_id，同菜谱重复写入为覆盖语义） */
const STORE_NAME = 'recipe_snapshot'

/** 快照结构版本号（区分缓存数据代际，未来迁移判断用） */
export const SNAPSHOT_VERSION = 1

/** localStorage 会话→菜谱映射键前缀（key = aicook_session_recipe_{sessionId}） */
const SESSION_MAP_PREFIX = 'aicook_session_recipe_'

/** 离线快照结构（IndexedDB 中持久化的完整记录） */
export interface RecipeSnapshot {
  /** 菜谱 ID（对象仓库主键） */
  recipe_id: number
  /** 菜名（离线兜底展示用；进入引导时异步补齐，拉取失败为空串） */
  title: string
  /** 步骤快照（离线渲染数据源） */
  steps: RecipeStep[]
  /** 菜谱基准份数（本步用量提示缩放分母；离线态无会话份数，按基准原样展示） */
  base_servings: number
  /** 最近一次关联的烹饪会话 ID（可缺省，供诊断与后续按会话检索扩展） */
  session_id?: string
  /** 缓存写入时间（毫秒时间戳） */
  cached_at: number
  /** 快照结构版本号 */
  version: number
}

/** 保存快照的入参（cached_at/version 由本模块自动补齐，无需调用方关心） */
export interface RecipeSnapshotInput {
  /** 菜谱 ID（主键） */
  recipe_id: number
  /** 菜名（可缺省，默认空串） */
  title?: string
  /** 步骤快照 */
  steps: RecipeStep[]
  /** 菜谱基准份数（可缺省，默认 1 = 不缩放） */
  base_servings?: number
  /** 最近一次关联的烹饪会话 ID（可缺省） */
  session_id?: string
}

/**
 * 读取 IndexedDB 工厂对象（SSR / 隐私模式安全）。
 * @returns indexedDB 工厂；环境不支持（未定义/被禁用）返回 null
 * @throws 不抛出（属性探测被部分环境拦截时也按 null 处理）
 */
function getIdbFactory(): IDBFactory | null {
  try {
    if (typeof indexedDB === 'undefined' || indexedDB === null) return null
    return indexedDB
  } catch {
    return null
  }
}

/**
 * 打开数据库并确保对象仓库存在（仓缺失时在升级回调中创建）。
 * @returns 打开的数据库连接（调用方负责 close 释放）
 * @throws 打开失败 / 版本被阻塞 / 环境不可用时 reject（由上层 catch 降级）
 */
function openDb(): Promise<IDBDatabase> {
  return new Promise((resolve, reject) => {
    const factory = getIdbFactory()
    if (!factory) {
      reject(new Error('IndexedDB unavailable'))
      return
    }
    let request: IDBOpenDBRequest
    try {
      request = factory.open(DB_NAME, DB_VERSION)
    } catch (e) {
      // 隐私模式等直接抛同步异常的场景
      reject(e instanceof Error ? e : new Error('IndexedDB open failed'))
      return
    }
    request.onupgradeneeded = () => {
      const db = request.result
      if (!db.objectStoreNames.contains(STORE_NAME)) {
        db.createObjectStore(STORE_NAME, { keyPath: 'recipe_id' })
      }
    }
    request.onsuccess = () => resolve(request.result)
    request.onerror = () => reject(request.error ?? new Error('IndexedDB open failed'))
    request.onblocked = () => reject(new Error('IndexedDB open blocked'))
  })
}

/**
 * 将 IDBRequest 包装为 Promise（get 类请求取值用）。
 * @param request IDB 请求对象
 * @returns 请求成功后的结果值
 * @throws 请求失败时 reject（由上层 catch 降级）
 */
function requestToPromise<T>(request: IDBRequest<T>): Promise<T> {
  return new Promise((resolve, reject) => {
    request.onsuccess = () => resolve(request.result)
    request.onerror = () => reject(request.error ?? new Error('IndexedDB request failed'))
  })
}

/**
 * 等待事务完成（put/delete 的持久性以 complete 事件为准，而非单条请求 success）。
 * @param tx IDB 事务
 * @returns 事务完成即 resolve
 * @throws 事务中止/失败时 reject（由上层 catch 降级）
 */
function transactionDone(tx: IDBTransaction): Promise<void> {
  return new Promise((resolve, reject) => {
    tx.oncomplete = () => resolve()
    tx.onabort = () => reject(tx.error ?? new Error('IndexedDB transaction aborted'))
    tx.onerror = () => reject(tx.error ?? new Error('IndexedDB transaction failed'))
  })
}

/**
 * 保存（写入或覆盖）当前菜谱离线快照。
 * @param input 快照入参（recipe_id/steps 必填，title/base_servings/session_id 可缺省）
 * @returns 写入成功返回 true；IndexedDB 不可用或任何环节失败返回 false（不抛错）
 * @throws 不抛出（内部全量 try/catch 静默降级，保存失败不影响在线烹饪流程）
 */
export async function saveRecipeSnapshot(input: RecipeSnapshotInput): Promise<boolean> {
  const snapshot: RecipeSnapshot = {
    recipe_id: input.recipe_id,
    title: input.title ?? '',
    steps: input.steps,
    base_servings: input.base_servings ?? 1,
    session_id: input.session_id,
    cached_at: Date.now(),
    version: SNAPSHOT_VERSION,
  }
  let db: IDBDatabase | null = null
  try {
    db = await openDb()
    const tx = db.transaction(STORE_NAME, 'readwrite')
    tx.objectStore(STORE_NAME).put(snapshot)
    await transactionDone(tx)
    return true
  } catch {
    return false
  } finally {
    db?.close()
  }
}

/**
 * 读取指定菜谱的离线快照（断点续做恢复失败时的第三层兜底数据源）。
 * @param recipeId 菜谱 ID
 * @returns 命中返回快照记录；不存在 / IndexedDB 不可用 / 读取失败返回 null（不抛错）
 * @throws 不抛出（内部全量 try/catch 静默降级）
 */
export async function getRecipeSnapshot(recipeId: number): Promise<RecipeSnapshot | null> {
  let db: IDBDatabase | null = null
  try {
    db = await openDb()
    const tx = db.transaction(STORE_NAME, 'readonly')
    const request = tx.objectStore(STORE_NAME).get(recipeId)
    const result = (await requestToPromise(request)) as RecipeSnapshot | undefined
    return result ?? null
  } catch {
    return null
  } finally {
    db?.close()
  }
}

/**
 * 清除指定菜谱的离线快照（会话正常完成后的缓存清理入口）。
 * @param recipeId 菜谱 ID
 * @returns 删除成功返回 true；IndexedDB 不可用或失败返回 false（不抛错）
 * @throws 不抛出（内部全量 try/catch 静默降级）
 */
export async function clearRecipeSnapshot(recipeId: number): Promise<boolean> {
  let db: IDBDatabase | null = null
  try {
    db = await openDb()
    const tx = db.transaction(STORE_NAME, 'readwrite')
    tx.objectStore(STORE_NAME).delete(recipeId)
    await transactionDone(tx)
    return true
  } catch {
    return false
  } finally {
    db?.close()
  }
}

/**
 * 记录「会话 ID → 菜谱 ID」映射（进入引导时写入，离线恢复反查用）。
 * @param sessionId 烹饪会话 ID
 * @param recipeId 关联菜谱 ID
 * @returns 无
 * @throws 不抛出（localStorage 不可用时静默失败）
 */
export function rememberSessionRecipe(sessionId: string, recipeId: number): void {
  try {
    localStorage.setItem(`${SESSION_MAP_PREFIX}${sessionId}`, String(recipeId))
  } catch {
    // localStorage 不可用（隐私模式/SSR）：静默失败，不影响在线流程
  }
}

/**
 * 反查「会话 ID → 菜谱 ID」映射（恢复失败时的离线快照检索入口）。
 * @param sessionId 烹饪会话 ID
 * @returns 关联菜谱 ID；映射缺失/非法/localStorage 不可用返回 null
 * @throws 不抛出
 */
export function recallSessionRecipe(sessionId: string): number | null {
  try {
    const raw = localStorage.getItem(`${SESSION_MAP_PREFIX}${sessionId}`)
    if (!raw) return null
    const id = Number(raw)
    return Number.isFinite(id) && id > 0 ? id : null
  } catch {
    return null
  }
}
