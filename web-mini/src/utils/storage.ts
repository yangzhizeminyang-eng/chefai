/**
 * 文件职责：uni storage 受控封装——本工程唯一的本地持久化入口。
 * 设计要点：
 * - 全部基于 uni.getStorageSync / setStorageSync / removeStorageSync / getStorageInfoSync，
 *   禁用浏览器 localStorage（小程序端无该 API，且静态检查脚本会拦截）；
 * - 值统一 JSON 序列化后落盘（set 写 JSON 字符串，get 尝试 JSON.parse），读失败静默返回
 *   fallback 不抛异常——存储异常绝不阻断主流程（阶段一教训：脏数据只降级不崩页）；
 * - SCHEMA_VERSION 校验（阶段一 NEW-01 教训）：模块加载时执行 ensureSchema()，
 *   aicook_schema_version 不匹配/缺失则清除全部 aicook_ 前缀键后写入当前版本，防脏数据；
 * - 容量治理：单键序列化 >256KB 触发 LRU 淘汰流程，仍超限则拒绝写入并 console.warn；
 *   LRU 索引维护于 aicook_lru_index（key 数组，队首最旧），get/set 时 touch；
 * - memoryStore：进程内 Map 封装——过敏原 / 健康目标等敏感数据仅存内存态，
 *   不落明文存储（PIPL 最小化原则），页面销毁即随实例回收。
 */

/** 统一键前缀：本应用所有持久化键均以此为前缀（schema 清理与容量治理的边界） */
const PREFIX = 'aicook_'

/** 结构版本号：键结构演进时递增，触发旧数据全量清理 */
export const SCHEMA_VERSION = '1'

/** schema 版本键 */
const SCHEMA_KEY = 'aicook_schema_version'

/** 匿名会话 ID 键（请求层 X-Anonymous-Id 头数据源；白名单豁免 LRU 淘汰） */
export const ANONYMOUS_ID_KEY = 'aicook_anonymous_id'

/** LRU 索引键（记录普通 key 的访问顺序，队首最旧；自身不入索引） */
const LRU_INDEX_KEY = 'aicook_lru_index'

/** 单键序列化硬上限（字节近似：按 UTF-16 码元长度估算） */
const MAX_VALUE_LENGTH = 256 * 1024

/** LRU 索引容量上限：超出时裁剪最旧条目，防索引自身无限增长 */
const LRU_INDEX_LIMIT = 100

/** LRU 淘汰白名单：身份 / 版本 / 索引三类基础设施键不参与淘汰 */
const LRU_WHITELIST = new Set<string>([ANONYMOUS_ID_KEY, SCHEMA_KEY, LRU_INDEX_KEY])

/**
 * 读取 LRU 索引（直接走 uni 原生 API，避免 get() 的 JSON 语义递归 touch）。
 * @returns 索引 key 数组（队首最旧）；缺失 / 损坏返回空数组
 * @throws 不抛出（内部 try/catch 静默兜底）
 */
function readLruIndex(): string[] {
  try {
    const raw = uni.getStorageSync(LRU_INDEX_KEY)
    if (typeof raw !== 'string' || raw === '') return []
    const parsed: unknown = JSON.parse(raw)
    if (!Array.isArray(parsed)) return []
    return parsed.filter((k): k is string => typeof k === 'string')
  } catch {
    return []
  }
}

/**
 * 写回 LRU 索引（超容量上限时裁剪最旧条目）。
 * @param keys 最新索引（队首最旧，队尾最近访问）
 * @returns 无
 * @throws 不抛出（存储不可用时静默放弃，仅影响后续淘汰精度）
 */
function writeLruIndex(keys: string[]): void {
  try {
    const trimmed = keys.slice(Math.max(0, keys.length - LRU_INDEX_LIMIT))
    uni.setStorageSync(LRU_INDEX_KEY, JSON.stringify(trimmed))
  } catch {
    // 存储不可用（磁盘满/隐私模式）：静默放弃
  }
}

/**
 * touch：把 key 移到 LRU 队尾（最近访问）。白名单键不入索引。
 * @param key 本次读/写的存储键
 * @returns 无
 * @throws 不抛出
 */
function touchLru(key: string): void {
  if (LRU_WHITELIST.has(key)) return
  const keys = readLruIndex()
  const idx = keys.indexOf(key)
  if (idx >= 0) keys.splice(idx, 1)
  keys.push(key)
  writeLruIndex(keys)
}

/**
 * 从 LRU 索引移除指定 key（remove/clear 时同步维护）。
 * @param key 被移除的存储键
 * @returns 无
 * @throws 不抛出
 */
function dropLru(key: string): void {
  const keys = readLruIndex()
  const idx = keys.indexOf(key)
  if (idx < 0) return
  keys.splice(idx, 1)
  writeLruIndex(keys)
}

/**
 * LRU 淘汰一轮：从队首逐个删除非白名单键（含索引同步），为本次写入腾出配额。
 * @returns 无
 * @throws 不抛出
 */
function evictOldest(): void {
  const keys = readLruIndex()
  while (keys.length > 0) {
    const oldest = keys.shift()
    if (!oldest || LRU_WHITELIST.has(oldest)) continue
    try {
      uni.removeStorageSync(oldest)
    } catch {
      // 删除失败：继续尝试下一个，避免单键阻塞淘汰流程
    }
    writeLruIndex(keys)
    return
  }
}

/**
 * schema 校验：版本不匹配 / 缺失时清除全部 aicook_ 前缀键并写入当前版本
 * （阶段一 NEW-01 教训：版本漂移导致的脏数据宁可丢弃也不带病运行）。
 * @returns 无
 * @throws 不抛出（模块加载期执行，任何异常静默——存储不可用不影响页面渲染）
 */
function ensureSchema(): void {
  try {
    const current = uni.getStorageSync(SCHEMA_KEY)
    if (current === SCHEMA_VERSION) return
    // 版本不匹配 / 缺失：清空本应用全部键（仅限 aicook_ 前缀，不碰其他插件数据）
    try {
      const info = uni.getStorageInfoSync()
      for (const key of info.keys ?? []) {
        if (key.startsWith(PREFIX)) {
          try {
            uni.removeStorageSync(key)
          } catch {
            // 单键删除失败忽略，继续清理其余键
          }
        }
      }
    } catch {
      // getStorageInfoSync 不可用：降级为清空全部（clearStorageSync）
      try {
        uni.clearStorageSync()
      } catch {
        // 彻底不可用：放弃
      }
    }
    uni.setStorageSync(SCHEMA_KEY, SCHEMA_VERSION)
  } catch {
    // 存储整体不可用：静默降级为纯内存运行
  }
}

// 模块加载即执行 schema 校验（阶段一 NEW-01：防脏数据，无需页面显式调用）
ensureSchema()

/**
 * 读取存储值（带重载：无 fallback 时返回 T | undefined）。
 * @param key 存储键（约定 aicook_ 前缀）
 * @param fallback 缺失 / 解析失败时的兜底值
 * @returns 反序列化后的值；键缺失 / 值为空 / JSON 解析失败返回 fallback（可能为 undefined）
 * @throws 不抛出（JSON.parse 失败、storage 异常均走 fallback）
 */
export function get<T>(key: string): T | undefined
export function get<T>(key: string, fallback: T): T
export function get<T>(key: string, fallback?: T): T | undefined {
  try {
    const raw = uni.getStorageSync(key)
    if (raw === '' || raw === null || raw === undefined) return fallback
    if (typeof raw === 'string') {
      try {
        return JSON.parse(raw) as T
      } catch {
        // 序列化格式与预期不符（历史脏数据）：按 fallback 处理
        return fallback
      }
    }
    // 部分平台 storage 会自动反序列化对象：直接透传
    return raw as T
  } catch {
    return fallback
  }
}

/**
 * 写入存储值（JSON 序列化；单键 >256KB 触发 LRU 淘汰流程，仍超限拒绝写入）。
 * @param key 存储键
 * @param value 待写入值（任意可 JSON 序列化结构）
 * @returns 无（拒绝写入时仅 console.warn，不抛异常）
 * @throws 不抛出（存储不可用时静默降级）
 */
export function set(key: string, value: unknown): void {
  let json: string
  try {
    json = JSON.stringify(value)
  } catch {
    // 循环引用等不可序列化值：拒绝写入（与超限同口径），不抛异常
    console.warn(`[storage] key=${key} 值不可序列化，已拒绝写入`)
    return
  }
  if (json.length > MAX_VALUE_LENGTH) {
    // 走 LRU：淘汰最旧的普通键为总配额腾空间（尽力而为）
    evictOldest()
    if (json.length > MAX_VALUE_LENGTH) {
      // 单键硬上限 256KB：淘汰他人无法缩小本键，拒绝写入
      console.warn(`[storage] key=${key} 序列化后 ${json.length}B 超过单键上限 ${MAX_VALUE_LENGTH}B，已拒绝写入`)
      return
    }
  }
  try {
    uni.setStorageSync(key, json)
    touchLru(key)
  } catch {
    // 写入失败（磁盘满/隐私模式）：静默降级
  }
}

/**
 * 删除指定键（同步移出 LRU 索引）。
 * @param key 存储键
 * @returns 无
 * @throws 不抛出
 */
export function remove(key: string): void {
  try {
    uni.removeStorageSync(key)
  } catch {
    // 存储不可用：静默
  }
  dropLru(key)
}

/**
 * 批量清除：带前缀时仅清除匹配键；不带前缀时清空全部存储。
 * @param prefix 键前缀（可选，如 'aicook_'）
 * @returns 无
 * @throws 不抛出
 */
export function clear(prefix?: string): void {
  if (prefix === undefined) {
    try {
      uni.clearStorageSync()
    } catch {
      // 静默
    }
    return
  }
  try {
    const info = uni.getStorageInfoSync()
    for (const key of info.keys ?? []) {
      if (key.startsWith(prefix)) remove(key)
    }
  } catch {
    // getStorageInfoSync 不可用：静默
  }
}

/* ═══════════════ 敏感数据内存态（不落明文） ═══════════════ */

/**
 * 进程内内存存储（Map 封装）：过敏原 / 健康目标等 PIPL 敏感数据专用，
 * 仅存活于小程序实例生命周期，退出即回收，绝不写入 uni storage 明文落盘。
 */
const memory = new Map<string, unknown>()

/**
 * 读内存态值。
 * @param key 内存键
 * @param fallback 缺失时的兜底值
 * @returns 命中的值或 fallback
 * @throws 不抛出
 */
export function memGet<T>(key: string, fallback?: T): T | undefined {
  return memory.has(key) ? (memory.get(key) as T) : fallback
}

/**
 * 写内存态值。
 * @param key 内存键
 * @param value 待存值
 * @returns 无
 * @throws 不抛出
 */
export function memSet(key: string, value: unknown): void {
  memory.set(key, value)
}

/**
 * 删内存态值。
 * @param key 内存键
 * @returns 无
 * @throws 不抛出
 */
export function memRemove(key: string): void {
  memory.delete(key)
}
