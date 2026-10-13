/**
 * 文件职责：Pinia store 统一出口（barrel）——阶段二小程序 11 个 store 集中转发，
 * 页面/组件统一从本文件导入，便于保持导入路径稳定。
 */
export { useSessionStore } from './session'
export { useConfigStore } from './config'
export { useHomeStore } from './home'
export { useAskStore } from './ask'
export { useIngredientsStore, INGREDIENT_CATEGORIES } from './ingredients'
export type { CategoryOption, SelectedIngredient } from './ingredients'
export {
  useRecommendStore,
  FILTER_REASON_TYPE_LABELS,
  filterReasonLabel,
} from './recommend'
export { useCookingStore } from './cooking'
export { useProfileStore } from './profile'
export { useInventoryStore, daysUntil } from './inventory'
export { useMeStore } from './me'
export { useInnovationStore } from './innovation'
