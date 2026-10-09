/**
 * 文件职责：POST /v1/ask 消费链路的纯函数集（空输入守卫 + 意图分流 + 结果映射）。
 * 无 Vue / Pinia / 路由 / 网络依赖，可被 vitest node 环境直接单测
 * （见 src/utils/__tests__/askFlow.spec.ts，Task：修复「问厨娘闭环断裂」）。
 * 消费链路：视图（HomeView / SelectIngredientView）→ stores/ask.submitQuestion
 *   → isBlankQuestion（空输入守卫：不发请求，仅提示「请输入内容」）
 *   → postAsk → resolveAskAction（按响应意图分流：blocked / recipe_search / chat）
 *   → recipe_search 分支经 recipeDetailToAskItem 把菜谱详情映射为推荐卡片数据，
 *     落入 recommend store 后跳 /recommend（与手选食材路径同终端视图）。
 */
import type { AskResponse, BlockedResponse, RecipeDetail, RecommendResultItem } from '@/api/types'

/**
 * ask 消费动作（resolveAskAction 的输出；调用方 stores/ask 按 type 执行副作用）。
 */
export type AskAction =
  /** 命中风控一票否决：payload 为短路响应体，写入 recommend store 后跳 W-05 拦截页 */
  | { type: 'blocked'; payload: BlockedResponse }
  /** 菜谱搜索命中：按 recipeIds 拉取详情落推荐态，随后跳 /recommend */
  | { type: 'recipe_search'; recipeIds: number[] }
  /** 受限问答 / 搜索无结果 / 其他意图：就地展示回答（answer 已含兜底文案，非空） */
  | { type: 'chat'; answer: string }

/** 搜索无结果（intent=recipe_search 但 recipe_ids 为空）时的兜底回答文案 */
export const NO_RECIPE_ANSWER = '没有找到相关菜谱，换个说法或补充一些食材信息试试？'

/** 响应未携带回答内容（intent=free_qa 无 answer、或其他未知意图）时的兜底文案 */
export const EMPTY_ANSWER = '厨娘暂时没有答案，换个问题试试？'

/**
 * 判断用户输入是否为空白输入（trim 后为空串）。
 * 空白输入不发起 POST /v1/ask 请求，由调用方提示「请输入内容」（缺陷 A1：空输入静默无响应）。
 * @param text 用户输入原文（可为未 trim 的原始值）
 * @returns 是否空白输入（true = 不应发请求）
 */
export function isBlankQuestion(text: string): boolean {
  return text.trim().length === 0
}

/**
 * 按 /v1/ask 响应意图分流消费动作（纯函数，无副作用，分流优先级 blocked > recipe_search > chat）。
 * 分流规则：
 * - res.blocked 存在 → blocked（携带短路体，调用方跳 W-05，行为与既有链路一致）；
 * - intent=recipe_search 且 recipe_ids 非空 → recipe_search（按 ids 拉详情落推荐态）；
 * - intent=recipe_search 但 ids 缺失/为空 → chat（展示「没有找到相关菜谱」兜底文案）；
 * - intent=free_qa → chat（展示 answer；answer 缺失时用通用兜底文案）；
 * - intent=recommend 或未知意图（后端未携带可消费负载）→ chat 兜底展示，不做跳转。
 * @param res POST /v1/ask 响应体（契约类型 AskResponse）
 * @returns 消费动作（type 判别联合）
 */
export function resolveAskAction(res: AskResponse): AskAction {
  if (res.blocked) {
    return { type: 'blocked', payload: res.blocked }
  }
  if (res.intent === 'recipe_search') {
    if (res.recipe_ids && res.recipe_ids.length > 0) {
      return { type: 'recipe_search', recipeIds: res.recipe_ids }
    }
    return { type: 'chat', answer: NO_RECIPE_ANSWER }
  }
  return { type: 'chat', answer: res.answer || EMPTY_ANSWER }
}

/**
 * 菜谱详情 → 推荐卡片数据（ask 搜索结果落入 recommend store 推荐态用）。
 * ask 链路只有菜谱 ID 列表（无食材匹配信息），映射约定：
 * - covered/missing 置空数组（推荐卡片不展示覆盖率，由视图在 askMode 下隐藏该列）；
 * - match_level 固定 can_cook_now（随三档分组首档「现在就能做」展示，均为可做的具体菜谱）；
 * - rank_reasons 标注来源问句（「为什么推荐给你」弹层如实说明）。
 * @param detail GET /v1/recipes/{id} 返回的菜谱详情
 * @param question 触发本次搜索的用户问句（用于 rank_reasons 溯源）
 * @returns 推荐结果条目（RecommendResultItem，兼容 W-02 既有卡片渲染）
 */
export function recipeDetailToAskItem(detail: RecipeDetail, question: string): RecommendResultItem {
  return {
    recipe_id: detail.id,
    title: detail.title,
    match_level: 'can_cook_now',
    covered_ingredients: [],
    missing_ingredients: [],
    time_minutes: detail.time_minutes,
    difficulty: detail.difficulty,
    calories_kcal: detail.calories_kcal,
    allergens: detail.allergen_codes,
    required_equipment: detail.equipment,
    rank_score: 0,
    rank_reasons: [`来自你的提问「${question}」`],
    source: detail.source_label,
  }
}
