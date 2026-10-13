/**
 * 文件级注释：offlineCache 单元测试——以内存 Map 模拟 storage 模块，
 * 覆盖：①写入成功读取一致；②超 50KB 不写入；③第 21 篇触发 LRU 淘汰最旧；
 * 附带会话映射往返与索引纯函数用例。
 */
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { saveRecipeSnapshot, getRecipeSnapshot, rememberSessionRecipe, recallSessionRecipe, applyIndexInsert } from '@/utils/offlineCache'

/** 模拟存储容器（vi.hoisted 保证在 vi.mock 工厂执行前可用） */
const mem = vi.hoisted(() => new Map<string, unknown>())

/** 以内存 Map 模拟 @/utils/storage（与真实模块同签名子集：get/set/remove） */
vi.mock('@/utils/storage', () => ({
  get: vi.fn((key: string) => (mem.has(key) ? mem.get(key) : undefined)),
  set: vi.fn((key: string, value: unknown) => {
    mem.set(key, value)
  }),
  remove: vi.fn((key: string) => {
    mem.delete(key)
  }),
  clear: vi.fn(),
}))

/** 构造一个最小合法步骤（测试数据工厂） */
function step(no: number): { no: number; description: string; duration_sec: number } {
  return { no, description: `步骤${no}：热锅下油`, duration_sec: 30 }
}

beforeEach(() => {
  mem.clear()
})

describe('offlineCache 快照存取', () => {
  it('写入成功后读取内容一致', async () => {
    const ok = await saveRecipeSnapshot({
      recipe_id: 1,
      title: '番茄炒蛋',
      steps: [step(1), step(2)],
      base_servings: 2,
      session_id: 's-001',
    })
    expect(ok).toBe(true)
    const snap = await getRecipeSnapshot(1)
    expect(snap).not.toBeNull()
    expect(snap?.recipe_id).toBe(1)
    expect(snap?.title).toBe('番茄炒蛋')
    expect(snap?.steps).toHaveLength(2)
    expect(snap?.base_servings).toBe(2)
    expect(snap?.session_id).toBe('s-001')
    expect(snap?.version).toBe(1)
  })

  it('序列化超 50KB 不写入并返回 false', async () => {
    const bigText = 'a'.repeat(60 * 1024)
    const ok = await saveRecipeSnapshot({
      recipe_id: 2,
      title: '超大菜谱',
      steps: [{ no: 1, description: bigText, duration_sec: 0 }],
    })
    expect(ok).toBe(false)
    expect(await getRecipeSnapshot(2)).toBeNull()
    // 确认未落任何快照实体键
    expect(mem.has('offline_recipe_2')).toBe(false)
  })

  it('第 21 篇触发 LRU：最旧的第 1 篇被淘汰，其余仍在', async () => {
    for (let id = 1; id <= 21; id++) {
      const ok = await saveRecipeSnapshot({ recipe_id: id, title: `菜谱${id}`, steps: [step(1)] })
      expect(ok).toBe(true)
    }
    // 第 1 篇（最旧）被淘汰
    expect(await getRecipeSnapshot(1)).toBeNull()
    // 第 2~21 篇仍在（共 20 篇）
    for (let id = 2; id <= 21; id++) {
      expect(await getRecipeSnapshot(id)).not.toBeNull()
    }
    // 重复写入触达：刷新 id=2 到队尾后，再写第 22 篇应淘汰 id=3
    await saveRecipeSnapshot({ recipe_id: 2, title: '菜谱2-覆盖', steps: [step(1)] })
    await saveRecipeSnapshot({ recipe_id: 22, title: '菜谱22', steps: [step(1)] })
    expect(await getRecipeSnapshot(3)).toBeNull()
    expect(await getRecipeSnapshot(2)).not.toBeNull()
    expect(await getRecipeSnapshot(22)).not.toBeNull()
  })

  it('会话 → 菜谱映射可往返', async () => {
    rememberSessionRecipe('s-100', 42)
    expect(recallSessionRecipe('s-100')).toBe(42)
    expect(recallSessionRecipe('s-missing')).toBeNull()
  })

  it('applyIndexInsert 纯函数：条数与总量淘汰、同 id 去重', () => {
    // 条数上限：插入第 21 条淘汰队首
    let index = Array.from({ length: 20 }, (_, i) => ({ id: i + 1, size: 100, cached_at: i }))
    let r = applyIndexInsert(index, 21, 100, 999)
    expect(r.index).toHaveLength(20)
    expect(r.evicted).toEqual([1])
    // 总量上限：单条 60KB × 17 = 1.02MB > 1MB → 插入后从队首逐出直至达标
    index = Array.from({ length: 16 }, (_, i) => ({ id: i + 1, size: 60 * 1024, cached_at: i }))
    r = applyIndexInsert(index, 17, 60 * 1024, 999)
    expect(r.index.reduce((s, e) => s + e.size, 0)).toBeLessThanOrEqual(1024 * 1024)
    expect(r.index[r.index.length - 1]?.id).toBe(17)
    // 同 id 去重：重复写不产生重复条目
    index = [
      { id: 5, size: 10, cached_at: 1 },
      { id: 6, size: 10, cached_at: 2 },
    ]
    r = applyIndexInsert(index, 5, 10, 3)
    expect(r.index.map((e) => e.id)).toEqual([6, 5])
  })
})
