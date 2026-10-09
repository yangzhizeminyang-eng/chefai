/**
 * 文件职责：列表页通用状态组合式函数（加载 / 错误 / 数据 / 分页）。
 * 统一「加载中 / 空 / 错误」三态与翻页行为，供各管理页面复用。
 */
import { ref } from 'vue'

import { getErrorMessage } from '@/api/admin'
import type { PageResult } from '@/api/admin'

/**
 * 简单列表（不分页）状态。
 * @param fetcher 拉取函数，返回列表数组
 * @returns loading / error / items / load
 */
export function useSimpleList<T>(fetcher: () => Promise<T[]>) {
  const loading = ref(false)
  const error = ref('')
  const items = ref<T[]>([])

  /** 拉取列表数据（覆盖加载 / 错误状态，失败时清空列表） */
  async function load(): Promise<void> {
    loading.value = true
    error.value = ''
    try {
      items.value = await fetcher()
    } catch (e) {
      error.value = getErrorMessage(e, '数据加载失败')
      items.value = []
    } finally {
      loading.value = false
    }
  }

  return { loading, error, items, load }
}

/**
 * 分页列表状态。
 * @param fetcher 拉取函数，入参为页码与页大小，返回分页结果
 * @param defaultSize 默认每页条数
 * @returns 三态数据 + 分页状态 + 翻页回调
 */
export function usePagedList<T>(fetcher: (page: number, size: number) => Promise<PageResult<T>>, defaultSize = 10) {
  const loading = ref(false)
  const error = ref('')
  const items = ref<T[]>([])
  const total = ref(0)
  const page = ref(1)
  const size = ref(defaultSize)

  /** 按当前页码拉取数据（覆盖加载 / 错误状态，失败时清空列表） */
  async function load(): Promise<void> {
    loading.value = true
    error.value = ''
    try {
      const result = await fetcher(page.value, size.value)
      items.value = result.items
      total.value = result.total
    } catch (e) {
      error.value = getErrorMessage(e, '数据加载失败')
      items.value = []
      total.value = 0
    } finally {
      loading.value = false
    }
  }

  /** 筛选条件变化后重置到第一页并重新加载 */
  async function reload(): Promise<void> {
    page.value = 1
    await load()
  }

  /**
   * 翻页回调。
   * @param p 目标页码
   */
  async function onPageChange(p: number): Promise<void> {
    page.value = p
    await load()
  }

  /**
   * 每页条数变化回调（重置到第一页）。
   * @param s 新的每页条数
   */
  async function onSizeChange(s: number): Promise<void> {
    size.value = s
    page.value = 1
    await load()
  }

  return { loading, error, items, total, page, size, load, reload, onPageChange, onSizeChange }
}
