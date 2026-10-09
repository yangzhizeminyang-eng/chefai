/**
 * 文件职责：菜谱展示相关纯工具函数集合（Task 11 前端单测目标模块）。
 * 无 Vue / DOM / 网络 / store 依赖，全部为纯函数（相同输入恒定输出、无副作用），
 * 可被 vitest 在 node 环境直接单测（见 src/utils/__tests__/recipe.spec.ts）。
 * 收敛自视图内联逻辑：三档分组与覆盖率（W-02 RecommendView）、成本格式化（W-06 TracePanelView）；
 * 用量缩放 / 量化展示 / 数字难度 / 致敏原映射为本模块新增的规范化实现。
 */
import type { RecommendResultItem } from '@/api/types'

/**
 * 量化用量原始值（菜谱食材行的数值化字段）。
 * 与 RecipeIngredientItem.amount（后端拼好的字符串）互补，用于前端本地缩放/拼装场景。
 */
export interface QuantifiedAmount {
  /** 单值用量（如 100；null/undefined 表示未提供单值） */
  amount_value?: number | null
  /** 区间用量下限（与 amount_max 同时提供时优先展示区间） */
  amount_min?: number | null
  /** 区间用量上限 */
  amount_max?: number | null
  /** 用量单位（如 g / ml / 勺；可为空） */
  amount_unit?: string | null
  /** 用量补充说明（如「1 勺 ≈ 15ml」；存在时追加在括号内） */
  amount_note?: string | null
}

/** GB 7718 八类致敏原编码 → 中文名映射（未收录编码由 allergenLabel 原样返回） */
const ALLERGEN_LABELS: Record<string, string> = {
  gluten: '含麸质谷物',
  crustacean: '甲壳类',
  fish: '鱼类',
  egg: '蛋类',
  peanut: '花生',
  soybean: '大豆',
  milk: '乳制品',
  nuts: '坚果',
}

/** 数字难度档位 → 中文标签映射（1~5 之外由 difficultyLabel 回退「中等」） */
const DIFFICULTY_LABELS: Record<number, string> = {
  1: '简单',
  2: '容易',
  3: '中等',
  4: '较难',
  5: '困难',
}

/**
 * 用量线性缩放：按份数系数等比缩放用量值，结果保留 1 位小数。
 * @param value 原始用量值（null 表示无量化数据，原样透传 null，不按 0 计）
 * @param factor 缩放系数（如份数 2→4 时 factor=2）
 * @returns 缩放后的用量值（保留 1 位小数）；value 为 null 时返回 null
 */
export function scaleAmount(value: number | null, factor: number): number | null {
  if (value == null) return null
  // 先乘后四舍五入到 1 位小数，规避浮点误差（如 0.3*3 = 0.8999...）
  return Math.round(value * factor * 10) / 10
}

/**
 * 量化用量 → 展示文案。
 * 优先级：区间（min/max 齐备且不等）> 单值；区间 min==max 时按单值展示。
 * 规则：单值 → 「100g」；区间 → 「300–500g」（en dash 连接）；单值带说明 → 「2 勺（1 勺 ≈ 15ml）」。
 * 中文单位（如「勺」）与数值之间补一个空格；拉丁单位（g / ml 等）与数值直接拼接。
 * @param item 量化用量原始值（各字段均可缺省/为 null）
 * @returns 展示文案；无任何量化数据时返回空串（由调用方决定占位符）
 */
export function amountText(item: QuantifiedAmount): string {
  const unit = item.amount_unit ?? ''
  // 中文单位（如「勺」）前补空格（对齐「2 勺」示例）；拉丁单位直接拼接（对齐「100g」示例）
  const sep = /[\u4e00-\u9fff]/.test(unit) ? ' ' : ''
  // 区间优先：min/max 同时提供时展示「min–max 单位」
  if (item.amount_min != null && item.amount_max != null) {
    if (item.amount_min === item.amount_max) return `${item.amount_min}${sep}${unit}`
    return `${item.amount_min}–${item.amount_max}${sep}${unit}`
  }
  // 单值兜底：有说明时追加全角括号备注（如勺参照）
  if (item.amount_value != null) {
    const base = `${item.amount_value}${sep}${unit}`
    return item.amount_note ? `${base}（${item.amount_note}）` : base
  }
  return ''
}

/**
 * 数字难度档位 → 中文标签。
 * @param d 难度档位（1 简单 / 2 容易 / 3 中等 / 4 较难 / 5 困难）
 * @returns 中文标签；越界（<1、>5 或非整数档位）回退「中等」
 */
export function difficultyLabel(d: number): string {
  return DIFFICULTY_LABELS[d] ?? '中等'
}

/**
 * 推荐结果按 match_level 三档分组（✅现在就能做 / 🛒差1–2样 / 💡需要多买几样）。
 * 各档内部保持原数组顺序；match_level 不属于三档的条目（异常数据）被过滤，不落入任何档。
 * @param results 推荐结果条目数组
 * @returns 三档分组结果（键与 match_level 枚举一一对应，值可能为空数组）
 */
export function groupResults(results: RecommendResultItem[]): {
  can_cook_now: RecommendResultItem[]
  missing_1_2: RecommendResultItem[]
  need_more: RecommendResultItem[]
} {
  return {
    can_cook_now: results.filter((r) => r.match_level === 'can_cook_now'),
    missing_1_2: results.filter((r) => r.match_level === 'missing_1_2'),
    need_more: results.filter((r) => r.match_level === 'need_more'),
  }
}

/**
 * 食材覆盖率百分比 = 已覆盖数 /（已覆盖数 + 缺失数）× 100。
 * @param covered 已覆盖（用户现有）食材名列表
 * @param missing 缺失食材名列表
 * @returns 覆盖率（0~100 整数，四舍五入）；分母为 0（两个列表均空）时返回 0
 */
export function coveragePercent(covered: string[], missing: string[]): number {
  const total = covered.length + missing.length
  if (total === 0) return 0
  return Math.round((covered.length / total) * 100)
}

/**
 * 致敏原编码 → 中文名（GB 7718 八类）。
 * @param code 致敏原编码（如 gluten / peanut）
 * @returns 中文名（gluten→含麸质谷物、crustacean→甲壳类、fish→鱼类、egg→蛋类、
 *          peanut→花生、soybean→大豆、milk→乳制品、nuts→坚果）；未收录编码原样返回
 */
export function allergenLabel(code: string): string {
  return ALLERGEN_LABELS[code] ?? code
}

/**
 * 成本（分）→ 元展示文案，保留 4 位小数（trace 面板与 token 成本展示用）。
 * @param cents 成本（分）；null 表示无成本数据
 * @returns 形如「¥0.0021」的字符串；cents 为 null 时返回「-」
 */
export function formatCost(cents: number | null): string {
  if (cents == null) return '-'
  return `¥${(cents / 100).toFixed(4)}`
}
