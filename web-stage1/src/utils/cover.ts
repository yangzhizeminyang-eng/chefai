/**
 * 文件职责：程序化占位封面色板纯函数（无 Vue / DOM / 网络依赖）。
 * 用于菜谱无真实封面图（cover_image_url 为 null）时的兜底占位封面着色：
 * 按菜谱 ID 稳定映射 8 色暖色板，同一菜谱恒定同色，视觉上可区分且不闪烁。
 * 可被 vitest 在 node 环境直接单测（见 src/utils/__tests__/cover.spec.ts）。
 */

/** 8 色暖色系占位封面色板（bg 浅底 / fg 深色文字成对，保证占位文案对比度可读） */
const COVER_PALETTE: ReadonlyArray<{ bg: string; fg: string }> = [
  { bg: '#FDEBD0', fg: '#935116' }, // 奶油橙
  { bg: '#FADBD8', fg: '#922B21' }, // 番茄红
  { bg: '#FCF3CF', fg: '#7D6608' }, // 蛋黄
  { bg: '#E8F1DE', fg: '#4A6B34' }, // 抹茶
  { bg: '#F6E0C3', fg: '#7E4A1F' }, // 陶土
  { bg: '#F3EAF6', fg: '#6C3483' }, // 藕荷
  { bg: '#F2DCBB', fg: '#6E3B12' }, // 焦糖
  { bg: '#FAF0E6', fg: '#8B5A2B' }, // 米杏
]

/** 色板长度（取模基数，0~7 循环） */
const PALETTE_SIZE = COVER_PALETTE.length

/**
 * 按菜谱 ID 稳定映射占位封面色板。
 * 规则：Math.abs(recipeId) % 8 —— 同 id 恒定同色；id 连续递增时 0~7 色循环；
 * 负数 id 取绝对值后取模（与对应正数同色，不会越界或产生 NaN 索引）。
 * @param recipeId 菜谱 ID（后端自增整数，可为负）
 * @returns 色板对：bg 占位封面背景色 / fg 占位文字深色（成对保证对比度，非空 CSS 颜色字符串）
 */
export function coverPalette(recipeId: number): { bg: string; fg: string } {
  // idx 恒在 0~7（Math.abs 整数取模）索引必命中；?? 兜底仅为
  // noUncheckedIndexedAccess 下的类型收窄（对齐 utils/recipe.ts 的 `?? '中等'` 风格）
  const pair =
    COVER_PALETTE[Math.abs(recipeId) % PALETTE_SIZE] ?? { bg: '#FDEBD0', fg: '#935116' }
  // 返回拷贝：避免调用方修改污染共享色板（纯函数无副作用）
  return { bg: pair.bg, fg: pair.fg }
}
