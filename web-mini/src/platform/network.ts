/**
 * 文件级注释：全局网络状态模块——模块级 reactive 单例，供各页面 useAppNetwork() 消费。
 * 说明：原实现位于 App.vue（普通 script 块导出），因 App.vue 被页面 import 会在 Vite
 * 构建时被拆为共享 chunk，产生组件级副产物 App.json，在 Windows 大小写不敏感文件系统上
 * 与应用入口 app.json 冲突导致产物损坏（报错 "The emitted file App.json overwrites a
 * previously emitted file of the same name"）。故抽出为独立模块，App.vue 恢复纯应用入口
 * （零具名导出），初始化由 App.vue onLaunch 调用 initNetworkWatch()。
 */
import { reactive } from 'vue'

/** 全局网络状态对象：networkType 当前网络类型，isConnected 是否联网 */
const networkState = reactive<{ networkType: string; isConnected: boolean }>({
  networkType: 'unknown',
  isConnected: true
})

/**
 * 获取全局网络状态的视图
 * @returns 全局网络状态 reactive 对象（networkType / isConnected）
 */
export function useAppNetwork() {
  return networkState
}

/**
 * 初始化网络探测与监听（应用启动时调用一次：App.vue onLaunch）。
 * 先探测当前网络类型写入初始态，再注册系统级网络状态变化监听。
 * @returns 无
 * @throws 不抛出（uni API 失败由平台回调吞掉，保持默认态）
 */
export function initNetworkWatch(): void {
  uni.getNetworkType({
    /** 网络类型探测成功回调 */
    success: (res) => {
      networkState.networkType = res.networkType
      networkState.isConnected = res.networkType !== 'none'
    }
  })
  uni.onNetworkStatusChange((res) => {
    networkState.isConnected = res.isConnected
    networkState.networkType = res.networkType
  })
}
