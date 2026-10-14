/**
 * 文件职责：免手语音指令（云端 ASR 版，PRD US-F4）。
 * 背景：utils/voiceCommand 的 Web Speech API（Chrome SpeechRecognition）依赖
 * Google 服务，国内网络/Edge 环境不可用；本模块仅用标准媒体 API
 * （getUserMedia / AudioContext）采集麦克风，静音检测（VAD）切分语句后
 * 编码为 WAV，经宿主注入的 transcribe 回调上传后端 /v1/speech/asr
 * （百炼 qwen3-asr-flash）转写，再复用 parseVoiceCommand 白名单本地解析。
 * - createAsrVoiceController：持续监听，说一句话触发一次指令，识别在后端完成；
 * - encodeWav：Float32 PCM → 16bit 单声道 WAV（纯函数，vitest 可测）；
 * - 识别/采集错误经 onError 回调上交宿主，本模块不抛出。
 */

import { parseVoiceCommand, type VoiceCommand, type VoiceCommandError } from './voiceCommand'

/** 再导出指令与错误类型（宿主从本模块统一导入，接口与 voiceCommand 对齐） */
export type { VoiceCommand, VoiceCommandError }

/** 控制器创建入参 */
export interface AsrVoiceControllerOptions {
  /** 上传一段 WAV 并返回转写文本（宿主接 /v1/speech/asr；失败时抛异常或返回空串） */
  transcribe: (wav: Blob) => Promise<string>
  /** 白名单指令命中后的回调（宿主映射到既有动作函数；text 为原始转写，供提取计时分钟数） */
  onCommand?: (command: VoiceCommand, text?: string) => void
  /** 白名单未命中的回调（宿主走 LLM 意图解析兜底，可缺省） */
  onUnknown?: (text: string) => void
  /** 每句最终转写全量回调（宿主自行路由：白名单/唤醒词/LLM；可缺省） */
  onTranscript?: (text: string) => void
  /** 采集门控（可缺省）：返回 false 时暂停采集（系统播报期间防外放回采，且不产生 ASR 调用） */
  shouldListen?: () => boolean
  /** 采集/识别出错回调（可缺省；不抛出） */
  onError?: (error: VoiceCommandError) => void
}

/** 语音控制器（宿主仅接触 start/stop/supported 三个成员，接口与 voiceCommand 对齐） */
export interface AsrVoiceController {
  /** 开始监听（不支持或已在监听时调用为幂等空操作） */
  start: () => void
  /** 停止监听（手动关闭 / 页面卸载时调用；幂等） */
  stop: () => void
  /** 当前浏览器是否支持麦克风采集（不支持时 start 为空操作） */
  readonly supported: boolean
}

/* ── VAD 分段参数（厨房环境：略长静音切句，防炒菜噪声误切） ── */

/** 语句结束静音时长（毫秒）：低于它视为还在说一句话（唤醒响应速度与切句准确性的折中） */
const SILENCE_END_MS = 700
/** 语句最短有效时长（毫秒）：短于此的「爆发声」（锅铲/碰撞）丢弃 */
const MIN_UTTERANCE_MS = 350
/** 单条语句最长时长（毫秒）：超长强制切分上传，防止无限增长 */
const MAX_UTTERANCE_MS = 10000
/** 静音噪声底下限（RMS）：低于它不再压低门限，防绝对安静环境误触发 */
const NOISE_FLOOR_MIN = 0.006
/** 帧长（样本数，onaudioprocess 单次缓冲） */
const FRAME_SIZE = 2048

/** 错误码 → 中文说明（与 voiceCommand.ERROR_MESSAGES 同文案口径） */
const ERROR_MESSAGES: Readonly<Record<string, string>> = {
  'not-allowed': '麦克风权限被拒绝，请在浏览器地址栏允许麦克风后重试',
  'service-not-allowed': '语音服务不可用，请检查浏览器权限设置',
  'audio-capture': '未检测到麦克风设备',
  network: '语音识别服务网络异常',
}

/**
 * Float32 PCM 片段编码为 16bit 单声道 WAV Blob（纯函数）。
 * @param chunks 语音片段（多帧顺序拼接）
 * @param sampleRate 采样率（AudioContext.sampleRate，通常 44100/48000）
 * @returns WAV Blob（audio/wav，44 字节头 + 16bit PCM）
 */
export function encodeWav(chunks: Float32Array[], sampleRate: number): Blob {
  let total = 0
  for (const chunk of chunks) total += chunk.length
  const buffer = new ArrayBuffer(44 + total * 2)
  const view = new DataView(buffer)
  const writeString = (offset: number, text: string): void => {
    for (let i = 0; i < text.length; i++) view.setUint8(offset + i, text.charCodeAt(i))
  }
  writeString(0, 'RIFF')
  view.setUint32(4, 36 + total * 2, true)
  writeString(8, 'WAVE')
  writeString(12, 'fmt ')
  view.setUint32(16, 16, true)
  view.setUint16(20, 1, true) // PCM
  view.setUint16(22, 1, true) // 单声道
  view.setUint32(24, sampleRate, true)
  view.setUint32(28, sampleRate * 2, true) // 字节率 = 采样率 × 2 字节
  view.setUint16(32, 2, true) // 块对齐
  view.setUint16(34, 16, true) // 位深
  writeString(36, 'data')
  view.setUint32(40, total * 2, true)
  let offset = 44
  for (const chunk of chunks) {
    for (let i = 0; i < chunk.length; i++) {
      const s = Math.max(-1, Math.min(1, chunk[i] ?? 0))
      view.setInt16(offset, s < 0 ? s * 0x8000 : s * 0x7fff, true)
      offset += 2
    }
  }
  return new Blob([buffer], { type: 'audio/wav' })
}

/**
 * 创建免手语音指令控制器（麦克风采集 + 云端 ASR + 白名单解析）。
 * 行为要点：
 *     ① supported = 特性检测 navigator.mediaDevices.getUserMedia（非 HTTPS /
 *        老浏览器为 undefined），不支持时 start/stop 均为空操作；
 *     ② 能量 VAD：动态噪声底（静音期缓慢跟随环境声）×2.5 为触发门限，
 *        说话开始采集、静音 900ms 切句；<350ms 的爆发声丢弃；单句最长 10s 强制切分；
 *     ③ 切句后异步上传转写（不阻塞下一句采集），文本经 parseVoiceCommand
 *        白名单解析命中才回调 onCommand；
 *     ④ 所有异常（权限/采集/上传）内部消化，经 onError 上交，不向宿主抛出。
 *
 * @param options transcribe / onCommand 必填、onError 可缺省
 * @returns { start, stop, supported } 控制器
 * @throws 不抛出（错误全部经 onError 回调上交）
 */
export function createAsrVoiceController(options: AsrVoiceControllerOptions): AsrVoiceController {
  const { transcribe, onCommand, onUnknown, onTranscript, shouldListen, onError } = options

  /* 特性检测：SSR/非安全上下文（http 非本机）无 mediaDevices */
  const supported =
    typeof navigator !== 'undefined' &&
    !!navigator.mediaDevices &&
    typeof navigator.mediaDevices.getUserMedia === 'function' &&
    typeof (globalThis as { AudioContext?: unknown }).AudioContext === 'function'

  /** AudioContext（null = 未监听） */
  let audioContext: AudioContext | null = null
  /** 当前媒体流（stop 时逐轨停止，释放麦克风指示灯） */
  let stream: MediaStream | null = null
  /** 是否处于监听会话中 */
  let listening = false
  /** 手动停止标记（防 stop 后异步回调继续工作） */
  let manualStopped = false

  /**
   * 上交错误（含中文说明），不抛出。
   * @param code 错误码
   * @returns 无
   */
  function emitError(code: string): void {
    onError?.({ code, message: ERROR_MESSAGES[code] ?? '语音识别出错' })
  }

  /**
   * 上传一段语句并解析指令（异步，失败仅上交错误不影响后续采集）。
   * @param wav 语句 WAV Blob
   * @returns 无
   */
  async function handleUtterance(wav: Blob): Promise<void> {
    try {
      const text = (await transcribe(wav)).trim()
      if (!text) return
      onTranscript?.(text)
      const command = parseVoiceCommand(text)
      // 联调诊断：控制台可见每句转写与指令命中情况
      console.debug('[voice] 转写:', text, '→ 指令:', command ?? '未命中白名单，走 LLM 兜底')
      if (command) onCommand?.(command, text)
      else if (text) onUnknown?.(text)
    } catch {
      emitError('network')
    }
  }

  /**
   * 开始监听（权限拒绝/构造失败静默降级，经 onError 上交）。
   * @returns 无
   */
  function startListening(): void {
    navigator.mediaDevices
      .getUserMedia({
        audio: { echoCancellation: true, noiseSuppression: true },
      })
      .then((mediaStream) => {
        if (manualStopped) {
          mediaStream.getTracks().forEach((t) => t.stop())
          return
        }
        stream = mediaStream
        const context = new AudioContext()
        audioContext = context
        const source = context.createMediaStreamSource(mediaStream)
        // ScriptProcessor 需挂到 destination 才会回调；经零增益节点防麦克风回放啸叫
        const processor = context.createScriptProcessor(FRAME_SIZE, 1, 1)
        const mute = context.createGain()
        mute.gain.value = 0
        source.connect(processor)
        processor.connect(mute)
        mute.connect(context.destination)
        processor.onaudioprocess = createVadHandler(context.sampleRate)
      })
      .catch((err: unknown) => {
        const code = (err as { name?: string } | null)?.name ?? 'unknown'
        if (code === 'NotAllowedError' || code === 'SecurityError') {
          emitError('not-allowed')
        } else if (code === 'NotFoundError' || code === 'DevicesNotFoundError') {
          emitError('audio-capture')
        } else {
          emitError('audio-capture')
        }
        listening = false
      })
  }

  /**
   * 创建 VAD 帧处理器（闭包持有分段状态，onaudioprocess 每帧调用）。
   * @param sampleRate 采样率（WAV 头需要）
   * @returns 帧处理函数
   */
  function createVadHandler(sampleRate: number): (event: AudioProcessingEvent) => void {
    /** 动态噪声底（静音期缓慢跟随环境声，说话期冻结） */
    let noiseFloor = 0.01
    /** 语句 PCM 片段缓存 */
    let utterance: Float32Array[] = []
    /** 当前语句累计时长（毫秒） */
    let utteranceMs = 0
    /** 连续静音时长（毫秒） */
    let silenceMs = 0
    /** 上传去抖：同一条语句只提交一次 */
    let submitting = false

    return (event: AudioProcessingEvent): void => {
      if (!listening || manualStopped) return
      // 采集门控：宿主播报期间暂停采集（不缓存不上传，防外放回采误触发）
      if (shouldListen && !shouldListen()) return
      const input = event.inputBuffer.getChannelData(0)
      let sumSquares = 0
      for (let i = 0; i < input.length; i++) sumSquares += (input[i] ?? 0) * (input[i] ?? 0)
      const rms = Math.sqrt(sumSquares / input.length)
      const frameMs = (input.length / sampleRate) * 1000
      const threshold = Math.max(NOISE_FLOOR_MIN, noiseFloor * 2.5)
      const isSpeech = rms > threshold

      if (isSpeech) {
        silenceMs = 0
        utterance.push(new Float32Array(input))
        utteranceMs += frameMs
        // 超长语句强制切分上传（防炒菜持续噪声把内存吃穿）
        if (utteranceMs >= MAX_UTTERANCE_MS) {
          flush()
          return
        }
      } else {
        // 静音期噪声底缓慢跟随环境声（说话期冻结防门限漂移）
        noiseFloor = noiseFloor + (rms - noiseFloor) * 0.01
        if (utterance.length > 0) {
          silenceMs += frameMs
          if (silenceMs >= SILENCE_END_MS) flush()
        }
      }
    }

    /**
     * 结束当前语句：达到最短时长才提交，否则直接丢弃（锅铲/碰撞噪声）。
     * @returns 无
     */
    function flush(): void {
      const chunks = utterance
      const durationMs = utteranceMs
      utterance = []
      utteranceMs = 0
      silenceMs = 0
      if (durationMs < MIN_UTTERANCE_MS || submitting) return
      submitting = true
      const wav = encodeWav(chunks, sampleRate)
      handleUtterance(wav).finally(() => {
        submitting = false
      })
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
      listening = true
      startListening()
    },
    /**
     * 停止监听（手动关闭 / 页面卸载时调用；幂等，释放麦克风）。
     * @returns 无
     * @throws 不抛出
     */
    stop(): void {
      manualStopped = true
      listening = false
      try {
        stream?.getTracks().forEach((t) => t.stop())
      } catch {
        // 释放失败无需处理
      }
      stream = null
      try {
        audioContext?.close()
      } catch {
        // 关闭失败无需处理
      }
      audioContext = null
    },
    get supported(): boolean {
      return supported
    },
  }
}
