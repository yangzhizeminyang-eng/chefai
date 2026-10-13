/**
 * 文件职责：路由常量表（单点维护，禁止页面散落硬编码路径字符串）。
 * 覆盖 pages.json 注册的全部页面：主包 11 页 + 5 个分包共 30 页。
 *
 * 跳转边界（重要）：
 * - tabBar 页（HOME / FRIDGE / FAVORITES / ME 四个，见 TAB_BAR_PATHS）必须用
 *   uni.switchTab 跳转，uni.navigateTo 跳 tabBar 页会静默失败（无报错弹窗）；
 * - 非 tabBar 页统一用 uni.navigateTo（保留页面栈，语义对齐 vue-router push）；
 * - 免责门（P-00）与 404 兜底等「清栈重开」场景用 uni.reLaunch。
 * 便捷函数 goRoute() 内置 tabBar 判定，页面优先使用它以避免误用 navigateTo。
 */

/** 路由路径常量对象（与 pages.json 逐条对应，含分包完整路径） */
export const ROUTES = {
  /* ── 主包 ── */
  /** P-01 首页（tabBar） */
  HOME: '/pages/index/index',
  /** P-00 免责声明页（免责门目标页） */
  DISCLAIMER: '/pages/disclaimer/index',
  /** P-00b 敏感信息单独同意页（scene=allergen|goal，query 传参） */
  CONSENT: '/pages/consent/index',
  /** P-02 家庭档案列表 */
  PROFILE_LIST: '/pages/profile/list',
  /** P-03 成员编辑（query: id 可选，无 id = 新增） */
  PROFILE_MEMBER_EDIT: '/pages/profile/member-edit',
  /** P-04 厨艺与设备 */
  PROFILE_SKILL: '/pages/profile/skill',
  /** P-05 饮食目标 */
  PROFILE_GOAL: '/pages/profile/goal',
  /** P-22 我的冰箱（tabBar） */
  FRIDGE: '/pages/fridge/index',
  /** P-26/27 收藏·历史（tabBar，页内双 Tab） */
  FAVORITES: '/pages/favorites/index',
  /** P-25 我的（tabBar） */
  ME: '/pages/me/index',
  /** 404 异常页（深链分包下载失败兜底，query.redirect 可选） */
  NOT_FOUND: '/pages/notfound/index',

  /* ── 分包：pages/recommend ── */
  /** W-01 手选食材 */
  RECOMMEND_SELECT: '/pages/recommend/select',
  /** 今天吃什么（零输入随机直出 + 时令食材融合，对齐 web 端 TodayView + SeasonalView） */
  RECOMMEND_TODAY: '/pages/recommend/today',
  /** 拍照识别 */
  RECOMMEND_PHOTO: '/pages/recommend/photo',
  /** 识别结果 */
  RECOMMEND_RECOGNIZE: '/pages/recommend/recognize',
  /** 语音点菜 */
  RECOMMEND_VOICE: '/pages/recommend/voice',
  /** 推荐列表 */
  RECOMMEND_LIST: '/pages/recommend/list',
  /** 筛选结果 */
  RECOMMEND_FILTERED: '/pages/recommend/filtered',
  /** 搜索/提问 */
  RECOMMEND_SEARCH: '/pages/recommend/search',
  /** 菜谱详情（query: recipe_id） */
  RECIPE_DETAIL: '/pages/recommend/detail',

  /* ── 分包：pages/cooking ── */
  /** 过敏原确认 */
  COOK_ALLERGEN_CONFIRM: '/pages/cooking/allergen-confirm',
  /** 烹饪指导（query: session_id，断点续做同参） */
  COOK_GUIDE: '/pages/cooking/guide',
  /** 计时器 */
  COOK_TIMER: '/pages/cooking/timer',
  /** 烹饪问答 */
  COOK_ASK: '/pages/cooking/ask',
  /** 完成烹饪 */
  COOK_FINISH: '/pages/cooking/finish',

  /* ── 分包：pages/nutrition ── */
  /** 营养总览 */
  NUTRITION_SUMMARY: '/pages/nutrition/summary',
  /** 今日摄入 */
  NUTRITION_TODAY: '/pages/nutrition/today',
  /** 手动记录 */
  NUTRITION_MANUAL: '/pages/nutrition/manual',
  /** 库存条目编辑（query: id 可选，无 id = 新增，新增动作埋 inventory_add） */
  ENTRY_EDIT: '/pages/nutrition/entry-edit',
  /** 购物清单 */
  SHOPPING: '/pages/nutrition/shopping',

  /* ── 分包：pages/member ── */
  /** 签名定制 */
  SIGNATURE: '/pages/member/signature',
  /** 设置（含数据权利入口） */
  SETTINGS: '/pages/member/settings',
  /** 关于 */
  ABOUT: '/pages/member/about',
  /** 会员中心（iOS / 支付开关关闭时入口整体隐藏，RL-21 方案 B） */
  MEMBER_CENTER: '/pages/member/center',
  /** 会员权益 */
  MEMBER_BENEFITS: '/pages/member/benefits',
  /** 我的订单 */
  MEMBER_ORDERS: '/pages/member/orders',
  /** 意见反馈 */
  FEEDBACK: '/pages/member/feedback',

  /* ── 分包：pages/innovation ── */
  /** AI 创新入口 */
  INNOVATION_ENTRY: '/pages/innovation/entry',
  /** 创新确认 */
  INNOVATION_CONFIRM: '/pages/innovation/confirm',
  /** 创新结果 */
  INNOVATION_RESULT: '/pages/innovation/result',
  /** 创新详情 */
  INNOVATION_DETAIL: '/pages/innovation/detail',
  /** 我的创新 */
  INNOVATION_MINE: '/pages/innovation/mine',
} as const

/** tabBar 页路径集合（switchTab 判定依据；与 pages.json tabBar.list 逐条对应） */
export const TAB_BAR_PATHS: ReadonlySet<string> = new Set<string>([
  ROUTES.HOME,
  ROUTES.FRIDGE,
  ROUTES.FAVORITES,
  ROUTES.ME,
])

/**
 * 按目标是否 tabBar 页自动选择跳转方式（tabBar → switchTab，其余 → navigateTo），
 * 失败静默不阻断主流程（页面未落位 / 页面栈超限等）。
 * @param url 页面完整路径（以 / 开头，可带 query；tabBar 页不允许带 query）
 * @returns 无
 * @throws 不抛出（fail 回调与同步异常均静默）
 */
export function goRoute(url: string): void {
  const pathOnly = url.split('?')[0]
  const isTab = TAB_BAR_PATHS.has(pathOnly)
  const tryNavigate = (): void => {
    if (isTab) {
      uni.switchTab({ url: pathOnly, fail: () => {} })
    } else {
      uni.navigateTo({ url, fail: () => {} })
    }
  }
  try {
    tryNavigate()
  } catch {
    // 极端环境同步异常：静默，不阻断主流程
  }
}
