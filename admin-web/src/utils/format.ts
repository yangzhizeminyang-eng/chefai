/**
 * 文件职责：后台通用格式化纯函数（金额分转元、日期格式化、数字千分位）。
 * 仅依赖标准库，可在 node 环境下被 vitest 直接单测。
 */

/**
 * 金额分转元并格式化为两位小数字符串。
 * @param cents 金额（分），支持 null/undefined/NaN 等非法输入
 * @returns 元为单位的字符串，保留两位小数；非法输入返回 "0.00"
 */
export function formatCents(cents: number | null | undefined): string {
  const value = typeof cents === 'number' && Number.isFinite(cents) ? cents : 0
  return (Math.round(value) / 100).toFixed(2)
}

/**
 * 金额分转元并带人民币符号（展示用）。
 * @param cents 金额（分）
 * @returns 形如 "¥12.34" 的展示字符串
 */
export function formatYuan(cents: number | null | undefined): string {
  return `¥${formatCents(cents)}`
}

/**
 * 数字千分位格式化（token 用量、请求数等展示）。
 * @param value 数字，非法输入按 0 处理
 * @returns 千分位字符串
 */
export function formatNumber(value: number | null | undefined): string {
  const v = typeof value === 'number' && Number.isFinite(value) ? value : 0
  return v.toLocaleString('en-US')
}

/**
 * 日期格式化（本地时区）。
 * @param value 日期来源：Date / 时间戳 / 日期字符串等
 * @param pattern 格式模板，支持 YYYY MM DD HH mm ss 占位符
 * @returns 格式化字符串；空值或无法解析时返回 "-"
 */
export function formatDate(value: string | number | Date | null | undefined, pattern = 'YYYY-MM-DD HH:mm:ss'): string {
  if (value === null || value === undefined || value === '') return '-'
  const date = value instanceof Date ? value : new Date(value)
  if (Number.isNaN(date.getTime())) return '-'
  const pad2 = (n: number): string => String(n).padStart(2, '0')
  return pattern
    .replace(/YYYY/g, String(date.getFullYear()))
    .replace(/MM/g, pad2(date.getMonth() + 1))
    .replace(/DD/g, pad2(date.getDate()))
    .replace(/HH/g, pad2(date.getHours()))
    .replace(/mm/g, pad2(date.getMinutes()))
    .replace(/ss/g, pad2(date.getSeconds()))
}
