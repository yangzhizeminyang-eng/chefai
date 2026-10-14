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
  /** 打开计时器（含近义：计时 / 倒计时；可携带「N 分钟」直接启动） */
  | 'timer_open'
  /** 停止计时（含近义：取消计时 / 停止；清掉全部计时而非暂停） */
  | 'timer_stop'
  /** 跳转到第 N 步（口令形如「去第 3 步」「第 5 步」） */
  | 'step_jump'
  /** 预设计时（含近义：焯水 / 煎 / 炖 / 焖 / 蒸，按常用烹饪时长直接起计时） */
  | 'timer_preset'
  /** 完成做菜（含近义：做完了 / 做好了；仅最后一步生效，防误结束） */
  | 'finish'
  /** 朗读/重播当前步骤内容（含近义：再说一遍 / 这一步是什么） */
  | 'repeat'
  /** 关闭当前弹层（计时器抽屉 / 求助弹窗 / 步骤列表） */
  | 'close'
  /** 暂停计时（含近义：暂停计时 / 停一下） */
  | 'timer_pause'
  /** 继续计时（含近义：继续计时 / 恢复） */
  | 'timer_resume'
  /** 打开求助弹窗（含近义：帮助 / 帮忙） */
  | 'help'

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
 * 若 resume 先匹配会把「继续做」误判为暂停恢复；
 * pause / resume / stop 必须先于 timer_open：「暂停计时」「继续计时」「停止计时」
 * 都含「计时」，若 timer_open 先匹配会误判为打开计时器；
 * step_jump 在 timer_open 之后：「第一次计时」应优先归计时而非跳步骤。
 */
const COMMAND_RULES: ReadonlyArray<{ command: VoiceCommand; keywords: readonly string[] }> = [
  { command: 'next', keywords: ['下一步', '下一', '继续做', '接下来', 'next'] },
  { command: 'prev', keywords: ['上一步', '上一', '退回', 'previous', 'back'] },
  { command: 'timer_pause', keywords: ['暂停', '停一下', 'pause'] },
  { command: 'timer_resume', keywords: ['继续', '恢复', 'resume'] },
  { command: 'timer_stop', keywords: ['停止计时', '取消计时', '关闭计时', '关掉计时', '结束计时', '停止', '停掉'] },
  { command: 'timer_open', keywords: ['计时', '倒计时', 'timer'] },
  { command: 'step_jump', keywords: ['去第', '跳到第', '跳到', '第'] },
  { command: 'timer_preset', keywords: ['焯水', '煎', '炖', '焖', '蒸'] },
  { command: 'help', keywords: ['求助', '帮助', '帮忙', '救命', '帮我问', '问一下', 'help'] },
  { command: 'repeat', keywords: ['再说一遍', '再念一遍', '念一下', '读一下', '这步是什么', '这一步是什么', '重读', '重复'] },
  { command: 'finish', keywords: ['做完了', '做好了', '完成做菜'] },
  { command: 'close', keywords: ['关闭', '关掉', '收起'] },
]

/** 中文数字 → 阿拉伯数字（计时/步骤口令解析用，覆盖家常常用数） */
const CN_DIGITS: Readonly<Record<string, number>> = {
  一: 1,
  二: 2,
  两: 2,
  三: 3,
  四: 4,
  五: 5,
  六: 6,
  七: 7,
  八: 8,
  九: 9,
  十: 10,
}

/**
 * 中文数字 token 转整数（内部纯函数）：支持 十 / 十五 / 二十 / 二十五 等组合。
 * @param token 中文数字串（如「十」「三」「二十五」）
 * @returns 对应整数；无法解析返回 null
 */
function parseCnInt(token: string): number | null {
  if (token === '十') return 10
  if (token.startsWith('十')) return token.length > 1 ? 10 + (CN_DIGITS[token.slice(1)] ?? 0) : 10
  if (token.includes('十')) {
    const [tens = '', ones] = token.split('十')
    const value = (CN_DIGITS[tens] ?? 0) * 10 + (ones ? (CN_DIGITS[ones] ?? 0) : 0)
    return value > 0 ? value : null
  }
  return CN_DIGITS[token] ?? null
}

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

/** 计时分钟数提取正则：阿拉伯数字（ASR 开启 ITN 后「三」→「3」） */
const ARABIC_MINUTES_RE = /(\d{1,3})\s*分钟?/
/**
 * 计时分钟数提取正则：中文数字串（捕获完整 token 后交 parseCnInt 解析，
 * 覆盖 十五 / 四十 / 九十 / 二十五 等全部组合——旧版逐支枚举到「三十」，
 * 「四十分钟」只匹配到「十」导致 40 被算成 10）。
 */
const CN_MINUTES_RE = /([一二两三四五六七八九十]{1,3})\s*分钟?/

/**
 * 从转写文本中提取计时分钟数（纯函数，timer_open 配套）。
 * 归一化后按「阿拉伯数字 + 分钟/分」优先，其次中文数字组合
 * （三分钟 / 十五分钟 / 二十五分钟）；超界（>180）返回 null 交由
 * 宿主走抽屉手动输入路径。
 *
 * @param text 识别出的原始文本（如「计时 5 分钟」「炖十五分钟」）
 * @returns 分钟数（1~180）；未提及分钟或超界返回 null
 * @throws 不抛出（纯字符串运算）
 */
export function parseTimerMinutes(text: string): number | null {
  const normalized = text.trim().toLowerCase()
  if (!normalized) return null
  const arabic = normalized.match(ARABIC_MINUTES_RE)
  if (arabic) {
    const minutes = Number.parseInt(arabic[1] ?? '', 10)
    return minutes >= 1 && minutes <= 180 ? minutes : null
  }
  const cn = normalized.match(CN_MINUTES_RE)
  if (cn) {
    const minutes = parseCnInt(cn[1] ?? '')
    return minutes != null && minutes >= 1 && minutes <= 180 ? minutes : null
  }
  return null
}

/** 序数选择口令正则：「第 N 个」（阿拉伯数字或中文数字，ASR ITN 多为阿拉伯） */
const ORDINAL_RE = /第\s*(\d{1,2}|[一两二三四五六七八九十]{1,3})\s*个/

/**
 * 从转写文本中提取「第 N 个」序数（纯函数，推荐列表语音点菜配套）。
 * @param text 识别出的原始文本（如「帮我打开第二个」）
 * @returns 序数（1~99）；未提及返回 null
 * @throws 不抛出（纯字符串运算）
 */
export function parseOrdinal(text: string): number | null {
  const normalized = text.trim().toLowerCase()
  if (!normalized) return null
  const m = normalized.match(ORDINAL_RE)
  if (!m) return null
  const token = m[1] ?? ''
  if (/^\d+$/.test(token)) {
    const no = Number.parseInt(token, 10)
    return no >= 1 && no <= 99 ? no : null
  }
  return parseCnInt(token)
}

/** 步骤跳转口令正则：阿拉伯数字（ASR ITN 输出形态，如「去第 3 步」） */
const ARABIC_STEP_RE = /第\s*(\d{1,2})\s*步/
/** 步骤跳转口令正则：中文数字（如「第五步」「第二十五步」） */
const CN_STEP_RE = /第\s*([一两二三四五六七八九十]{1,3})\s*步/

/**
 * 从转写文本中提取目标步骤序号（纯函数，step_jump 配套）。
 * 优先「阿拉伯数字 + 步」，其次中文数字（第五步 / 第二十五步）。
 *
 * @param text 识别出的原始文本（如「去第 3 步」「跳到第五步」）
 * @returns 步骤序号（1~99）；未提及步骤返回 null
 * @throws 不抛出（纯字符串运算）
 */
export function parseStepNumber(text: string): number | null {
  const normalized = text.trim().toLowerCase()
  if (!normalized) return null
  const arabic = normalized.match(ARABIC_STEP_RE)
  if (arabic) {
    const no = Number.parseInt(arabic[1] ?? '', 10)
    return no >= 1 && no <= 99 ? no : null
  }
  const cn = normalized.match(CN_STEP_RE)
  if (cn) return parseCnInt(cn[1] ?? '')
  return null
}

/** 时长提及检测（阿拉伯数字 / 分钟 / 秒 / 中文数字） */
const DURATION_MENTION_RE = /\d|分钟|秒|[一两二三四五六七八九十]/

/**
 * 判断转写文本是否提及了时长（纯函数，timer_open 参数缺失时区分
 * 「只说了计时」（默认 5 分钟）与「说了时长但没听清」（应追问））。
 * @param text 识别出的原始文本
 * @returns true = 提及了数字/分钟/秒/中文数字
 * @throws 不抛出（纯字符串运算）
 */
export function mentionsDuration(text: string): boolean {
  return DURATION_MENTION_RE.test(text.trim())
}

/** 求助口令前缀剥离表（长词组在前，防「帮我」先吃掉「帮我求助一下」） */
const HELP_PREFIXES: readonly string[] = [
  '帮我发送求助',
  '帮我求助一下',
  '帮我求助',
  '帮我问一下',
  '帮我问下',
  '帮我问',
  '帮忙问一下',
  '帮忙问下',
  '帮忙问',
  '帮我',
  '帮忙',
  '麻烦',
  '请问',
  '发送',
  '发一下',
  '提问',
  '求助一下',
  '求助',
  '问一下',
  '问下',
  '问',
]

/** 口令首尾要剥掉的标点/引号（含全角） */
const QUESTION_TRIM_RE = /^[\s，。！？、“”「」『』,!?]+|[\s，。！？、“”「」『』,!?]+$/g

/**
 * 从求助口令中提取问题正文（纯函数，help 指令配套）。
 * 处理链：归一化 → 循环剥离前缀口令词（帮我发送求助 / 帮我求助一下 / 请问…）
 * → 剥离首尾标点引号。剩余为空（只说了「求助」）返回 null，宿主仅开弹窗不提交。
 *
 * @param text 识别出的原始文本（如「帮我求助一下 火太大怎么办」）
 * @returns 问题正文；无有效正文返回 null
 * @throws 不抛出（纯字符串运算）
 */
export function parseHelpQuestion(text: string): string | null {
  let normalized = text.trim().toLowerCase()
  if (!normalized) return null
  let stripped = true
  while (stripped) {
    stripped = false
    for (const prefix of HELP_PREFIXES) {
      if (normalized.startsWith(prefix)) {
        normalized = normalized.slice(prefix.length).trim()
        stripped = true
        break
      }
    }
  }
  const question = normalized.replace(QUESTION_TRIM_RE, '').trim()
  return question || null
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
