/**
 * 文件职责：步骤用量提示（amount_hint）份数缩放管线（纯函数，vitest 可测）。
 * 背景（缺陷 M3/R3）：菜谱详情与烹饪模式的「本步用量」为静态文案，
 * 不随份数缩放；本模块把文本中的「数字 + 单位」片段按 份数/基准份数 等比缩放。
 * 规则（与食材表缩放口径一致，见 utils/recipe.ts 的 scaleAmount）：
 *       ① 仅缩放带明确单位的用量（g/千克/ml/L/个/只/根/片/块/勺/大勺/小勺/瓣/颗 等）；
 *       ② 支持「1~2g」「1-2g」范围格式 → 等比缩放为「2~4g」（两端各自缩放）；
 *       ③ 时间单位（分钟/秒/小时）不参与缩放（腌制 10 分钟仍是 10 分钟）；
 *       ④ 无单位的数字不缩放（如「冲洗 2 遍」的序数/次数）；
 *       ⑤ 取整策略复用 recipe.ts scaleAmount：乘后四舍五入保留 1 位小数。
 */
import { scaleAmount } from './recipe'

/**
 * 参与缩放的单位正则片段（交替分支，长词在前避免「千克」被「克」截断）。
 * 刻意不包含时间单位（分钟/秒/小时）与无单位量词（遍/次/成 等），保证不误伤。
 */
const UNIT_GROUP = String.raw`(?:千克|公斤|kg|毫升|ml|克|g|大勺|小勺|勺|升|L|个|只|根|片|块|瓣|颗)`

/** 范围用量正则：「数字 分隔符(~～-) 数字 单位」，组号 1~7（分组内联注释见 parseAmountTokens） */
const RANGE_RE = String.raw`(\d+(?:\.\d+)?)(\s*)([~～\-])(\s*)(\d+(?:\.\d+)?)(\s*)(${UNIT_GROUP})`
/** 单值用量正则：「数字 单位」，组号 8~10（分组内联注释见 parseAmountTokens） */
const SINGLE_RE = String.raw`(\d+(?:\.\d+)?)(\s*)(${UNIT_GROUP})`
/** 合并匹配（g 全局替换；范围分支优先于单值分支，避免「1~2g」的左值被单值规则吃掉） */
const AMOUNT_RE = new RegExp(`${RANGE_RE}|${SINGLE_RE}`, 'g')

/**
 * 缩放数值 → 展示串（整数去小数尾，最多 1 位小数）。
 * @param value 缩放后的数值（如 600、1.5）
 * @returns 展示串（如「600」「1.5」）
 */
function formatScaled(value: number): string {
  return String(value)
}

/**
 * 解析并等比缩放步骤用量提示文本（函数）。
 *
 * 说明：
 *     扫描文本中所有「数字+单位」片段（含范围格式），按 factor 等比缩放后原位回填；
 *     其余字符（食材名、标点、时间、无单位数字）原样保留。
 *
 * @param text 原始用量提示文本（如「番茄 300g；鸡蛋 3 个」「盐 1~2g；糖 3g」）
 * @param factor 缩放系数（= 目标份数 / 菜谱基准份数；1 表示不缩放）
 * @returns 缩放后的文本（如 factor=2 时「番茄 600g；鸡蛋 6 个」「盐 2~4g；糖 6g」）；
 *          text 非法或 factor 不为有限正数时原样返回
 *
 * 异常：
 *     不抛出（正则执行失败时返回原文，缩放属展示增强不应打断页面渲染）。
 */
export function scaleAmountHintText(text: string, factor: number): string {
  if (!text || !Number.isFinite(factor) || factor <= 0 || factor === 1) return text
  try {
    return text.replace(AMOUNT_RE, (match, ...groups: unknown[]) => {
      // 命名展开：RANGE 分支组 1~7，SINGLE 分支组 8~10（与正则定义顺序一一对应）
      const [min, gap1, dash, gap2, max, gap3, rangeUnit, singleNum, singleGap, singleUnit] =
        groups as (string | undefined)[]
      if (min != null && max != null && rangeUnit != null) {
        // 范围分支：两端各自等比缩放（1~2g ×2 → 2~4g），保留原分隔符与空格
        const lo = scaleAmount(Number(min), factor)
        const hi = scaleAmount(Number(max), factor)
        if (lo == null || hi == null) return match
        return `${formatScaled(lo)}${dash}${formatScaled(hi)}${gap3 ?? ''}${rangeUnit}`
      }
      if (singleNum != null && singleUnit != null) {
        // 单值分支：数值缩放，保留数字与单位之间的原始空格
        const scaled = scaleAmount(Number(singleNum), factor)
        if (scaled == null) return match
        return `${formatScaled(scaled)}${singleGap ?? ''}${singleUnit}`
      }
      // 分支不完整（异常捕获兜底）：原样返回
      return match
    })
  } catch {
    // 正则异常时静默降级：返回原文（展示增强不阻塞主流程）
    return text
  }
}

/**
 * 步骤对象缩放辅助：对 amount_hint 做份数缩放（description 不缩放——
 * 步骤描述以动作说明为主，含时间等非用量信息，误伤风险高）。
 * @param hint 原始用量提示（可空）
 * @param factor 缩放系数（目标份数 / 基准份数）
 * @returns 缩放后的提示文案；hint 为空返回空串
 */
export function scaleStepHint(hint: string | null | undefined, factor: number): string {
  if (!hint) return ''
  return scaleAmountHintText(hint, factor)
}
