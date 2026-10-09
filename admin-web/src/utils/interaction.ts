/**
 * 文件职责：通用交互辅助（写操作前统一确认框）。
 */
import { ElMessageBox } from 'element-plus'

/**
 * 弹出统一确认框（所有写操作前置确认）。
 * @param message 确认文案
 * @param title 弹窗标题，默认「操作确认」
 * @returns 用户点击确定返回 true；取消或关闭返回 false
 */
export async function confirmAction(message: string, title = '操作确认'): Promise<boolean> {
  try {
    await ElMessageBox.confirm(message, title, {
      type: 'warning',
      confirmButtonText: '确定',
      cancelButtonText: '取消',
    })
    return true
  } catch {
    return false
  }
}
