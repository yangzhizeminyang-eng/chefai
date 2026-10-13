/**
 * 文件职责：跨端共享的用户可见安全文案常量（单点维护，避免同义文案多处分叉导致不一致）。
 * 从 web-stage1/src/constants/copy.ts 零改造迁移 MEMBER_QUOTA_LABEL，
 * 并追加阶段二小程序端统一引用的安全/降级/拦截/免责文案常量
 * （供 web-mini 经 vite alias @shared 引用，禁止在视图里散落硬编码）。
 */

/** 会员「本周期识别额度」标签文案（识别结果页 /member 页额度展示同源引用，L4-3 修复） */
export const MEMBER_QUOTA_LABEL = '本周期识别额度'

/** 过敏原提示固定后缀（涉敏内容后追加，提示以包装标签为准） */
export const ALLERGEN_ALERT_SUFFIX = '请以实际食材包装标签为准'

/** AI 生成内容通用免责声明（多场景共用基础文案） */
export const DISCLAIMER_TEXT = '内容由 AI 生成，仅供参考，不构成专业建议'

/** 首页免责声明（与通用文案同源，独立命名便于按场景单独调整） */
export const DISCLAIMER_HOME = DISCLAIMER_TEXT

/** 菜谱详情页免责声明（与通用文案同源） */
export const DISCLAIMER_DETAIL = DISCLAIMER_TEXT

/** 营养区免责声明（估算口径专门声明） */
export const DISCLAIMER_NUTRITION = '营养数据为估算值，非实测值，仅供参考'

/** 风险拦截页就医引导声明 */
export const DISCLAIMER_RISK = '本结果仅作饮食参考，如有身体不适请及时就医'

/** 分享卡片免责声明（空间受限的短文案） */
export const DISCLAIMER_SHARE = '内容由 AI 生成，仅供参考'

/** 营养每份估算前缀（如「每份约含 350 kcal」） */
export const NUTRITION_STATEMENT_PREFIX = '每份约含'

/** 营养估算口径标注（数值后附注） */
export const NUTRITION_ESTIMATE_NOTE = '估算值，非实测值'

/** 保守模式（安全模式）顶部提示条文案 */
export const SAFE_MODE_BAR_TEXT = '安全服务暂时不可用，已切换为保守模式，部分内容可能无法生成'

/** 部分内容降级提示条文案（partial_failures 非空时展示） */
export const DEGRADED_BAR_TEXT = '本次部分内容未能生成，仅供参考'

/** 食品安全风险一票否决拦截文案 */
export const RISK_BLOCK_FOOD_TEXT = '该请求涉及食品安全风险，未生成任何内容'

/** 过敏原风险拦截文案 */
export const RISK_BLOCK_ALLERGEN_TEXT = '该内容可能涉及您的过敏原风险，已阻止展示'

/** 医疗诊断类问题拦截文案 */
export const RISK_BLOCK_MEDICAL_TEXT = '该问题涉及医疗诊断，建议咨询专业医生'

/** 医疗健康类提问受限问答引导文案 */
export const MEDICAL_REFUSE_TEXT = '涉及医疗健康问题，建议咨询专业医生或医疗机构'

/** 可食用性判断边界说明（系统不判断食材是否可食用） */
export const INEDIBLE_JUDGE_NOTE = '系统不判断食材是否可食用，变质或过期食材请勿使用'

/** 图片来源标注（HowToCook 语料配图，Unlicense 公有领域） */
export const IMAGE_SOURCE_NOTE = '图片来源：HowToCook 语料配图（Unlicense 公有领域）'

/** 计时器切后台边界说明（提醒可能延迟） */
export const TIMER_BOUNDARY_NOTE = '小程序切后台后提醒可能延迟，建议停留在小程序内查看计时'

/** 登录服务不可用降级文案（保留本地数据） */
export const LOGIN_FALLBACK_TEXT = '登录暂不可用，已保留本地数据'

/** 离线可用提示条文案（有缓存内容时） */
export const OFFLINE_BAR_TEXT = '当前网络不可用，已缓存内容可正常查看'

/** 离线且无缓存提示文案 */
export const OFFLINE_UNCACHED_TEXT = '该内容需联网加载'
