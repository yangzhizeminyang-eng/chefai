/**
 * 文件职责：订阅消息（计时器提醒）平台适配——uni.requestSubscribeMessage 封装。
 * PRD-Q-6 口径：本地提醒（页面倒计时 + 常亮 + 震动）为主路径，订阅消息仅为切后台辅助，
 * 因此拒绝 / 失败 / 模板未配置一律静默返回 false，绝不阻断烹饪流程、绝不打扰用户。
 * 模板 ID 常量 TIMER_TEMPLATE_ID 当前为占位空串：待微信公众平台申请「计时提醒」类目
 * 订阅模板后填入；为空时本函数直接返回 false（不发无效请求）。
 */

/** 订阅消息模板 ID（占位：待平台申请后填入，如 'ABCdef123...'） */
export const TIMER_TEMPLATE_ID = ''

/**
 * 请求计时器订阅消息授权。
 * @returns 用户在本次弹窗中同意返回 true；拒绝 / 失败 / 模板未配置返回 false
 * @throws 不抛出（订阅失败静默，不阻断主流程——本地提醒为主路径）
 */
export function requestTimerSubscribe(): Promise<boolean> {
  // 模板未申请/未配置：直接跳过，不发无效请求
  if (!TIMER_TEMPLATE_ID) return Promise.resolve(false)
  return new Promise<boolean>((resolve) => {
    try {
      uni.requestSubscribeMessage({
        tmplIds: [TIMER_TEMPLATE_ID],
        success: (res) => {
          // res 形如 { [tmplId]: 'accept' | 'reject' | 'ban' | 'filter', errMsg }；经 unknown 断言取模板键
          const state = (res as unknown as Record<string, unknown>)[TIMER_TEMPLATE_ID]
          resolve(state === 'accept')
        },
        fail: () => resolve(false),
      })
    } catch {
      resolve(false)
    }
  })
}
