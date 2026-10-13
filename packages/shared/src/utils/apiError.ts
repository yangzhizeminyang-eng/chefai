/**
 * 文件职责：ApiError 附加信息格式化工具（当前聚焦 422 参数校验错误的 detail 解析）。
 * 修复 P0-1.3：后端 422 统一返回 { code: 'VALIDATION_ERROR', message: '请求参数不合法',
 * detail: str(exc.errors()) }（见 backend/app/main.py validation_exception_handler），
 * detail 为 pydantic 错误列表的 Python repr 字符串，形如：
 *   "[{'type': 'enum', 'loc': ('body', 'location'), 'msg': \"Input should be 'fridge', ...\", 'input': '冷藏', ...}]"
 * 前端此前仅 toast「请求参数不合法」，用户无从得知哪个字段错、该怎么改。
 * 本模块把 detail 解析为「字段中文名：原因（当前值：xxx）」串，供调用方拼进 toast。
 * 同时防御性兼容 detail 为原生错误数组（[{loc, msg, input}]）的结构。
 * 无 Vue / DOM / 网络 / store 依赖，纯函数可被 vitest 在 node 环境直接单测。
 * 从 web-stage1/src/utils/apiError.ts 向后兼容增强迁移：保留既有全部导出与行为不变，
 * 新增 fromUniFailure 工厂（把 uni.request fail 的 errMsg 归一化为 ApiError，
 * timeout → TIMEOUT/加载超时，其余 → NETWORK/网络连接不可用，文案与 web-stage1
 * api/index.ts normalizeError 既有口径一致），类型导入路径由 @/api/types 改为
 * 本包相对路径 ../types/api。供小程序端（web-mini，经 vite alias @shared 引用）与 Web 端共用。
 */
import type { ApiError } from '../types/api'

/** 后端请求体字段名 → 中文标签映射（未收录字段由 entryText 原样透出，不做臆测翻译） */
const FIELD_LABELS: Record<string, string> = {
  location: '存放位置',
  quantity_level: '数量档位',
  expire_date: '到期日',
  ingredient_id: '食材',
  quantity_note: '数量备注',
  status: '条目状态',
  session_id: '会话 ID',
  anonymous_id: '匿名会话',
  request_id: '请求标识',
}

/**
 * 校验错误单条的最小结构（loc/msg 为 pydantic 标准字段，input 可选）。
 * loc 兼容数组形式（['body', 'location']）与 repr 解析后的字符串数组。
 */
interface ValidationErrorEntry {
  /** 错误位置路径（如 ['body', 'location']，最后一级字符串为字段名） */
  loc?: unknown
  /** pydantic 原始英文消息（如 "Input should be 'fridge', ..."） */
  msg?: string
  /** 用户当前提交的非法值（可为字符串/数字等，缺失表示值本身未提供） */
  input?: unknown
}

/**
 * 剥去 Python repr / JSON 字符串字面量的外层引号并还原常见转义。
 * @param raw 原始捕获串（如 "'冷藏'" 或 "\"Input should be 'fridge', ...\""，也可能是裸值）
 * @returns 还原后的文本；裸值（非引号包裹）去除首尾空白后原样返回
 */
function unquote(raw: string): string {
  const trimmed = raw.trim()
  const first = trimmed[0]
  if (first !== "'" && first !== '"') return trimmed
  return trimmed
    .slice(1, -1)
    // 还原 repr 常见转义：\' \" \\ \n（其余 \x 序号还原为字面字符，够用即可）
    .replace(/\\(['"\\n])/g, (_, ch: string) => (ch === 'n' ? '\n' : ch))
}

/**
 * 从 loc/msg 所在的 repr 片段（tuple/数组字面量）提取全部字符串元素。
 * @param raw 形如 "('body', 'location')" 或 "['body', 'location']" 的捕获串
 * @returns 字符串元素列表（数字层级自动忽略）
 */
function quotedList(raw: string): string[] {
  const out: string[] = []
  for (const m of raw.matchAll(/'([^']*)'|"([^"]*)"/g)) {
    out.push(unquote(m[0]))
  }
  return out
}

/**
 * 把后端 str(exc.errors()) repr 串解析为结构化错误条目。
 * 依赖 pydantic 错误 dict 的固定键序（type → loc → msg → input → ctx），
 * 用单条正则整体匹配可选 loc、msg、可选 input，避免逐键全局收集导致的条目错位。
 * @param text repr 字符串（如 "[{'loc': ('body', 'location'), 'msg': '...', 'input': '冷藏'}]"）
 * @returns 解析出的错误条目数组；无法匹配时为空数组（调用方回退原始 message）
 */
function parseReprDetail(text: string): ValidationErrorEntry[] {
  const entries: ValidationErrorEntry[] = []
  // loc 组可选（pydantic 错误恒有 loc，但防御无 loc 的变体条目）；msg 锚定，input 可选
  const entryRe =
    /(?:'loc':\s*(\[[^\]]*\]|\([^)]*\))\s*,\s*)?'msg':\s*('(?:[^'\\]|\\.)*'|"(?:[^"\\]|\\.)*")(?:\s*,\s*'input':\s*('(?:[^'\\]|\\.)*'|"(?:[^"\\]|\\.)*"|[^,}\][{]*?(?=\s*[,}\]])))?/g
  for (const m of text.matchAll(entryRe)) {
    entries.push({
      loc: m[1] != null ? quotedList(m[1]) : undefined,
      // msg 组（第 2 组）在正则结构上必命中；?? '' 仅为满足 noUncheckedIndexedAccess
      msg: unquote(m[2] ?? ''),
      input: m[3] != null ? unquote(m[3]) : undefined,
    })
  }
  return entries
}

/**
 * 把错误位置路径转为中文（或原样）字段标签。
 * @param loc 位置路径：优先取最后一级字符串字段名（跳过数字索引与 'body' 之外的路径噪音）
 * @returns 字段中文标签；未收录字段原样返回字段名；无法解析返回空串
 */
function fieldLabel(loc: unknown): string {
  if (!Array.isArray(loc)) return ''
  const parts = loc as unknown[]
  const field = [...parts].reverse().find((p): p is string => typeof p === 'string')
  if (!field) return ''
  return FIELD_LABELS[field] ?? field
}

/**
 * 把 pydantic 原始英文消息转译为用户可读文案（仅覆盖常见模式，其余原样透出）。
 * @param msg 原始消息
 * @param input 用户提交的当前值（可选，用于「值必须是…之一」场景后的当前值提示）
 * @returns 可读原因文案；msg 缺失时返回空串
 */
function humanizeMsg(msg: string | undefined, input?: unknown): string {
  if (!msg) return ''
  // 枚举/字面量校验失败：Input should be 'fridge', 'freezer', 'room' or 'dry'
  const enumMatch = msg.match(/^Input should be (.+)$/)
  if (enumMatch) {
    // 第 1 捕获组理论必命中；?? '' 仅为满足 noUncheckedIndexedAccess
    const enumBody = enumMatch[1] ?? ''
    const candidates = [...enumBody.matchAll(/'([^']*)'|"([^"]*)"/g)].map((m) => m[1] ?? m[2])
    if (candidates.length > 0) {
      const base = `值必须是 ${candidates.join('/')} 之一`
      // 附加当前值帮助定位（仅对原始类型值展示，复杂结构不展示）
      if (typeof input === 'string' || typeof input === 'number') return `${base}（当前值：${input}）`
      return base
    }
  }
  // 必填字段缺失
  if (msg === 'Field required') return '缺少必填字段'
  // 自定义校验器错误：剥离前缀后透出（后端此模式通常已给中文话术）
  if (msg.startsWith('Value error, ')) return msg.slice('Value error, '.length)
  return msg
}

/**
 * 拼接单条错误的「字段：原因」片段。
 * @param entry 结构化错误条目
 * @returns 如「存放位置：值必须是 fridge/freezer/room/dry 之一（当前值：冷藏）」；无有效内容返回空串
 */
function entryText(entry: ValidationErrorEntry): string {
  const field = fieldLabel(entry.loc)
  const reason = humanizeMsg(entry.msg, entry.input)
  if (!field && !reason) return ''
  if (!field) return reason
  if (!reason) return field
  return `${field}：${reason}`
}

/**
 * 从 ApiError 中格式化 422 校验错误的具体字段信息（修复缺陷 1.3 的统一入口）。
 * @param error 归一化后的 ApiError（detail 需由响应拦截器透传，见 api/index.ts normalizeError）
 * @returns 「存放位置：值必须是 fridge/freezer/room/dry 之一」样式串，多条以「；」连接；
 *          非 422 错误、无 detail 或解析不出有效内容时返回空串（调用方应回退展示原始 message）
 */
export function format422Detail(error: ApiError): string {
  if (error.code !== 422 && error.code !== 'VALIDATION_ERROR') return ''
  const raw = error.detail
  if (raw == null) return ''
  let entries: ValidationErrorEntry[] = []
  if (Array.isArray(raw)) {
    // 防御分支：detail 为原生 FastAPI 校验错误数组（[{loc, msg, input}]）
    entries = (raw as Record<string, unknown>[]).map((e) => ({
      loc: e?.loc,
      msg: typeof e?.msg === 'string' ? e.msg : e?.msg != null ? String(e.msg) : undefined,
      input: e?.input,
    }))
  } else if (typeof raw === 'string') {
    // 当前后端口径：detail 为 str(exc.errors()) repr 串
    entries = parseReprDetail(raw)
  }
  return entries
    .map(entryText)
    .filter(Boolean)
    .join('；')
}

/**
 * uni.request fail 的 errMsg → 归一化 ApiError（向后兼容增强新增；小程序端请求失败统一入口）。
 * 映射口径复用 web-stage1 api/index.ts normalizeError 的既有错误码与文案：
 * - errMsg 含「timeout」（如 "request:fail timeout"）→ { code: 'TIMEOUT', message: '加载超时，请重试' }；
 * - 其余失败（如 "request:fail abort"、"request:fail "）→
 *   { code: 'NETWORK', message: '网络连接不可用，请检查网络后重试' }。
 * @param errMsg uni.request fail 回调的 errMsg 原始串（可空）
 * @returns 归一化 ApiError（仅含 code 与 message；detail 无）

 * 异常：
 *     不抛出（errMsg 为空 / null / 非超时失败一律按 NETWORK 兜底）。
 */
export function fromUniFailure(errMsg: string): ApiError {
  const msg = errMsg ?? ''
  if (msg.includes('timeout')) return { code: 'TIMEOUT', message: '加载超时，请重试' }
  return { code: 'NETWORK', message: '网络连接不可用，请检查网络后重试' }
}
