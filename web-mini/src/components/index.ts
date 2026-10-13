/**
 * 文件级注释：components 目录统一出口（安全件 + 业务件）。
 * 页面可经此处统一引入（`import { RiskBlockModal } from '@/components'`），
 * 也可直接路径引入（`import RiskBlockModal from '@/components/RiskBlockModal.vue'`），二者等价。
 */
// ── 安全组件（G-01/G-02/G-03 与降级/离线提示，主包内置，页面级复用） ──
export { default as RiskBlockModal } from './RiskBlockModal.vue'
export { default as DisclaimerBar } from './DisclaimerBar.vue'
export { default as AllergenAlertBar } from './AllergenAlertBar.vue'
export { default as DegradedBar } from './DegradedBar.vue'
export { default as OfflineBar } from './OfflineBar.vue'

// ── 业务组件 ──
export { default as RecipeCover } from './RecipeCover.vue'
export { default as RecipeCard } from './RecipeCard.vue'
export { default as AskChatCard } from './AskChatCard.vue'
export { default as FeedbackFab } from './FeedbackFab.vue'
export { default as IngredientGrid } from './IngredientGrid.vue'
export { default as TimerPanel } from './TimerPanel.vue'
export { default as NutritionRing } from './NutritionRing.vue'
export { default as SkeletonPage } from './SkeletonPage.vue'
export { default as EmptyState } from './EmptyState.vue'
export { default as ErrorState } from './ErrorState.vue'
export { default as PermissionGuide } from './PermissionGuide.vue'
export { default as BaseNavbar } from './BaseNavbar.vue'

// ── 组件配套类型（页面适配数据时引用） ──
export type { RecipeCardLike } from './RecipeCard.vue'
export type { IngredientGridItem, IngredientGridCategory } from './IngredientGrid.vue'
export type { NutritionRingItem } from './NutritionRing.vue'
export type { RecipeCoverSize } from './RecipeCover.vue'
export type { SkeletonType } from './SkeletonPage.vue'
export type { ErrorKind } from './ErrorState.vue'
export type { PermissionScope } from './PermissionGuide.vue'
export type { DisclaimerScene } from './DisclaimerBar.vue'
