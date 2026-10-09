/**
 * 文件职责：食材库与已选食材状态（W-01 数据源）。
 * - categories：十类分类常量（对齐架构文档食材分类）；
 * - list/loading/error：食材列表三态；
 * - loadIngredients(category?, q?)：按分类/关键词（含别名）拉取；
 * - selected：已选食材 Map（id → {id, name}），toggle/clear 维护。
 */
import { defineStore } from 'pinia'
import { getIngredients, type IngredientListResponse } from '@/api/endpoints'
import type { Ingredient } from '@/api/types'
import type { ApiError } from '@/api/types'

/** 分类选项结构 */
export interface CategoryOption {
  /** 分类编码（传给后端的 category 参数） */
  code: string
  /** 分类中文名（展示用） */
  label: string
}

/** 食材十类分类常量（ veg 蔬菜 / meat 肉禽 / seafood 水产 / egg_milk 蛋奶 / soy 豆制品 / staple 主食 / seasoning 调味品 / dry 干货 / frozen 冷冻 / other 其他） */
export const INGREDIENT_CATEGORIES: CategoryOption[] = [
  { code: 'veg', label: '蔬菜' },
  { code: 'meat', label: '肉禽' },
  { code: 'seafood', label: '水产' },
  { code: 'egg_milk', label: '蛋奶' },
  { code: 'soy', label: '豆制品' },
  { code: 'staple', label: '主食' },
  { code: 'seasoning', label: '调味品' },
  { code: 'dry', label: '干货' },
  { code: 'frozen', label: '冷冻' },
  { code: 'other', label: '其他' },
]

/** 已选食材条目 */
export interface SelectedIngredient {
  /** 食材 ID */
  id: number
  /** 食材名 */
  name: string
}

export const useIngredientsStore = defineStore('ingredients', {
  state: () => ({
    /** 分类常量（组件直接读取，避免重复定义） */
    categories: INGREDIENT_CATEGORIES,
    /** 当前加载出的食材列表 */
    list: [] as Ingredient[],
    /** 列表加载中标记 */
    loading: false,
    /** 列表加载错误信息（归一化 ApiError，null 表示无错） */
    error: null as ApiError | null,
    /** 已选食材 Map：id → {id, name}（用 Record 便于持久化与响应式遍历） */
    selected: {} as Record<number, SelectedIngredient>,
  }),
  getters: {
    /**
     * 已选食材数量。
     * @returns 数量
     */
    selectedCount: (state): number => Object.keys(state.selected).length,
    /**
     * 已选食材数组（供推荐请求体使用）。
     * @returns 已选条目数组
     */
    selectedList: (state): SelectedIngredient[] => Object.values(state.selected),
  },
  actions: {
    /**
     * 拉取食材列表（按分类 / 关键词含别名过滤），维护三态。
     * @param category 分类编码（可选，缺省拉全部）
     * @param q 关键词（可选，后端含别名搜索）
     */
    async loadIngredients(category?: string, q?: string): Promise<void> {
      this.loading = true
      this.error = null
      try {
        const res: IngredientListResponse = await getIngredients({ category, q })
        this.list = res.items ?? []
      } catch (e) {
        this.error = e as ApiError
        this.list = []
      } finally {
        this.loading = false
      }
    },

    /**
     * 切换某食材的选中态（已选则取消，未选则加入）。
     * @param ing 食材（需含 id 与 name）
     */
    toggle(ing: Ingredient): void {
      if (this.selected[ing.id]) {
        // 已选 → 取消选中
        delete this.selected[ing.id]
      } else {
        // 未选 → 加入（用解构保证响应式）
        this.selected = { ...this.selected, [ing.id]: { id: ing.id, name: ing.name } }
      }
    },

    /**
     * 清空全部已选食材。
     */
    clear(): void {
      this.selected = {}
    },
  },
})
