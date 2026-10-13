/**
 * 文件职责：离线菜谱快照（NFR-3.6 离线可读，F 模块烹饪引导配套）。
 * 自 web-stage1/src/utils/offlineCache.ts 迁移：IndexedDB 换为本工程 storage.ts
 * （uni storage；对外函数签名与 key 语义保持不变）。
 * - 进入烹饪引导（会话建立成功）时把当前菜谱步骤写入本地存储（key = offline_recipe_{id}），
 *   断网/会话缓存被清时可读可渲染；
 * - 另含 sessionId → recipeId 的映射（key = aicook_session_recipe_{sessionId}，
 *   recallSessionRecipe）：断点续做恢复失败时路由里只有 sessionId，经映射反查 recipeId；
 * - 容量治理：单篇序列化 >50KB 不缓存并 console.warn；aicook_offline_index 维护
 *   LRU（最多 20 篇，超限淘汰最旧），总量 >1MB 逐出最旧直至达标；
 * - 降级策略：存储不可用 / 任何失败全部静默——save/clear 返回 false、get 返回 null，
 *   不抛错、不打断在线烹饪流程。
 */
import type { RecipeStep } from '@shared/types'
import { get as storageGet, set as storageSet, remove as storageRemove } from '@/utils/storage'

/** 快照结构版本号（区分缓存数据代际，未来迁移判断用；不匹配视为脏数据返回 null） */
export const SNAPSHOT_VERSION = 1

/** 会话 → 菜谱映射键前缀（key = aicook_session_recipe_{sessionId}，沿用源码语义） */
const SESSION_MAP_PREFIX = 'aicook_session_recipe_'

/** 菜谱离线快照键前缀（key = offline_recipe_{id}，任务规定口径） */
const SNAPSHOT_KEY_PREFIX = 'offline_recipe_'

/** LRU 索引键（元素 { id, size, cached_at }，队首最旧） */
export const OFFLINE_INDEX_KEY = 'aicook_offline_index'

/** 单篇快照序列化上限（50KB，超出不缓存） */
export const MAX_SNAPSHOT_BYTES = 50 * 1024

/** LRU 条数上限（最多缓存 20 篇） */
export const MAX_INDEX_COUNT = 20

/** 索引内总量上限（>1MB 逐出最旧直至达标） */
export const MAX_TOTAL_BYTES = 1024 * 1024

/** LRU 索引条目 */
export interface OfflineIndexEntry {
  /** 菜谱 ID */
  id: number
  /** 序列化后字节数（近似，按字符串长度） */
  size: number
  /** 写入时间（毫秒时间戳，仅诊断用；淘汰以队列顺序为准） */
  cached_at: number
}

/** LRU 索引类型（队首最旧、队尾最新） */
export type OfflineIndex = OfflineIndexEntry[]

/** 离线快照结构（本地存储中持久化的完整记录） */
export interface RecipeSnapshot {
  /** 菜谱 ID */
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
  /** 菜谱 ID */
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
 * 纯函数：把一次快照写入合并进 LRU 索引（同 id 先去重再触达队尾），
 * 依次按条数上限（20 篇）与总量上限（1MB）从队首淘汰最旧条目。
 * 导出以便单测直接验证 LRU 淘汰逻辑。
 * @param index 现有索引（队首最旧）
 * @param id 本次写入的菜谱 ID
 * @param size 本次快照序列化字节数
 * @param now 本次写入时间（缺省 Date.now()，测试可注入固定值）
 * @returns { index } 淘汰后的新索引；{ evicted } 被淘汰的菜谱 ID 列表（调用方负责删快照实体）
 * @throws 不抛出
 */
export function applyIndexInsert(
  index: OfflineIndex,
  id: number,
  size: number,
  now: number = Date.now(),
): { index: OfflineIndex; evicted: number[] } {
  const rest = index.filter((e) => e.id !== id)
  const next: OfflineIndex = [...rest, { id, size, cached_at: now }]
  const evicted: number[] = []
  // 条数上限：超出即从队首（最旧）淘汰
  while (next.length > MAX_INDEX_COUNT) {
    const oldest = next.shift()
    if (oldest) evicted.push(oldest.id)
  }
  // 总量上限：>1MB 逐出最旧直至达标
  let total = next.reduce((sum, e) => sum + e.size, 0)
  while (total > MAX_TOTAL_BYTES && next.length > 0) {
    const oldest = next.shift()
    if (!oldest) break
    total -= oldest.size
    evicted.push(oldest.id)
  }
  return { index: next, evicted }
}

/**
 * 读取 LRU 索引（损坏 / 缺失返回空数组）。
 * @returns 索引数组
 * @throws 不抛出
 */
function readIndex(): OfflineIndex {
  try {
    const raw = storageGet<OfflineIndex>(OFFLINE_INDEX_KEY, [])
    return Array.isArray(raw) ? raw : []
  } catch {
    return []
  }
}

/**
 * 写回 LRU 索引（静默）。
 * @param index 新索引
 * @returns 无
 * @throws 不抛出
 */
function writeIndex(index: OfflineIndex): void {
  try {
    storageSet(OFFLINE_INDEX_KEY, index)
  } catch {
    // 静默：索引写失败仅影响后续淘汰精度
  }
}

/**
 * 删除被淘汰菜谱的快照实体（静默）。
 * @param ids 被淘汰的菜谱 ID 列表
 * @returns 无
 * @throws 不抛出
 */
function evictSnapshots(ids: number[]): void {
  for (const id of ids) {
    try {
      storageRemove(`${SNAPSHOT_KEY_PREFIX}${id}`)
    } catch {
      // 静默
    }
  }
}

/**
 * 保存（写入或覆盖）当前菜谱离线快照。
 * 序列化 >50KB 不缓存（console.warn）；写成功后同步 LRU 索引并淘汰超额条目。
 * @param input 快照入参（recipe_id/steps 必填，title/base_servings/session_id 可缺省）
 * @returns 写入成功返回 true；超限 / 存储不可用 / 任何失败返回 false（不抛错）
 * @throws 不抛出（内部全量 try/catch 静默降级，保存失败不影响在线烹饪流程）
 */
export async function saveRecipeSnapshot(input: RecipeSnapshotInput): Promise<boolean> {
  try {
    const snapshot: RecipeSnapshot = {
      recipe_id: input.recipe_id,
      title: input.title ?? '',
      steps: input.steps,
      base_servings: input.base_servings ?? 1,
      session_id: input.session_id,
      cached_at: Date.now(),
      version: SNAPSHOT_VERSION,
    }
    const json = JSON.stringify(snapshot)
    if (json.length > MAX_SNAPSHOT_BYTES) {
      console.warn(`[offlineCache] 菜谱 ${input.recipe_id} 快照 ${json.length}B 超过 ${MAX_SNAPSHOT_BYTES}B，放弃缓存`)
      return false
    }
    const { index: nextIndex, evicted } = applyIndexInsert(readIndex(), input.recipe_id, json.length)
    storageSet(`${SNAPSHOT_KEY_PREFIX}${input.recipe_id}`, snapshot)
    evictSnapshots(evicted)
    writeIndex(nextIndex)
    return true
  } catch {
    return false
  }
}

/**
 * 读取指定菜谱的离线快照（断点续做恢复失败时的第三层兜底数据源）。
 * @param recipeId 菜谱 ID
 * @returns 命中返回快照记录；不存在 / 版本不匹配（脏数据）/ 存储不可用返回 null（不抛错）
 * @throws 不抛出（内部全量 try/catch 静默降级）
 */
export async function getRecipeSnapshot(recipeId: number): Promise<RecipeSnapshot | null> {
  try {
    const raw = storageGet<RecipeSnapshot>(`${SNAPSHOT_KEY_PREFIX}${recipeId}`)
    if (!raw || typeof raw !== 'object') return null
    if (raw.version !== SNAPSHOT_VERSION) return null
    return raw
  } catch {
    return null
  }
}

/**
 * 清除指定菜谱的离线快照（会话正常完成后的缓存清理入口），并同步移除索引条目。
 * @param recipeId 菜谱 ID
 * @returns 删除成功返回 true；存储不可用或失败返回 false（不抛错）
 * @throws 不抛出（内部全量 try/catch 静默降级）
 */
export async function clearRecipeSnapshot(recipeId: number): Promise<boolean> {
  try {
    storageRemove(`${SNAPSHOT_KEY_PREFIX}${recipeId}`)
    writeIndex(readIndex().filter((e) => e.id !== recipeId))
    return true
  } catch {
    return false
  }
}

/**
 * 记录「会话 ID → 菜谱 ID」映射（进入引导时写入，离线恢复反查用）。
 * @param sessionId 烹饪会话 ID
 * @param recipeId 关联菜谱 ID
 * @returns 无
 * @throws 不抛出（storage 不可用时静默失败）
 */
export function rememberSessionRecipe(sessionId: string, recipeId: number): void {
  try {
    storageSet(`${SESSION_MAP_PREFIX}${sessionId}`, recipeId)
  } catch {
    // storage 不可用：静默失败，不影响在线流程
  }
}

/**
 * 反查「会话 ID → 菜谱 ID」映射（恢复失败时的离线快照检索入口）。
 * @param sessionId 烹饪会话 ID
 * @returns 关联菜谱 ID；映射缺失 / 非法 / storage 不可用返回 null
 * @throws 不抛出
 */
export function recallSessionRecipe(sessionId: string): number | null {
  try {
    const id = storageGet<number>(`${SESSION_MAP_PREFIX}${sessionId}`)
    return typeof id === 'number' && Number.isFinite(id) && id > 0 ? id : null
  } catch {
    return null
  }
}
