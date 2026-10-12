/**
 * 文件职责：搜索分流与查询词分类纯函数（DEF-02 修复配套）。
 * - decideHomeSearchRoute：首页搜索框回车的四分支分流决策（纯函数，便于单测）；
 * - classifyQueryResult：食材选择页消费 ?q= 的三类结果分类
 *   （命中菜谱 / 回退食材定位 / 双未命中走既有空态）；
 * - 纯函数不依赖组件与 store，View 层只负责执行路由跳转与状态更新。
 */

/**
 * 提问意图判定正则（与 HomeView / SelectIngredientView 原有口径同源：
 * 疑问词/问号/祈使词视为提问而非纯搜索）。
 */
export const QUESTION_PATTERN = /[?？]|吗|呢|怎么|怎样|如何|什么|哪些|多少|能不能|可不可以|行不行|可以|推荐/

/** 首页搜索分流决策结果 */
export type HomeSearchRoute =
  /** 空输入：交由 ask store 出单条提示，不跳转 */
  | 'emptyHint'
  /** qa 开关关闭：降级为食材名精确搜索（带 q 跳转） */
  | 'selectDegraded'
  /** 短且无疑问词：菜名/食材名搜索意图，带 q 跳食材选择页（DEF-02 修复） */
  | 'selectShort'
  /** 其余：走统一 ask 消费链路（stores/ask.submitQuestion） */
  | 'ask'

/**
 * 首页搜索框回车分流决策（纯函数，DEF-02）。
 * 说明：
 *   「宫保鸡丁」等短菜名不再丢失查询词——selectShort 分支由调用方携带
 *   q=原始输入 跳转 /select（修复前短词跳转不带 q，搜索意图完全丢失）。
 * @param text 用户输入（已 trim 或原始串均可，函数内部再 trim）
 * @param qaEnabled 问答模块开关（switch.qa 未返回时视为 true）
 * @returns 分流决策（emptyHint / selectDegraded / selectShort / ask）
 */
export function decideHomeSearchRoute(text: string, qaEnabled: boolean): HomeSearchRoute {
  const t = (text ?? '').trim()
  if (!t) return 'emptyHint'
  if (!qaEnabled) return 'selectDegraded'
  // 短且无疑问词 → 菜名/食材名搜索意图（DEF-02：带 q 跳转，不丢词）
  if (!QUESTION_PATTERN.test(t) && t.length <= 4) return 'selectShort'
  return 'ask'
}

/** 食材选择页 ?q= 消费分类结果 */
export type QueryResultKind =
  /** 命中菜谱：页面顶部呈现菜谱结果条 */
  | 'recipes'
  /** 未命中菜谱但命中食材：回退食材名定位（过滤/滚动到该食材） */
  | 'ingredient'
  /** 双未命中：走既有「试试更宽泛的关键词」空态 */
  | 'none'

/** 参与食材匹配的最小食材结构（Ingredient 的结构子集） */
export interface QueryIngredientLike {
  /** 食材名 */
  name: string
  /** 别名列表（可缺省） */
  aliases?: string[] | null
}

/**
 * 判断文本是否命中食材（名称或别名，双向包含，忽略大小写）（内部函数）。
 * @param text 待匹配文本（已 trim）
 * @param ingredients 食材候选列表
 * @returns 是否命中任一食材
 */
function matchesAnyIngredient(text: string, ingredients: QueryIngredientLike[]): boolean {
  const t = text.toLowerCase()
  if (!t) return false
  return ingredients.some((ing) => {
    const name = (ing.name ?? '').toLowerCase()
    if (name && (name === t || name.includes(t) || t.includes(name))) return true
    return (ing.aliases ?? []).some((alias) => {
      const a = (alias ?? '').toLowerCase()
      return !!a && (a === t || a.includes(t) || t.includes(a))
    })
  })
}

/**
 * 食材选择页 ?q= 消费分类（纯函数，DEF-02）。
 * 说明：
 *   a) 菜谱搜索命中 ≥1 条 → 'recipes'（展示结果条，保留食材页正常功能）；
 *   b) 未命中菜谱但文本命中食材名/别名 → 'ingredient'（回退食材名定位）；
 *   c) 双双未命中 → 'none'（既有「试试更宽泛的关键词」空态，不新增空态）。
 * @param recipes 菜谱搜索结果（允许为空数组，搜索失败时也传空数组）
 * @param q 查询词（原始输入）
 * @param ingredients 当前食材库列表（用于回退定位判定）
 * @returns 分类结果（recipes / ingredient / none）
 */
export function classifyQueryResult(
  recipes: Array<{ id: number }>,
  q: string,
  ingredients: QueryIngredientLike[],
): QueryResultKind {
  if (recipes.length > 0) return 'recipes'
  const t = (q ?? '').trim()
  if (!t) return 'none'
  return matchesAnyIngredient(t, ingredients) ? 'ingredient' : 'none'
}
