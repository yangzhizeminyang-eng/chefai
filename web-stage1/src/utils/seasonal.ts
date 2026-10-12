/**
 * 文件职责：时令页（SeasonalView）可抽离的纯函数工具。
 * - toggleSeasonalId：当季食材选中集合的不可变增删（返回新 Set，便于 ref 响应式替换与单测）；
 * - seasonalSubtitle：月份副标题文案生成（month 来自服务端，未加载/异常时不显示月份数字）。
 */
/** 合法月份数值（1~12）类型谓词用的下界/上界常量 */
const MIN_MONTH = 1
const MAX_MONTH = 12

/**
 * 切换某当季食材的选中态（不可变更新）：未选则加入，已选则移除。
 * @param ids 当前选中集合（只读，不修改原集合）
 * @param id 食材 ID
 * @returns 新的选中集合（原集合保持不变；幂等：同一 id 重复调用按当前态翻转）
 */
export function toggleSeasonalId(ids: ReadonlySet<number>, id: number): Set<number> {
  const next = new Set(ids)
  if (next.has(id)) {
    next.delete(id)
  } else {
    next.add(id)
  }
  return next
}

/**
 * 生成时令页月份副标题文案：month 为合法 1~12 整数时显示「N 月 · 当季食材」，
 * 未加载（null/undefined）、非整数或越界时回退为「当季食材」（不显示月份数字，不留占位符）。
 * @param month 服务端返回的月份数（可为空，加载前/降级时无值）
 * @returns 副标题文案
 */
export function seasonalSubtitle(month: number | null | undefined): string {
  if (
    typeof month !== 'number' ||
    !Number.isInteger(month) ||
    month < MIN_MONTH ||
    month > MAX_MONTH
  ) {
    return '当季食材'
  }
  return `${month} 月 · 当季食材`
}
