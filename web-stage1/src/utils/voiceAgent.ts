/**
 * 文件职责：全局语音智能体（模块级单例，任意页面可用）。
 * - 唤醒词：转写含「厨娘」→ 唤醒 10s 并 TTS 回应「我在！」，余句直接当指令；
 * - 指令路由：烹饪页处理器（CookGuideView 注册，免唤醒全量接管）→
 *   全局导航白名单（今天吃什么/时令吃什么/打开首页…）→ LLM 意图兜底
 *   （导航动作 + 当前路由上下文）；
 * - 生命周期：顶部「语音助手」开关控制麦克风常开；未注册页面处理器的页面
 *   需先唤醒才接受指令（防环境误触发）。
 */

import { ref } from 'vue'
import router from '@/router'
import { ElMessage } from 'element-plus'
import { postSpeechAsr, postVoiceIntent } from '@/api/endpoints'
import { createAsrVoiceController, type AsrVoiceController } from './asrVoiceCommand'

/** 语音助手开关状态（AppHeader 按钮与烹饪页语音按钮共享；不持久化——每次进站手动开启，避免首屏就索要麦克风权限） */
export const voiceAgentEnabled = ref(false)
/** 唤醒态（唤醒窗口内无需再说唤醒词） */
export const voiceAgentAwake = ref(false)

/** 唤醒词（转写含该词即唤醒；「嗨厨娘」「厨娘厨娘」均命中） */
const WAKE_KEYWORD = '厨娘'
/** 唤醒窗口（毫秒）：唤醒后这段时间内的话都当指令 */
const WAKE_WINDOW_MS = 10000

/** 烹饪页处理器（CookGuideView 挂载期注册：白名单→动作 / LLM 意图兜底） */
type PageHandler = (text: string) => Promise<void> | void
let pageHandler: PageHandler | null = null

/** 语音控制器（懒创建，开关切换复用同一实例与麦克风流） */
let controller: AsrVoiceController | null = null
/** 唤醒窗口截止时间戳 */
let awakeUntil = 0
/** 回应/朗读音频（新回应打断上一段） */
let replyAudio: HTMLAudioElement | null = null
/** 唤醒回应「我在！」预合成缓存（开启助手时预取，唤醒秒回） */
let wakeReplyBlob: Blob | null = null
/** 系统正在播放语音（朗读/回应）：期间丢弃一切语音输入，防外放回采误触发 */
let speaking = false
/** 播放结束时间戳（留缓冲排空在途片段） */
let lastSpeakEnd = 0
/** 播放结束后的输入静默缓冲（毫秒） */
const PLAYBACK_GRACE_MS = 600

/** 全局导航白名单（高频口令免 LLM；仅无页面处理器时消费） */
const GLOBAL_NAV: ReadonlyArray<{ keywords: readonly string[]; path: string }> = [
  { keywords: ['今天吃什么'], path: '/today' },
  { keywords: ['时令吃什么'], path: '/seasonal' },
  { keywords: ['选择食材'], path: '/select' },
  { keywords: ['推荐结果'], path: '/recommend' },
  { keywords: ['家庭档案'], path: '/profile' },
  { keywords: ['我的冰箱'], path: '/inventory' },
  { keywords: ['调度面板'], path: '/trace' },
  { keywords: ['打开首页', '回到首页', '回首页', '返回首页'], path: '/' },
]

/** LLM 导航动作 → 路由（意图解析产物映射） */
const ACTION_ROUTES: Readonly<Record<string, string>> = {
  nav_home: '/',
  nav_select: '/select',
  nav_recommend: '/recommend',
  nav_today: '/today',
  nav_seasonal: '/seasonal',
  nav_recognize: '/recognize',
  nav_profile: '/profile',
  nav_inventory: '/inventory',
  nav_innovate: '/innovate',
  nav_me: '/me',
  nav_trace: '/trace',
}

/**
 * 注册/注销当前页面的语音处理器（函数）。
 * 页面挂载期注册（如烹饪引导页），卸载期传 null 注销；注册期间该页转写
 * 全量交给处理器（烹饪页免唤醒，保持既有免手体验）。
 * @param handler 处理器或 null
 * @returns 无
 */
export function setVoicePageHandler(handler: PageHandler | null): void {
  pageHandler = handler
}

/**
 * 向当前页面处理器转发一条文本指令（函数）。
 * @param text 指令文本（页面按自身白名单解析执行）
 * @returns 是否存在页面处理器（false = 当前页面无落点）
 */
export function dispatchToPage(text: string): boolean {
  if (!pageHandler) return false
  void pageHandler(text)
  return true
}

/**
 * 切换语音助手开关（函数）。
 * @returns 无
 */
export function toggleVoiceAgent(): void {
  if (voiceAgentEnabled.value) disableVoiceAgent()
  else enableVoiceAgent()
}

/**
 * 开启语音助手：请求麦克风并持续监听（函数）。
 * @returns 无
 */
export function enableVoiceAgent(): void {
  if (voiceAgentEnabled.value) return
  if (!controller) {
    controller = createAsrVoiceController({
      transcribe: (wav) => postSpeechAsr(wav).then((r) => (r.degraded ? '' : r.text)),
      shouldListen: playbackGate,
      onTranscript: (text) => {
        void handleTranscript(text)
      },
      onError: (e) => {
        if (e.code === 'not-allowed' || e.code === 'service-not-allowed') {
          disableVoiceAgent()
        }
        ElMessage.warning(`语音助手：${e.message}`)
      },
    })
  }
  controller.start()
  voiceAgentEnabled.value = true
  // 预合成唤醒回应（fire-and-forget）：固定话术提前拿到音频，唤醒时秒回
  if (!wakeReplyBlob) {
    void fetch('/v1/speech/tts/stream?text=' + encodeURIComponent('我在！'))
      .then((res) => (res.ok ? res.blob() : null))
      .then((blob) => {
        if (blob) wakeReplyBlob = blob
      })
      .catch(() => {})
  }
}

/**
 * 关闭语音助手：释放麦克风并退出唤醒态（函数）。
 * @returns 无
 */
export function disableVoiceAgent(): void {
  voiceAgentEnabled.value = false
  voiceAgentAwake.value = false
  awakeUntil = 0
  setVoicePlayback(false)
  replyAudio?.pause()
  replyAudio = null
  try {
    controller?.stop()
  } catch {
    // 释放失败无需处理
  }
}

/**
 * 标记系统语音播放状态（导出，页面朗读接线用，函数）。
 * 播放期间 handleTranscript 丢弃一切语音输入（含唤醒词），
 * 结束后留 PLAYBACK_GRACE_MS 缓冲排空在途片段再恢复接收。
 * @param active true = 开始播放；false = 播放结束
 * @returns 无
 */
export function setVoicePlayback(active: boolean): void {
  if (active) {
    speaking = true
    return
  }
  speaking = false
  lastSpeakEnd = Date.now()
}

/**
 * 系统是否正在播放语音或处于播放后缓冲期（内部函数）。
 * @returns true = 应丢弃语音输入
 */
function isPlaybackBusy(): boolean {
  return speaking || Date.now() - lastSpeakEnd < PLAYBACK_GRACE_MS
}

/**
 * 采集门控（内部函数）：供语音控制器每帧查询，播报期间直接暂停采集。
 * @returns true = 允许采集
 */
function playbackGate(): boolean {
  return !isPlaybackBusy()
}

/**
 * 转写总路由（内部函数）：播放静默 → 唤醒词 → 页面处理器 → 唤醒窗口指令。
 * @param text 最终转写文本
 * @returns 无
 */
async function handleTranscript(text: string): Promise<void> {
  // 系统复述期间（含结束缓冲期）不接收任何语音：防外放回采与同时说话叠加
  if (isPlaybackBusy()) return
  const t = text.trim()
  if (!t) return
  // ① 唤醒词：任意页面生效；唤醒词后的余句立即当指令
  if (t.includes(WAKE_KEYWORD)) {
    const remainder = t.slice(t.lastIndexOf(WAKE_KEYWORD) + WAKE_KEYWORD.length).trim()
    if (Date.now() >= awakeUntil) {
      awakeUntil = Date.now() + WAKE_WINDOW_MS
      voiceAgentAwake.value = true
      speakReply('我在！')
    } else {
      awakeUntil = Date.now() + WAKE_WINDOW_MS
    }
    if (remainder) {
      // 有页面处理器（如烹饪页）时余句交页面执行（白名单/计时参数解析都在页面层）
      if (pageHandler) await pageHandler(remainder)
      else await handleCommand(remainder)
    }
    return
  }
  // ② 烹饪页处理器：注册期间全量接管（免唤醒，保持引导页既有体验）
  if (pageHandler) {
    await pageHandler(t)
    return
  }
  // ③ 其他页面：需处于唤醒窗口（防环境对话误触发）
  if (Date.now() >= awakeUntil) return
  awakeUntil = Date.now() + WAKE_WINDOW_MS
  await handleCommand(t)
}

/**
 * 指令执行（内部函数）：全局导航白名单优先，未命中走 LLM 意图兜底。
 * @param text 指令文本
 * @returns 无
 */
async function handleCommand(text: string): Promise<void> {
  for (const nav of GLOBAL_NAV) {
    if (nav.keywords.some((k) => text.includes(k))) {
      await router.push(nav.path).catch(() => {})
      return
    }
  }
  await globalIntentFallback(text)
}

/**
 * LLM 意图兜底（导出，供注册页面的本地解析未命中时复用）：
 * 转写 + 当前路由上下文交主 LLM 解析；导航动作直接跳转，none 时朗读 reply。
 * @param text 指令文本
 * @returns 无
 */
export async function globalIntentFallback(text: string): Promise<void> {
  let intent
  try {
    intent = await postVoiceIntent(text, {
      current_route: router.currentRoute.value.fullPath,
      scene: 'global_navigation',
    })
  } catch {
    return
  }
  if (intent.degraded || intent.action === 'none') {
    if (intent.reply) speakReply(intent.reply)
    return
  }
  // 页面级动作转发回注册页执行（页内白名单按合成文本解析）
  if (intent.action === 'pick_recipe' && intent.step_no != null) {
    if (!dispatchToPage(`第${intent.step_no}个`)) speakReply('当前页面没有可以选的菜')
    return
  }
  if (intent.action === 'start_cooking') {
    if (!dispatchToPage('开始做菜')) speakReply('请先打开一个菜谱')
    return
  }
  const path = ACTION_ROUTES[intent.action]
  if (path) {
    await router.push(path).catch(() => {})
    return
  }
  // 非导航类动作在无页面处理器的页面无落点：若有回应话术则朗读
  if (intent.reply) speakReply(intent.reply)
}

/**
 * TTS 朗读一句回应（内部函数）：走后端流式端点，新回应打断上一段。
 * @param text 回应文本
 * @returns 无
 */
function speakReply(text: string): void {
  replyAudio?.pause()
  replyAudio = null
  let src: string
  if (text === '我在！' && wakeReplyBlob) {
    src = URL.createObjectURL(wakeReplyBlob)
  } else {
    src = `/v1/speech/tts/stream?text=${encodeURIComponent(text)}`
  }
  const el = new Audio(src)
  replyAudio = el
  setVoicePlayback(true)
  el.addEventListener('ended', () => setVoicePlayback(false))
  el.addEventListener('error', () => setVoicePlayback(false))
  el.play().catch(() => {
    // 自动播放被拦截：静默跳过
    setVoicePlayback(false)
    replyAudio = null
  })
}
