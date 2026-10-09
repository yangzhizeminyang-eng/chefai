/**
 * 文件职责：后台管理端路由表与导航守卫。
 * - 未登录（无 token）访问业务页一律重定向 /login；
 * - 已登录访问 /login 自动进入看板；
 * - 路由元信息统一维护页面标题（afterEach 设置 document.title）。
 */
import { createRouter, createWebHistory } from 'vue-router'
import type { RouteRecordRaw } from 'vue-router'

import { TOKEN_KEY } from '@/api/admin'

/** 路由元信息：页面标题 */
declare module 'vue-router' {
  interface RouteMeta {
    title?: string
  }
}

/** 路由表：登录页 + 后台布局（含 14 个业务子页面） */
const routes: RouteRecordRaw[] = [
  {
    path: '/login',
    name: 'login',
    component: () => import('@/views/admin/LoginView.vue'),
    meta: { title: '登录' },
  },
  {
    path: '/',
    component: () => import('@/views/admin/AdminLayout.vue'),
    redirect: '/dashboard',
    children: [
      { path: 'dashboard', name: 'dashboard', component: () => import('@/views/admin/DashboardView.vue'), meta: { title: '看板' } },
      { path: 'recipes', name: 'recipes', component: () => import('@/views/admin/RecipeManageView.vue'), meta: { title: '菜谱管理' } },
      { path: 'ingredients', name: 'ingredients', component: () => import('@/views/admin/IngredientManageView.vue'), meta: { title: '食材库' } },
      { path: 'nutrition', name: 'nutrition', component: () => import('@/views/admin/NutritionView.vue'), meta: { title: '营养数据' } },
      { path: 'risk-rules', name: 'risk-rules', component: () => import('@/views/admin/RiskRuleView.vue'), meta: { title: '风控规则' } },
      { path: 'sensitive-words', name: 'sensitive-words', component: () => import('@/views/admin/SensitiveWordsView.vue'), meta: { title: '违禁词' } },
      { path: 'trace-logs', name: 'trace-logs', component: () => import('@/views/admin/TraceLogView.vue'), meta: { title: 'Agent 日志' } },
      { path: 'feedbacks', name: 'feedbacks', component: () => import('@/views/admin/FeedbackTicketView.vue'), meta: { title: '反馈工单' } },
      { path: 'admin-users', name: 'admin-users', component: () => import('@/views/admin/AdminUserView.vue'), meta: { title: '成员权限' } },
      { path: 'operation-logs', name: 'operation-logs', component: () => import('@/views/admin/OperationLogView.vue'), meta: { title: '操作日志' } },
      { path: 'switches', name: 'switches', component: () => import('@/views/admin/SwitchManageView.vue'), meta: { title: '远程开关' } },
      { path: 'orders', name: 'orders', component: () => import('@/views/admin/OrderManageView.vue'), meta: { title: '订单管理' } },
      { path: 'innovation-rules', name: 'innovation-rules', component: () => import('@/views/admin/InnovationRuleView.vue'), meta: { title: '创新规则库' } },
      { path: 'innovation-inspect', name: 'innovation-inspect', component: () => import('@/views/admin/InnovationInspectView.vue'), meta: { title: '创新菜巡检' } },
    ],
  },
  // 未匹配路径兜底回首页
  { path: '/:pathMatch(.*)*', redirect: '/' },
]

const router = createRouter({
  // base 取 Vite BASE_URL：dev 与根路径部署为 '/'（行为不变），
  // 容器栈 Dockerfile.web 以 --base=/admin/ 构建，子路径托管时路由 base 同步为 /admin/
  history: createWebHistory(import.meta.env.BASE_URL),
  routes,
})

/**
 * 全局前置守卫：登录态校验。
 * @param to 目标路由
 * @returns 放行返回 true，否则返回重定向目标
 */
router.beforeEach((to) => {
  const hasToken = Boolean(localStorage.getItem(TOKEN_KEY))
  if (to.path !== '/login' && !hasToken) return { path: '/login' }
  if (to.path === '/login' && hasToken) return { path: '/dashboard' }
  return true
})

/**
 * 全局后置钩子：设置页面标题。
 * @param to 目标路由
 */
router.afterEach((to) => {
  document.title = to.meta.title ? `${to.meta.title} · AI 厨娘管理后台` : 'AI 厨娘管理后台'
})

export default router
