/**
 * 文件职责：库存与购物清单状态（/v1/inventory、/v1/shopping-list 数据源；
 * 自 web-stage1/src/stores/inventory.ts 原样平移）。
 * - items：在库条目（active），页面负责临期置顶排序展示；
 * - shoppingItems：购物清单条目；
 * - 增删改 / 标记用完 / 转入库存 / 清空已购：动作成功后本地同步刷新对应列表；
 * - 三态齐备（loading / error / 数据），供页面直接渲染。
 */
import { defineStore } from 'pinia'
import {
  deleteInventory,
  deleteShoppingItem,
  getInventory,
  getShoppingList,
  patchInventory,
  postInventory,
  postShoppingList,
  postShoppingToInventory,
} from '@/api/endpoints'
import type {
  ApiError,
  InventoryCreateBody,
  InventoryItem,
  InventoryPatchBody,
  ShoppingCreateBody,
  ShoppingItem,
} from '@shared/types'

export const useInventoryStore = defineStore('inventory', {
  state: () => ({
    /** 在库条目列表（status=active） */
    items: [] as InventoryItem[],
    /** 购物清单条目 */
    shoppingItems: [] as ShoppingItem[],
    /** 库存加载中 */
    loading: false,
    /** 库存加载错误 */
    error: null as ApiError | null,
    /** 购物清单加载中 */
    shoppingLoading: false,
    /** 购物清单加载错误 */
    shoppingError: null as ApiError | null,
    /** 变更动作进行中（新增/编辑/删除等共用，防连点） */
    mutating: false,
  }),
  getters: {
    /**
     * 在库条目数。
     * @returns 数量
     */
    activeCount: (state): number => state.items.length,
    /**
     * 临期条目（剩余 ≤3 天含已过期，供提醒条与置顶排序参考）。
     * @returns 临期条目数组
     */
    expiringItems: (state): InventoryItem[] =>
      state.items.filter((it) => {
        const days = daysUntil(it.expire_date)
        return days <= 3
      }),
  },
  actions: {
    /**
     * 拉取在库条目（status=active）。
     * @returns 无
     * @throws 不抛出（失败写入 error 三态并清空列表）
     */
    async loadItems(): Promise<void> {
      this.loading = true
      this.error = null
      try {
        const res = await getInventory('active')
        this.items = res.items ?? []
      } catch (e) {
        this.error = e as ApiError
        this.items = []
      } finally {
        this.loading = false
      }
    },

    /**
     * 拉取购物清单。
     * @returns 无
     * @throws 不抛出（失败写入 shoppingError 三态并清空列表）
     */
    async loadShopping(): Promise<void> {
      this.shoppingLoading = true
      this.shoppingError = null
      try {
        const res = await getShoppingList()
        this.shoppingItems = res.items ?? []
      } catch (e) {
        this.shoppingError = e as ApiError
        this.shoppingItems = []
      } finally {
        this.shoppingLoading = false
      }
    },

    /**
     * 新增库存条目，成功后重拉列表保持排序一致。
     * @param body 食材 + 数量档位 + 可选到期日/位置
     * @returns 无
     * @throws 接口失败时抛出归一化 ApiError（mutating 保证复位）
     */
    async addItem(body: InventoryCreateBody): Promise<void> {
      this.mutating = true
      try {
        await postInventory(body)
        await this.loadItems()
      } finally {
        this.mutating = false
      }
    },

    /**
     * 修改库存条目（本地原位替换，不打乱页面排序）。
     * @param id 条目 ID
     * @param patch 增量字段
     * @returns 无
     * @throws 接口失败时抛出归一化 ApiError（mutating 保证复位）
     */
    async patchItem(id: number, patch: InventoryPatchBody): Promise<void> {
      this.mutating = true
      try {
        const updated = await patchInventory(id, patch)
        this.items = this.items.map((it) => (it.id === id ? updated : it))
      } finally {
        this.mutating = false
      }
    },

    /**
     * 删除库存条目，成功后本地移除。
     * @param id 条目 ID
     * @returns 无
     * @throws 接口失败时抛出归一化 ApiError（mutating 保证复位）
     */
    async removeItem(id: number): Promise<void> {
      this.mutating = true
      try {
        await deleteInventory(id)
        this.items = this.items.filter((it) => it.id !== id)
      } finally {
        this.mutating = false
      }
    },

    /**
     * 标记条目用完（status=used）。
     * @param id 条目 ID
     * @returns 无
     * @throws 接口失败时抛出归一化 ApiError（透传 patchItem）
     */
    async markUsed(id: number): Promise<void> {
      await this.patchItem(id, { status: 'used' })
    },

    /**
     * 新增购物清单条目（后端按食材合并去重），成功后重拉清单。
     * @param body 新增条目列表
     * @returns 无
     * @throws 接口失败时抛出归一化 ApiError（mutating 保证复位）
     */
    async addShopping(body: ShoppingCreateBody): Promise<void> {
      this.mutating = true
      try {
        await postShoppingList(body)
        await this.loadShopping()
      } finally {
        this.mutating = false
      }
    },

    /**
     * 删除购物清单条目。
     * @param id 条目 ID
     * @returns 无
     * @throws 接口失败时抛出归一化 ApiError（mutating 保证复位）
     */
    async removeShopping(id: number): Promise<void> {
      this.mutating = true
      try {
        await deleteShoppingItem(id)
        this.shoppingItems = this.shoppingItems.filter((it) => it.id !== id)
      } finally {
        this.mutating = false
      }
    },

    /**
     * 切换购物条目勾选态（纯本地态：契约中购物清单无勾选同步端点，
     * 「清空已购」与「转入库存」按勾选结果驱动真实请求）。
     * @param id 条目 ID
     * @returns 无
     */
    toggleShopping(id: number): void {
      const target = this.shoppingItems.find((it) => it.id === id)
      if (!target) return
      target.checked = !target.checked
    },

    /**
     * 购物条目一键转入库存，成功后双列表重拉。
     * @param id 条目 ID
     * @returns 无
     * @throws 接口失败时抛出归一化 ApiError（mutating 保证复位）
     */
    async toInventory(id: number): Promise<void> {
      this.mutating = true
      try {
        await postShoppingToInventory(id)
        await Promise.all([this.loadShopping(), this.loadItems()])
      } finally {
        this.mutating = false
      }
    },

    /**
     * 清空已购（勾选为 true 的条目逐条删除）。
     * @returns 无
     * @throws 接口失败时抛出归一化 ApiError（mutating 保证复位）
     */
    async clearChecked(): Promise<void> {
      this.mutating = true
      try {
        const checked = this.shoppingItems.filter((it) => it.checked)
        await Promise.all(checked.map((it) => deleteShoppingItem(it.id)))
        this.shoppingItems = this.shoppingItems.filter((it) => !it.checked)
      } finally {
        this.mutating = false
      }
    },
  },
})

/**
 * 计算目标日期距今天的天数（负数 = 已过期）。
 * @param expireDate 到期日（YYYY-MM-DD；空串/非法返回正无穷视为不临期）
 * @returns 剩余天数
 */
export function daysUntil(expireDate: string): number {
  if (!expireDate) return Number.POSITIVE_INFINITY
  const target = new Date(`${expireDate}T00:00:00`)
  if (Number.isNaN(target.getTime())) return Number.POSITIVE_INFINITY
  const today = new Date()
  today.setHours(0, 0, 0, 0)
  return Math.round((target.getTime() - today.getTime()) / 86400000)
}
