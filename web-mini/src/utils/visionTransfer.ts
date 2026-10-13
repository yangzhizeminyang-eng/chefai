/**
 * 文件级注释：拍照识别（photo）→ 识别确认（recognize）页面间数据交接模块。
 * 识别响应（recognized + quota + degraded）整体写入 storage，识别确认页读取后即清除；
 * 常量独立成模块，保证两页引用同一键（避免字面量漂移）。
 * 🔴 说明：不得将此常量定义在 .vue 页面文件中——页面被其他页面 import 会在 Vite 构建
 * 时被拆为共享 chunk，产生页面双份产物（如 pages/recommend/photo2.js）与
 * "ignore files" 编译告警（历史缺陷：photo.vue/App.vue 均因此修复过，勿回退）。
 */

/** photo → recognize 识别结果交接的 storage 键（值为 VisionRecognizeResponse 整体 JSON） */
export const VISION_RESULT_KEY = 'aicook_vision_result_v1'

/**
 * 写入识别结果交接数据（photo 页识别成功后调用）。
 * @param response 识别响应整体（recognized + quota + degraded）
 * @returns 无
 * @throws 不抛出（storage 写入失败静默，页面上层已 toast 主流程错误）
 */
export function saveVisionHandoff(response: unknown): void {
  try {
    uni.setStorageSync(VISION_RESULT_KEY, JSON.stringify(response))
  } catch {
    // 交接写入失败静默：主流程错误已由页面 toast，交接缺失仅影响确认页兜底提示
  }
}

/**
 * 读取并清除识别结果交接数据（recognize 页确认页读取后即清除，防止残留脏数据）。
 * @param T 期望的响应类型（调用方传入 VisionRecognizeResponse）
 * @returns 解析后的响应；不存在或解析失败返回 null
 * @throws 不抛出（读取/解析失败静默返回 null，页面按无交接数据处理）
 */
export function takeVisionHandoff<T>(): T | null {
  try {
    const raw = uni.getStorageSync(VISION_RESULT_KEY)
    if (!raw) {
      return null
    }
    uni.removeStorageSync(VISION_RESULT_KEY)
    return JSON.parse(String(raw)) as T
  } catch {
    return null
  }
}
