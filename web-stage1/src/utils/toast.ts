/**
 * 文件职责：ElMessage 轻封装（全局 toast 防堆叠，供新增代码统一复用）。
 * 背景：项目内 toast 原为散调 ElMessage（15+ 处），连续触发相同文案时会纵向堆叠
 * 多条提示（缺陷 M1/N5：/select 页空态提示、推荐守卫 toast、ask 结果 toast 三路同时弹出）。
 * 本封装统一携带 grouping: true——相同文案在分组窗口内合并为一条计数展示；
 * 不同文案仍各自出现，但视图层已通过 if/else 互斥保证单路提示（见 SelectIngredientView）。
 * 约定：新增/修改代码一律使用本工具；存量散调 ElMessage 的位置按需逐步迁移。
 */
import { ElMessage } from 'element-plus'

/**
 * 成功提示（grouping 防堆叠）。
 * @param message 提示文案
 * @returns 无
 */
export function toastSuccess(message: string): void {
  ElMessage.success({ message, grouping: true })
}

/**
 * 警示提示（grouping 防堆叠）。
 * @param message 提示文案
 * @returns 无
 */
export function toastWarning(message: string): void {
  ElMessage.warning({ message, grouping: true })
}

/**
 * 信息提示（grouping 防堆叠）。
 * @param message 提示文案
 * @returns 无
 */
export function toastInfo(message: string): void {
  ElMessage.info({ message, grouping: true })
}

/**
 * 错误提示（grouping 防堆叠）。
 * @param message 提示文案
 * @returns 无
 */
export function toastError(message: string): void {
  ElMessage.error({ message, grouping: true })
}
