/**
 * 文件职责：「查看营养」跳转入口 query 的构造与解析（DEF-07 修复「查看营养丢份数」）。
 * - buildNutritionQuery：完成页（CookGuideView）跳转菜谱详情时构造 query
 *   （expand_nutrition=1 + servings），把本次烹饪份数带到详情页；
 * - parseNutritionQuery：详情页（RecipeDetailView）挂载时解析 query，
 *   驱动营养区自动展开与份数初始化（1~20 整数合法，对齐烹饪会话份数上限）。
 * 两侧均为纯函数，无副作用，便于 vitest 直接单测。
 */

/** 完成页 → 详情页跳转 query 的构造结果（router.push 的 query 对象） */
export interface NutritionEntryQuery {
  /** 营养区自动展开标记（恒 '1'） */
  expand_nutrition: string
  /** 本次烹饪份数（字符串化；份数非法时缺省该键） */
  servings?: string
  /** 索引签名：兼容 vue-router LocationQueryRaw（键值均为字符串形态） */
  [key: string]: string | undefined
}

/** 详情页解析结果（驱动营养区展开与份数初始化） */
export interface ParsedNutritionQuery {
  /** 是否自动展开营养估算区 */
  expand: boolean
  /** 合法份数（1~20 整数）；缺省或非法为 null（不覆盖详情页默认份数） */
  servings: number | null
}

/** 份数合法范围（对齐烹饪会话 servings 校验 1~20） */
const MIN_SERVINGS = 1
const MAX_SERVINGS = 20

/**
 * 构造完成页「查看营养」跳转 query（函数）。
 * @param session 烹饪会话快照（完成态至少携带 recipe_id 与 servings）
 * @returns query 对象：合法份数（1~20 整数）时带 servings 字符串；
 *          份数非法（异常快照）时仅带展开标记，不传错误份数
 */
export function buildNutritionQuery(session: { recipe_id: number; servings: number }): NutritionEntryQuery {
  const servings = session.servings
  if (Number.isInteger(servings) && servings >= MIN_SERVINGS && servings <= MAX_SERVINGS) {
    return { expand_nutrition: '1', servings: String(servings) }
  }
  return { expand_nutrition: '1' }
}

/**
 * 解析详情页入口 query（函数）。
 * @param query 路由 query（vue-router LocationQuery 兼容的键值视图；
 *              值可能为 string / string[] / null）
 * @returns 解析结果：expand=expand_nutrition=='1'；servings 为 1~20 整数否则 null
 */
export function parseNutritionQuery(query: Record<string, unknown>): ParsedNutritionQuery {
  // vue-router 同名参数会打包为数组，expand 与 servings 均取首值解析
  const expandRaw = Array.isArray(query.expand_nutrition)
    ? query.expand_nutrition[0]
    : query.expand_nutrition
  const expand = expandRaw === '1' || expandRaw === 1
  const raw = Array.isArray(query.servings) ? query.servings[0] : query.servings
  const num = typeof raw === 'number' ? raw : typeof raw === 'string' ? Number(raw) : Number.NaN
  const servings =
    Number.isInteger(num) && num >= MIN_SERVINGS && num <= MAX_SERVINGS ? num : null
  return { expand, servings }
}
