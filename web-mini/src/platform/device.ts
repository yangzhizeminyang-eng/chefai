/**
 * 文件职责：设备能力适配——屏幕常亮 / 震动 / 提醒音 / 网络类型 / 调试态判断。
 * 约定：全部吞掉宿主异常（设备能力失败绝不阻断烹饪主流程），
 * 提醒音资源缺失（onError）静默——烹饪页用震动 + 视觉提示兜底。
 */

/**
 * 设置屏幕常亮（烹饪引导页进入时开启、离开时关闭）。
 * @param on true 常亮 / false 恢复跟随系统
 * @returns 无
 * @throws 不抛出（宿主失败静默）
 */
export function setKeepScreenOn(on: boolean): void {
  try {
    uni.setKeepScreenOn({
      keepScreenOn: on,
      fail: () => {
        // 设置失败静默：仅影响省电体验
      },
    })
  } catch {
    // 平台不支持：静默
  }
}

/**
 * 长震动提醒（计时结束 / 关键步骤提示用）。
 * @returns 无
 * @throws 不抛出（设备不支持震动时静默）
 */
export function vibrate(): void {
  try {
    uni.vibrateLong({
      fail: () => {
        // 震动失败静默
      },
    })
  } catch {
    // 平台不支持：静默
  }
}

/**
 * 播放提醒音（计时结束主提醒；资源缺失/播放失败静默）。
 * 音频资源 src 为占位 '/static/alert.mp4'，待资源就位后替换（无需改调用方）。
 * @returns 无
 * @throws 不抛出（onError 静默；创建上下文异常静默）
 */
export function playAlertSound(): void {
  try {
    const audio = uni.createInnerAudioContext()
    // 占位资源：可替换为实际提醒音文件（放 src/static/ 下）
    audio.src = '/static/alert.mp4'
    audio.onError(() => {
      // 资源缺失 / 解码失败 / 播放失败：静默，震动与视觉提示兜底
    })
    audio.play()
  } catch {
    // 平台不支持：静默
  }
}

/**
 * 获取当前网络类型（Promise 化 uni.getNetworkType）。
 * @returns 网络类型（'wifi' | '2g' | '3g' | '4g' | '5g' | 'unknown' | 'none' 等）；
 *          获取失败返回 'unknown'
 * @throws 不抛出
 */
export function getNetworkType(): Promise<string> {
  return new Promise<string>((resolve) => {
    try {
      uni.getNetworkType({
        success: (res) => resolve(res.networkType),
        fail: () => resolve('unknown'),
      })
    } catch {
      resolve('unknown')
    }
  })
}

/**
 * 是否调试环境（vite development 模式）。
 * @returns 开发模式返回 true
 * @throws 不抛出
 */
export function isDebugEnv(): boolean {
  try {
    return import.meta.env.MODE === 'development'
  } catch {
    return false
  }
}
