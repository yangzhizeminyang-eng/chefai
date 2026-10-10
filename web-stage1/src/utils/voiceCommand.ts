/**
 * 文件职责：免手语音指令（PRD US-F4 分步引导免手语音；架构 §8.2 指令白名单本地解析，不走模型）。
 * - createVoiceCommandController：Web Speech API（SpeechRecognition / webkitSpeechRecognition）
 *   封装，continuous 持续监听 + onend 自动续听，识别结果经白名单解析后回调 onCommand；
 * - parseVoiceCommand：指令白名单本地解析纯函数（vitest 可测），中英文键均不区分大小写；
 * - 识别错误（no-speech / not-allowed 等）经 onError 回调上交宿主，本模块不抛出。
 */

/** 语音指令枚举（与烹饪引导既有动作一一对应） */
export type VoiceCommand =
  /** 下一步（含近义：下一 / 继续做 / 接下来） */
  | 'next'
  /** 上一步（含近义：上一 / 退回） */
  | 'prev'
  /** 暂停计时（含近义：暂停计时 / 停一下） */
  | 'timer_pause'
  /** 继续计时（含近义：继续计时 / 恢复） */
  | 'timer_resume'

/** 识别错误对象（经 onError 回调上交，宿主决定提示策略） */
export interface VoiceCommandError {
  /** 原生错误码（no-speech / not-allowed / audio-capture / network ...） */
  code: string
  /** 面向展示的中文错误说明 */
  message: string
}

/** 控制器创建入参 */
export interface VoiceCommandControllerOptions {
  /** 白名单指令命中后的回调（宿主映射到既有动作函数） */
  onCommand: (command: VoiceCommand) => void
  /** 识别出错回调（可缺省；no-speech 等高频噪音也走此通道，不抛出） */
  onError?: (error: VoiceCommandError) => void
}

/** 语音控制器（宿主仅接触 start/stop/supported 三个成员） */
export interface VoiceCommandController {
  /** 开始监听（不支持或已在监听时调用为幂等空操作） */
  start: () => void
  /** 停止监听（手动关闭 / 页面卸载时调用） */
  stop: () => void
  /** 当前浏览器是否支持 Web Speech API（不支持时 start 为空操作） */
  readonly supported: boolean
}

/* ── Web Speech API 最小类型视图（lib.dom 未内置，运行时特性检测，风格同 WakeLock 用法） ── */

/** 单条识别候选 */
interface SpeechRecognitionAlternativeLike {
  /** 识别文本 */
  transcript: string
  /** 是否最终结果（非中间临时结果） */
  isFinal: boolean
}

/** 一段识别结果（含多个候选） */
interface SpeechRecognitionResultLike {
  length: number
  [index: number]: SpeechRecognitionAlternativeLike | undefined
}

/** 结果列表（事件中可能包含多段） */
interface SpeechRecognitionResultListLike {
  length: number
  [index: number]: SpeechRecognitionResultLike | undefined
}

/** 识别结果事件（仅声明用到的成员） */
interface SpeechRecognitionEventLike {
  /** 本轮事件起始结果下标 */
  resultIndex: number
  /** 结果列表 */
  results: SpeechRecognitionResultListLike
}

/** 识别错误事件（仅声明用到的成员） */
interface SpeechRecognitionErrorEventLike {
  /** 原生错误码 */
  error: string
}

/** 识别实例最小接口视图 */
interface SpeechRecognitionLike {
  lang: string
  continuous: boolean
  interimResults: boolean
  start: () => void
  stop: () => void
  abort: () => void
  onresult: ((event: SpeechRecognitionEventLike) => void) | null
  onerror: ((event: SpeechRecognitionErrorEventLike) => void) | null
  onend: (() => void) | null
}

/** 识别构造器最小类型视图 */
type SpeechRecognitionCtor = new () => SpeechRecognitionLike

/** 挂载识别构造器的 window 类型视图 */
type WindowWithSpeech = Window & {
  SpeechRecognition?: SpeechRecognitionCtor
  webkitSpeechRecognition?: SpeechRecognitionCtor
}

/* ── 指令白名单（本地规则表，顺序即优先级） ── */

/**
 * 白名单规则表：按数组顺序首条命中即返回。
 * 顺序约定 —— next 必须先于 timer_resume：「继续做」包含「继续」，
 * 若 resume 先匹配会把「继续做」误判为暂停恢复。
 */
const COMMAND_RULES: ReadonlyArray<{ command: VoiceCommand; keywords: readonly string[] }> = [
  { command: 'next', keywords: ['下一步', '下一', '继续做', '接下来', 'next'] },
  { command: 'prev', keywords: ['上一步', '上一', '退回', 'previous', 'back'] },
  { command: 'timer_pause', keywords: ['暂停', '停一下', 'pause'] },
  { command: 'timer_resume', keywords: ['继续', '恢复', 'resume'] },
]

/** 错误码 → 中文说明（onError 上交用，宿主可直接展示） */
const ERROR_MESSAGES: Readonly<Record<string, string>> = {
  'no-speech': '没有听清指令，请再说一次',
  'not-allowed': '麦克风权限被拒绝，请在浏览器地址栏允许麦克风后重试',
  'service-not-allowed': '语音服务不可用，请检查浏览器权限设置',
  'audio-capture': '未检测到麦克风设备',
  network: '语音识别服务网络异常',
  aborted: '语音识别已中止',
}

/**
 * 指令白名单本地解析（纯函数，架构 §8.2：不走模型）。
 * 归一化：去首尾空白 + 小写（中文不受影响，英文键大小写不敏感）；
 * 匹配：识别文本常带句尾标点/前缀，按「包含关键词」命中，规则表顺序即优先级。
 *
 * @param text 识别出的原始文本（如「下一步。」「厨娘继续做」）
 * @returns 命中的指令；无命中 / 空文本返回 null
 * @throws 不抛出（纯字符串运算）
 */
export function parseVoiceCommand(text: string): VoiceCommand | null {
  const normalized = text.trim().toLowerCase()
  if (!normalized) return null
  for (const rule of COMMAND_RULES) {
    for (const keyword of rule.keywords) {
      if (normalized.includes(keyword)) return rule.command
    }
  }
  return null
}

/**
 * 创建免手语音指令控制器（Web Speech API 封装）。
 * 行为要点：
 *     ① supported = 特性检测 window.SpeechRecognition / webkitSpeechRecognition，不支持时
 *        start/stop 均为空操作，宿主据 supported=false 给一次性提示；
 *     ② continuous 持续监听 + onend 自动续听（浏览器静音超时会自动 end，重启维持免手体验）；
 *        权限类错误（not-allowed）不再续听；
 *     ③ 仅处理最终结果（interimResults=false），解析命中白名单才回调 onCommand；
 *     ④ 所有异常（构造/启动/回调）内部消化，经 onError 上交，不向宿主抛出。
 *
 * @param options onCommand 必填、onError 可缺省
 * @returns { start, stop, supported } 控制器
 * @throws 不抛出（识别过程中的错误全部经 onError 回调上交）
 */
export function createVoiceCommandController(
  options: VoiceCommandControllerOptions,
): VoiceCommandController {
  const { onCommand, onError } = options

  /* 特性检测：node/SSR（无 window）与老浏览器均归为不支持 */
  let ctor: SpeechRecognitionCtor | null = null
  let supported = false
  try {
    if (typeof window !== 'undefined') {
      const win = window as WindowWithSpeech
      ctor = win.SpeechRecognition ?? win.webkitSpeechRecognition ?? null
      supported = ctor !== null
    }
  } catch {
    supported = false
  }

  /** 当前识别实例（null = 未监听） */
  let recognition: SpeechRecognitionLike | null = null
  /** 是否处于监听会话中（onend 自动续听的判断依据） */
  let listening = false
  /** 手动停止标记（stop 后 onend 不再自动续听） */
  let manualStopped = false

  /**
   * 上交识别错误（含中文说明），不抛出。
   * @param code 原生错误码
   * @returns 无
   */
  function emitError(code: string): void {
    onError?.({ code, message: ERROR_MESSAGES[code] ?? '语音识别出错' })
  }

  /**
   * 识别结果处理：取事件窗口内的最终结果 → 白名单解析 → 命中回调 onCommand。
   * @param event 识别结果事件
   * @returns 无
   */
  function handleResult(event: SpeechRecognitionEventLike): void {
    for (let i = event.resultIndex; i < event.results.length; i++) {
      const result = event.results[i]
      if (!result) continue
      const item = result[0]
      if (!item || !item.isFinal) continue
      const command = parseVoiceCommand(item.transcript)
      if (command) onCommand(command)
    }
  }

  /**
   * 创建识别实例并启动监听（构造/启动失败静默降级，不抛出）。
   * @returns 无
   */
  function startRecognition(): void {
    if (!ctor) return
    try {
      const instance = new ctor()
      instance.lang = 'zh-CN'
      instance.continuous = true
      instance.interimResults = false
      instance.onresult = handleResult
      instance.onerror = (event: SpeechRecognitionErrorEventLike) => {
        const code = event?.error || 'unknown'
        // 权限被拒：终止监听会话（onend 不再续听），交由宿主提示
        if (code === 'not-allowed' || code === 'service-not-allowed') {
          listening = false
        }
        emitError(code)
      }
      instance.onend = () => {
        // 浏览器静音超时等会自动 end：非手动停止则续听，维持免手体验
        if (listening && !manualStopped) {
          try {
            instance.start()
          } catch {
            // 续听失败（如实例仍处活动态）：等待下一次 onend 再试
          }
        }
      }
      instance.start()
      recognition = instance
      listening = true
    } catch {
      // 启动失败（麦克风被占用等）：静默降级，宿主开关仍可手动关闭重试
      recognition = null
      listening = false
    }
  }

  return {
    /**
     * 开始监听（不支持或已在监听时为幂等空操作）。
     * @returns 无
     * @throws 不抛出
     */
    start(): void {
      if (!supported || listening) return
      manualStopped = false
      startRecognition()
    },
    /**
     * 停止监听（手动关闭 / 页面卸载时调用；幂等）。
     * @returns 无
     * @throws 不抛出
     */
    stop(): void {
      manualStopped = true
      listening = false
      try {
        recognition?.stop()
      } catch {
        // 停止失败无需处理
      }
      recognition = null
    },
    get supported(): boolean {
      return supported
    },
  }
}
