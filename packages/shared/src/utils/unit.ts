/**
 * 文件职责：计量单位展示工具（DEF-09 前端对齐 PRD §5.4「克 / 毫升 / 勺」三选）。
 * - formatAmount：单值用量按展示模式格式化（纯函数，vitest 可测）；
 * - formatAmountText：把文本中「数字+单位」片段按展示模式转换
 *   （菜谱食材表 amount、步骤提示等后端拼好的字符串场景）；
 * - migrateUnitSetting：历史设置键迁移（metric/imperial → 新三选枚举，
 *   读时兼容映射一次，写回一律为新值）。
 * 无 Vue / DOM / 网络 / store 依赖，全部为纯函数（相同输入恒定输出、无副作用）。
 * 从 web-stage1/src/utils/unit.ts 零改造迁移（仅本文件级注释追加迁移说明，实现与导出签名不变），
 * 供小程序端（web-mini，经 vite alias @shared 引用）与 Web 端共用。
 */

/** 计量单位展示模式（PRD §5.4 三选：克 / 毫升 / 勺） */
export type UnitMode = 'gram' | 'milliliter' | 'spoon'

/** 用户设置中的计量单位取值（新枚举；历史值 metric/imperial 读时由 migrateUnitSetting 迁移） */
export type UnitSetting = UnitMode

/** 体积类（ml 类）单位集合（小写归一后匹配；spoon 模式下换算为勺/茶匙） */
const VOLUME_UNITS = new Set(['ml', '毫升', 'l', '升'])

/** 1 勺 ≈ 15ml（与菜谱详情页「用量参照」既有说明口径一致） */
const ML_PER_SPOON = 15

/** 1 茶匙 ≈ 5ml */
const ML_PER_TEASPOON = 5

/** spoon 模式换算上限（ml）：超过 10 勺的大体积保持原值展示（如「500ml 水」用勺表达无意义） */
const MAX_SPOON_ML = ML_PER_SPOON * 10

/** 历史设置键 → 新枚举映射（读时兼容迁移一次） */
const LEGACY_UNIT_MAP: Record<string, UnitSetting> = {
  metric: 'gram',
  imperial: 'milliliter',
}

/**
 * 文本中「数字 + 重量/体积单位」片段正则（g 类与 ml 类，长词在前避免「千克」被「克」截断）。
 * 刻意不包含「勺/大勺/小勺/个/只」等单位（勺模式不重复换算、计数单位无换算语义）；
 * 单位后接字母时不算单位（后顾断言，避免英文单词被误伤）。
 */
const AMOUNT_UNIT_RE = /(\d+(?:\.\d+)?)(\s*)(千克|公斤|kg|毫升|ml|克|g|磅|lb|盎司|oz|升|l)(?![a-zA-Z])/gi

/**
 * 数值 → 展示串（整数去小数尾，最多 1 位小数）。
 * @param value 换算后的档位值（如 1、0.5、1.5）
 * @returns 展示串（如「1」「0.5」「1.5」）

 * 异常：
 *     不抛出（value 已由调用方保证为有限数）。
 */
function formatStepNum(value: number): string {
  return String(Math.round(value * 10) / 10)
}

/**
 * 中文单位与数值之间补空格（对齐「2 勺」示例）；拉丁单位直接拼接（对齐「100g」示例）。
 * @param unit 用量单位
 * @returns 分隔符（中文单位为空格，其余为空串）

 * 异常：
 *     不抛出。
 */
function unitSep(unit: string): string {
  return /[\u4e00-\u9fff]/.test(unit) ? ' ' : ''
}

/**
 * 归一化单位小写标识（trim + 小写，用于类别判定）。
 * @param unit 用量单位
 * @returns 小写标识（如 'G' → 'g'、'毫升' → '毫升'）

 * 异常：
 *     不抛出。
 */
function unitKey(unit: string): string {
  return unit.trim().toLowerCase()
}

/**
 * 毫升值 → 勺/茶匙展示文案（就近半档换算）。
 * 规则：≥7.5ml 按勺档（1 勺=15ml）就近半档；2.5~7.5ml 按茶匙档（1 茶匙=5ml）
 * 就近半档；<2.5ml 或 ≥150ml（10 勺）保持原值展示；结果固定附注「1 勺 ≈ 15ml」。
 * @param ml 毫升数（正数）
 * @param original 原始「数值+单位」串（兜底原样展示用）
 * @returns 换算后的展示文案（如「1 勺（1 勺 ≈ 15ml）」「1 茶匙（1 勺 ≈ 15ml）」）

 * 异常：
 *     不抛出（ml 已由调用方保证为有限数）。
 */
function toSpoonText(ml: number, original: string): string {
  if (ml <= 0 || ml < ML_PER_TEASPOON / 2 || ml >= MAX_SPOON_ML) return original
  const note = '（1 勺 ≈ 15ml）'
  if (ml >= ML_PER_SPOON / 2) {
    // 勺档：就近半档（0.5 步长四舍五入）
    const spoons = Math.round((ml / ML_PER_SPOON) * 2) / 2
    return `${formatStepNum(spoons)} 勺${note}`
  }
  // 茶匙档：就近半档（0.5 步长四舍五入）
  const teaspoons = Math.round((ml / ML_PER_TEASPOON) * 2) / 2
  return `${formatStepNum(teaspoons)} 茶匙${note}`
}

/**
 * 单值用量格式化（函数）。
 *
 * 说明：
 *     mode='gram' | 'milliliter'：按单位自身类别（g 类 / ml 类）原值展示（不做换算）；
 *     mode='spoon'：ml 类换算为「X 勺 / X 茶匙」（1 勺≈15ml、1 茶匙≈5ml，就近半档）
 *     并固定附注「1 勺 ≈ 15ml」；g 类保持克展示；无法归类的单位原样返回。
 *
 * @param amount 用量数值（如 100）
 * @param unit 用量单位（如 'g' / 'ml' / '勺'）
 * @param mode 展示模式（gram / milliliter / spoon）
 * @returns 展示文案（如「100g」「1 勺（1 勺 ≈ 15ml）」）；amount 非有限数返回空串；
 *          unit 为空返回纯数值串

 * 异常：
 *     不抛出（非有限数值、未知单位均有兜底）。
 */
export function formatAmount(amount: number, unit: string, mode: UnitMode): string {
  // 非有限数值兜底：不产出「NaNg」这类脏文案
  if (!Number.isFinite(amount)) return ''
  const trimmed = (unit ?? '').trim()
  // 无单位：仅展示数值
  if (!trimmed) return `${amount}`
  const sep = unitSep(trimmed)
  const original = `${amount}${sep}${trimmed}`
  // 克 / 毫升模式：按单位类别原值展示（不换算）
  if (mode === 'gram' || mode === 'milliliter') return original
  // 勺模式：仅 ml 类换算；g 类与未知单位保持原值
  const key = unitKey(trimmed)
  if (VOLUME_UNITS.has(key)) {
    // 升类单位先统一换算为 ml（'L'/'l' 均归一为 'l' 后判断）
    const ml = key === 'l' || key === '升' ? amount * 1000 : amount
    return toSpoonText(ml, original)
  }
  return original
}

/**
 * 文本用量片段格式化（函数）。
 *
 * 说明：
 *     扫描文本中所有「数字+重量/体积单位」片段，spoon 模式下把 ml 类片段换算为
 *     勺/茶匙（g 类与其他单位保持原样）；gram / milliliter 模式下文本原样返回
 *     （原值展示即目标形态，保留原文空格差异更安全）。
 *
 * @param text 原始用量文本（如「盐 2g；水 30ml」，可空）
 * @param mode 展示模式（gram / milliliter / spoon）
 * @returns 转换后的文本（如 spoon 模式「盐 2g；水 2 勺（1 勺 ≈ 15ml）」）；
 *          text 为空原样返回

 * 异常：
 *     不抛出（正则执行异常时静默降级返回原文，展示增强不阻塞渲染）。
 */
export function formatAmountText(text: string, mode: UnitMode): string {
  if (!text) return text
  // 克 / 毫升模式：文本中的「数值+单位」即目标形态，原样返回
  if (mode === 'gram' || mode === 'milliliter') return text
  try {
    return text.replace(AMOUNT_UNIT_RE, (match, num: string, _gap: string, unit: string) => {
      const converted = formatAmount(Number(num), unit, mode)
      // 换算兜底（如非有限数值）时保留原片段
      return converted === '' ? match : converted
    })
  } catch {
    // 正则异常静默降级：返回原文（展示增强不应打断页面渲染）
    return text
  }
}

/**
 * 设置键迁移：旧计量单位值 → 新三选枚举（函数）。
 *
 * 说明：
 *     历史值 metric → gram、imperial → milliliter；新值（gram/milliliter/spoon）
 *     直通；空值/未知值兜底为默认 gram。读取侧调用一次完成兼容映射，
 *     写入侧（设置页保存）只产出新值。
 *
 * @param value 设置中存储的单位原始值（可空/未知）
 * @returns 新三选枚举值（gram / milliliter / spoon）

 * 异常：
 *     不抛出（未知值兜底默认 gram）。
 */
export function migrateUnitSetting(value: string | null | undefined): UnitSetting {
  if (value === 'gram' || value === 'milliliter' || value === 'spoon') return value
  return LEGACY_UNIT_MAP[value ?? ''] ?? 'gram'
}
