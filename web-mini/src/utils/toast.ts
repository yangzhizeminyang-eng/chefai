/**
 * 文件职责：uni.showToast 轻封装——对齐 web-stage1/src/utils/toast.ts 的四函数语义
 * （success / warning / info / error），供小程序端所有用户提示统一复用。
 * 平台差异处理：uni.showToast 的 icon 仅支持 success / error / none 三态且文案长度受限
 * （约 2 行），故约定：success 用 icon 'success'；warning / info / error 一律
 * icon 'none' + title 纯文本（duration 2000ms），与 web 端 ElMessage 语义对齐。
 * 健壮性约定：showToast 自身任何异常（如 title 超长 fail、页面栈异常）全部吞掉，
 * 提示失败绝不抛出、绝不阻断主流程。
 */

/** 提示展示时长（毫秒，与 web 端 ElMessage 默认观感对齐） */
const TOAST_DURATION_MS = 2000

/**
 * 内部统一弹出入口。
 * @param title 提示文案
 * @param icon 图标类型（success 用 'success'，其余 'none'）
 * @returns 无
 * @throws 不抛出（fail 回调与同步异常均静默）
 */
function showToastSafe(title: string, icon: 'success' | 'none'): void {
  try {
    uni.showToast({
      title,
      icon,
      duration: TOAST_DURATION_MS,
      fail: () => {
        // showToast fail（如 title 超限）：静默，提示失败不阻断主流程
      },
    })
  } catch {
    // 极端环境（页面栈异常等）：静默
  }
}

/**
 * 成功提示（icon success）。
 * @param msg 提示文案
 * @returns 无
 * @throws 不抛出
 */
export function toastSuccess(msg: string): void {
  showToastSafe(msg, 'success')
}

/**
 * 警示提示（icon none）。
 * @param msg 提示文案
 * @returns 无
 * @throws 不抛出
 */
export function toastWarning(msg: string): void {
  showToastSafe(msg, 'none')
}

/**
 * 信息提示（icon none）。
 * @param msg 提示文案
 * @returns 无
 * @throws 不抛出
 */
export function toastInfo(msg: string): void {
  showToastSafe(msg, 'none')
}

/**
 * 错误提示（icon none）。
 * @param msg 提示文案
 * @returns 无
 * @throws 不抛出
 */
export function toastError(msg: string): void {
  showToastSafe(msg, 'none')
}
