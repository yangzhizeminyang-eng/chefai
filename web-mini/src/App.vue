<!--
  文件级注释：应用壳组件——声明应用生命周期，负责：
  1) 应用启动时调用 initNetworkWatch()（网络态探测与监听，状态模块见 platform/network.ts）；
  2) 全局错误捕获（onError / uni.onUnhandledRejection）；
  3) 引入全局样式（tokens + global）。
  🔴 红线：应用入口文件不得有任何具名导出——页面 import App.vue 会使其被 Vite 拆为共享
  chunk，产生组件级副产物 App.json，在 Windows 大小写不敏感文件系统上覆盖应用入口
  app.json，导致产物损坏（历史缺陷，勿回退）。
  结构说明：仅保留 <script setup> 承载 onLaunch / onError 生命周期。
-->
<script setup lang="ts">
/**
 * 启动接入说明（Task 6）：
 * - onLaunch 顺序：网络探测 → P-00 免责门（未同意 reLaunch 免责页）→
 *   session.ensureAnonymousId() →（并行）config.load() + home.load() → trackEvent('app_enter')；
 * - onShow（应用级）：config.refreshOnShow() 前台恢复刷新开关（文档 §10.3）；
 * - onError / onUnhandledRejection：经 postTrackEvents 直接上报 app_error 运维事件
 *   （app_error 不属于 PRD 38 业务事件清单，不走 trackEvent 缓冲，失败静默）。
 */
import { onLaunch, onShow, onError } from '@dcloudio/uni-app'
import { useSessionStore } from '@/stores/session'
import { useConfigStore } from '@/stores/config'
import { useHomeStore } from '@/stores/home'
import { trackEvent } from '@/utils/track'
import { ROUTES } from '@/utils/routes'
import { postTrackEvents } from '@/api/endpoints'
import { generateRequestId } from '@/api/request'
import { initNetworkWatch } from '@/platform/network'

/** app_error 运维事件 message 截断长度（防止异常堆栈撑爆上报体） */
const ERROR_MESSAGE_MAX = 200

/**
 * 取当前页面栈末页的 route（app_error 归因用；无页面栈时兜底空串）。
 * @returns 末页 route 字符串（如 'pages/index/index'；取不到返回 ''）
 * @throws 不抛出（页面栈不可用时静默兜底）
 */
function lastPageRoute(): string {
  try {
    const pages = getCurrentPages()
    const last = pages[pages.length - 1]
    return last?.route ?? ''
  } catch {
    return ''
  }
}

/**
 * 上报 app_error 运维事件（不走 trackEvent 业务缓冲，直接单条 postTrackEvents；
 * app_error 为运维事件，不属于 PRD 38 业务事件清单；任何失败静默）。
 * @param message 错误文本（onError 为拼接串 / onUnhandledRejection 为 reason 文本，截断 200 字）
 * @returns 无
 * @throws 不抛出（上报失败静默——错误上报绝不引发二次错误）
 */
function reportAppError(message: string): void {
  const payload = [{
    name: 'app_error',
    props: {
      page: lastPageRoute(),
      message: String(message).slice(0, ERROR_MESSAGE_MAX),
    },
    ts: Date.now(),
    request_id: generateRequestId(),
  }]
  try {
    postTrackEvents(payload).catch(() => {
      // 上报失败静默（接口本期未实现 / 网络异常均不阻断）
    })
  } catch {
    // 同步异常静默
  }
}

onLaunch(() => {
  // 初始网络态探测与监听（platform/network.ts，保持原行为）
  initNetworkWatch()

  // P-00 免责门：未同意免责声明则整窗替换到免责页（同意后回首页）
  const sessionStore = useSessionStore()
  if (!sessionStore.disclaimerAgreed) {
    uni.reLaunch({ url: ROUTES.DISCLAIMER, fail: () => {} })
  }

  // 启动链路：匿名 ID 先行 →（并行）开关预取 + 首页聚合预取 → 埋点 app_enter
  void sessionStore.ensureAnonymousId().then(() => {
    return Promise.all([
      useConfigStore().load(),
      useHomeStore().load(),
    ])
  }).finally(() => {
    trackEvent('app_enter')
  })
})

onShow(() => {
  // 应用级前台恢复：刷新远程开关（文档 §10.3，TTL 内为无操作）
  void useConfigStore().refreshOnShow()
})

onError((err) => {
  // 全局错误上报（app_error 运维事件，失败静默）
  reportAppError(err)
})

uni.onUnhandledRejection(({ reason }) => {
  // 未处理 Promise 拒绝上报（app_error 运维事件，失败静默；reason 平台类型不定，防御式取 message/stack）
  const detail = reason as { message?: unknown; stack?: unknown } | null | undefined
  reportAppError(
    detail?.message !== undefined
      ? `${String(detail.message)}\n${detail.stack ? String(detail.stack) : ''}`
      : String(reason),
  )
})
</script>

<style lang="scss">
/* 全局样式：设计 token 与通用类（App.vue 的 style 天然全局生效，勿加 scoped） */
@import './styles/global.scss';
</style>
