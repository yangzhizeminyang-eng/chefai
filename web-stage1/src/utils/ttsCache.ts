/**
 * 文件职责：步骤朗读音频 IndexedDB 缓存（DB: aicook-tts，store: step-audio）。
 * 键 = `${recipeId}:${stepNo}`，值 = { blob, createdAt }；
 * FIFO 上限淘汰（超限删最早写入条目）；任何 IndexedDB 失败静默降级
 * （缓存不可用 ≠ 朗读功能不可用，朗读链路照走流式）。
 */

/** 数据库名（独立于离线快照库，互不影响） */
const DB_NAME = 'aicook-tts'
/** 对象仓库名 */
const STORE_NAME = 'step-audio'
/** 缓存条目上限（一步音频约几百 KB，100 条 ≈ 几十 MB 内） */
const MAX_ENTRIES = 100

/** 缓存条目（模型类） */
interface StepAudioEntry {
  /** 音频 Blob（wav） */
  blob: Blob
  /** 写入时间戳（FIFO 淘汰依据） */
  createdAt: number
}

/** 打开中的 DB 单例（失败后置空允许下次重试） */
let dbPromise: Promise<IDBDatabase> | null = null

/**
 * 打开（或复用）IndexedDB 连接（内部函数）。
 * @returns IDBDatabase 实例
 */
function openDb(): Promise<IDBDatabase> {
  if (!dbPromise) {
    dbPromise = new Promise<IDBDatabase>((resolve, reject) => {
      if (typeof indexedDB === 'undefined') {
        reject(new Error('indexedDB unavailable'))
        return
      }
      const req = indexedDB.open(DB_NAME, 1)
      req.onupgradeneeded = () => {
        if (!req.result.objectStoreNames.contains(STORE_NAME)) {
          req.result.createObjectStore(STORE_NAME)
        }
      }
      req.onsuccess = () => resolve(req.result)
      req.onerror = () => reject(req.error ?? new Error('open failed'))
    })
    dbPromise.catch(() => {
      dbPromise = null
    })
  }
  return dbPromise
}

/**
 * 读取一步的缓存音频（函数）。
 * @param recipeId 菜谱 ID
 * @param stepNo 步骤号（1 起）
 * @returns 音频 Blob；未命中或缓存不可用返回 null
 */
export async function getStepAudio(recipeId: number, stepNo: number): Promise<Blob | null> {
  try {
    const db = await openDb()
    return await new Promise<Blob | null>((resolve, reject) => {
      const tx = db.transaction(STORE_NAME, 'readonly')
      const req = tx.objectStore(STORE_NAME).get(`${recipeId}:${stepNo}`)
      req.onsuccess = () => {
        const entry = req.result as StepAudioEntry | undefined
        resolve(entry?.blob ?? null)
      }
      req.onerror = () => reject(req.error ?? new Error('get failed'))
    })
  } catch {
    return null
  }
}

/**
 * 写入一步的缓存音频并做 FIFO 淘汰（函数）。
 * @param recipeId 菜谱 ID
 * @param stepNo 步骤号（1 起）
 * @param blob 音频 Blob
 * @returns 无
 */
export async function putStepAudio(recipeId: number, stepNo: number, blob: Blob): Promise<void> {
  try {
    const db = await openDb()
    await new Promise<void>((resolve, reject) => {
      const tx = db.transaction(STORE_NAME, 'readwrite')
      tx.objectStore(STORE_NAME).put({ blob, createdAt: Date.now() } satisfies StepAudioEntry, `${recipeId}:${stepNo}`)
      tx.oncomplete = () => resolve()
      tx.onerror = () => reject(tx.error ?? new Error('put failed'))
      tx.onabort = () => reject(tx.error ?? new Error('put aborted'))
    })
    await evictIfOverflow(db)
  } catch {
    // 缓存写失败静默：朗读主链路不受影响
  }
}

/**
 * 超限淘汰：按写入时间 FIFO 删掉最旧条目（内部函数）。
 * @param db 已打开的 DB
 * @returns 无
 */
async function evictIfOverflow(db: IDBDatabase): Promise<void> {
  try {
    const entries = await new Promise<Array<{ key: string; createdAt: number }>>((resolve, reject) => {
      const items: Array<{ key: string; createdAt: number }> = []
      const tx = db.transaction(STORE_NAME, 'readonly')
      const cursorReq = tx.objectStore(STORE_NAME).openCursor()
      cursorReq.onsuccess = () => {
        const cursor = cursorReq.result
        if (!cursor) {
          resolve(items)
          return
        }
        const entry = cursor.value as StepAudioEntry | undefined
        items.push({ key: String(cursor.key), createdAt: entry?.createdAt ?? 0 })
        cursor.continue()
      }
      cursorReq.onerror = () => reject(cursorReq.error ?? new Error('cursor failed'))
    })
    if (entries.length <= MAX_ENTRIES) return
    entries.sort((a, b) => a.createdAt - b.createdAt)
    const doomed = entries.slice(0, entries.length - MAX_ENTRIES)
    const tx = db.transaction(STORE_NAME, 'readwrite')
    const store = tx.objectStore(STORE_NAME)
    for (const item of doomed) store.delete(item.key)
  } catch {
    // 淘汰失败静默：下次写入再试
  }
}
