/**
 * 文件职责：食材库与已选食材状态（W-01 数据源；自 web-stage1/src/stores/ingredients.ts 逐行迁移）。
 * - categories：十类分类常量（对齐架构文档食材分类）；
 * - list/loading/error：食材列表三态；
 * - loadIngredients(category?, q?)：按分类/关键词（含别名）拉取；
 * - selected：已选食材 Map（id → {id, name}），toggle/clear 维护；
 * - selected 经 @/utils/storage 持久化（key: aicook_selected_ingredients_v1）：
 *   store 初始化时恢复、toggle/clear 时写回，应用重进不丢（S10/L2 修复）。
 * 平台差异：原会话级存储改由 storage.ts 统一承载（storage.get 已完成 JSON 反序列化
 * 与失败兜底，恢复逻辑相应适配"已解析值"入参，校验规则逐条保持）。
 */
import { defineStore } from 'pinia'
import { getIngredients, type IngredientListResponse } from '@/api/endpoints'
import type { ApiError, Ingredient } from '@shared/types'
import { get as storageGet, set as storageSet } from '@/utils/storage'

/** 分类选项结构 */
export interface CategoryOption {
  /** 分类编码（传给后端的 category 参数） */
  code: string
  /** 分类中文名（展示用） */
  label: string
}

/** 已选食材持久化键（v1：结构变更有需时升版本号） */
const SELECTED_KEY = 'aicook_selected_ingredients_v1'

/**
 * 从本地存储恢复已选食材（store 初始化时调用，S10/L2 修复）。
 * storage.get 内部已完成 JSON 反序列化：键缺失 / 空值 / 解析失败均返回 undefined，
 * 结构非法（数组 / 标量）与条目脏数据在此逐层校验过滤，不抛异常阻塞启动。
 * @returns 已选食材 Map（id → {id, name}）；无有效数据时为 {}
 * @throws 不抛出（任何异常回退空选择）
 */
function restoreSelected(): Record<number, SelectedIngredient> {
  try {
    const parsed: unknown = storageGet<unknown>(SELECTED_KEY)
    if (parsed === null || typeof parsed !== 'object' || Array.isArray(parsed)) return {}
    // 逐条校验结构（id 数字 / name 字符串），过滤脏数据避免污染推荐请求
    const restored: Record<number, SelectedIngredient> = {}
    for (const [key, value] of Object.entries(parsed as Record<string, unknown>)) {
      const id = Number(key)
      const item = value as Partial<SelectedIngredient> | null
      if (Number.isInteger(id) && id > 0 && typeof item?.id === 'number' && typeof item?.name === 'string') {
        restored[id] = { id, name: item.name }
      }
    }
    return restored
  } catch {
    // 结构校验意外异常：回退空选择
    return {}
  }
}

/**
 * 将已选食材写入本地存储（toggle/clear 后调用，S10/L2 修复）。
 * storage.set 内部 JSON 序列化并全捕获异常（超限拒绝写入 / 存储不可用静默）。
 * @param selected 当前已选食材 Map（id → {id, name}）
 * @returns 无（持久化失败静默忽略，不影响内存态）
 * @throws 不抛出（storage 层已兜底）
 */
function persistSelected(selected: Record<number, SelectedIngredient>): void {
  storageSet(SELECTED_KEY, selected)
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
    /** 已选食材 Map：id → {id, name}（用 Record 便于持久化与响应式遍历；初始化时从本地存储恢复） */
    selected: restoreSelected(),
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
     * @returns 无
     * @throws 不抛出（失败写入 error 三态并清空列表）
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
     * @returns 无
     */
    toggle(ing: Ingredient): void {
      if (this.selected[ing.id]) {
        // 已选 → 取消选中
        delete this.selected[ing.id]
      } else {
        // 未选 → 加入（用解构保证响应式）
        this.selected = { ...this.selected, [ing.id]: { id: ing.id, name: ing.name } }
      }
      // S10/L2：选中态变化即写回本地存储，应用重进后恢复
      persistSelected(this.selected)
    },

    /**
     * 清空全部已选食材。
     * @returns 无
     */
    clear(): void {
      this.selected = {}
      // S10/L2：清空同样写回本地存储（空对象），保持两侧一致
      persistSelected(this.selected)
    },
  },
})
