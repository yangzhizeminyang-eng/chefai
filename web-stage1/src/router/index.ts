/**
 * 文件职责：路由定义与全局守卫。
 * 路由表（阶段一 W-01~W-06 + Task 9 新增 7 页）：
 * / → HomeView（首页直达，不再重定向）；/select、/recommend、/recipe/:id、
 * /cook/:sessionId、/blocked、/trace；新增 /profile（档案）、/inventory（冰箱与购物清单）、
 * /me（个人中心）、/member（会员）、/innovate（AI 创新）、/recognize（拍照识别）；
 * 末尾 catchAll（/:pathMatch(.*)*）→ NotFoundView（N2/L2：未知路由不再主体空白）。
 * 全局守卫：
 * - 未选任何食材进入 /recommend → 提示并回 /select（W-01）；例外：「问厨娘」搜索结果
 *   直达（recommend store askMode 已落库）放行，保证 ask 链路闭环；
 * - 无拦截数据进入 /blocked → 回 /select（防止直达空拦截页）；
 * - /cook/:sessionId 允许进入（页面自身按会话加载，不在守卫拦截）。
 */
import { createRouter, createWebHistory } from 'vue-router'
import { toastWarning } from '@/utils/toast'
import { useIngredientsStore } from '@/stores/ingredients'
import { useRecommendStore } from '@/stores/recommend'

const router = createRouter({
  history: createWebHistory(import.meta.env.BASE_URL),
  routes: [
    /** 首页（Task 9）：五大入口 + 临期提醒 + 继续上次的菜 */
    { path: '/', name: 'home', component: () => import('@/views/HomeView.vue') },
    /** W-01 食材选择 */
    { path: '/select', name: 'select', component: () => import('@/views/SelectIngredientView.vue') },
    /** W-02 推荐结果 */
    { path: '/recommend', name: 'recommend', component: () => import('@/views/RecommendView.vue') },
    /** W-03 菜谱详情（:id 菜谱 ID） */
    { path: '/recipe/:id', name: 'recipe-detail', component: () => import('@/views/RecipeDetailView.vue') },
    /** W-04 分步引导（:sessionId 烹饪会话 ID） */
    { path: '/cook/:sessionId', name: 'cook-guide', component: () => import('@/views/CookGuideView.vue') },
    /** W-05 风控拦截页 */
    { path: '/blocked', name: 'blocked', component: () => import('@/views/BlockedView.vue') },
    /** W-06 Agent 调度面板 */
    { path: '/trace', name: 'trace-panel', component: () => import('@/views/TracePanelView.vue') },
    /** Task 9 家庭档案：成员 / 厨艺设备 / 饮食目标 */
    { path: '/profile', name: 'profile', component: () => import('@/views/ProfileView.vue') },
    /** Task 9 我的冰箱 + 购物清单 */
    { path: '/inventory', name: 'inventory', component: () => import('@/views/InventoryView.vue') },
    /** Task 9 个人中心：收藏/历史/拿手菜/营养/设置/数据权利 */
    { path: '/me', name: 'me', component: () => import('@/views/MeView.vue') },
    /** Task 9 会员中心：套餐/状态额度/订单（模拟支付） */
    { path: '/member', name: 'member', component: () => import('@/views/MemberView.vue') },
    /** Task 9 AI 创新菜 */
    { path: '/innovate', name: 'innovate', component: () => import('@/views/InnovateView.vue') },
    /** Task 9 拍照识别食材 */
    { path: '/recognize', name: 'recognize', component: () => import('@/views/RecognizeView.vue') },
    /** 404 兜底（N2/L2 修复）：必须位于路由表末尾，未知路径统一进 NotFoundView */
    { path: '/:pathMatch(.*)*', name: 'not-found', component: () => import('@/views/NotFoundView.vue') },
  ],
})

/**
 * 全局前置守卫：拦截非法直达路由。
 * @param to 目标路由
 * @returns undefined 放行 / 路由地址字符串重定向
 */
router.beforeEach((to) => {
  // 守卫 1：未选食材进入推荐页 → 提示并回食材选择。
  // 例外：「问厨娘」搜索结果直达（recommend store askMode 已落库，无已选食材）→ 放行，
  // 修复闭环断裂：ask 命中 recipe_search 后不再被本守卫弹回 /select 丢弃结果。
  if (to.name === 'recommend') {
    const ingredientsStore = useIngredientsStore()
    const recommendStore = useRecommendStore()
    if (ingredientsStore.selectedCount === 0 && !recommendStore.askMode) {
      toastWarning('请先选择至少 1 样食材')
      return '/select'
    }
  }
  // 守卫 2：无拦截数据进入风控拦截页 → 回食材选择（拦截页必须由真实短路响应驱动）
  if (to.name === 'blocked') {
    const recommendStore = useRecommendStore()
    if (!recommendStore.blockedPayload) {
      return '/select'
    }
  }
  // /cook/:sessionId 不在守卫拦截：允许进入，页面自身按会话加载与兜底
  return undefined
})

export default router
