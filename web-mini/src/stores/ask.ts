/**
 * 文件职责：「问厨娘」统一消费链路（POST /v1/ask 的唯一消费入口，修复闭环断裂缺陷；
 * 自 web-stage1/src/stores/ask.ts 逐行迁移）。
 * 背景：ask 响应（intent=recipe_search 含 recipe_ids / free_qa 含 answer / blocked）
 * 原先在各入口视图散落消费且互相矛盾。本 store 收敛为单一 action submitQuestion：
 * - 空输入：单条「请输入内容」警示，不发请求（@shared/utils askFlow.isBlankQuestion）；
 * - blocked：写入 recommend store 后跳 W-05（保持既有阻断行为不变）；
 * - recipe_search：按 recipe_ids 拉详情落 recommend store 推荐态后跳推荐列表页
 *   （与手选食材同终端视图；视图按 askMode 放行）；
 * - chat/其他意图：就地展示回答（chat 态由视图渲染，含免责小字）；
 * - 请求/落库失败：单一降级 toast「厨娘暂时走神了，请稍后再试」。
 * 意图分流判定为纯函数（@shared/utils askFlow.resolveAskAction），可被 vitest 直接单测。
 * 平台差异：vue-router push → uni.navigateTo（保留页面栈，语义对齐 push）；
 * W-05 拦截页为分包规划位（pages/recommend/blocked），页面文件由页面迁移任务落位，
 * 跳转失败静默不阻断数据链路（blockedPayload 已写入 store，页面落位后自动生效）。
 */
import { defineStore } from 'pinia'
import { postAsk } from '@/api/endpoints'
import { isBlankQuestion, resolveAskAction } from '@shared/utils'
import { toastError, toastWarning } from '@/utils/toast'
import { useRecommendStore } from './recommend'

/** 推荐列表页路径（分包 pages/recommend/list，W-02） */
const ROUTE_RECOMMEND = '/pages/recommend/list'

/** W-05 风控拦截页路径（分包规划位；页面落位前 navigateTo fail 静默兜底） */
const ROUTE_BLOCKED = '/pages/recommend/blocked'

/**
 * 页面跳转（平台适配辅助：对齐 vue-router push 的保留栈语义）。
 * @param url 页面路径（以 / 开头，支持分包页面）
 * @returns 无
 * @throws 不抛出（页面未注册 / 页面栈异常等失败一律静默，不阻断数据链路）
 */
function navigateTo(url: string): void {
  try {
    uni.navigateTo({
      url,
      fail: () => {
        // 跳转失败（页面未落位等）：静默，不阻断主流程
      },
    })
  } catch {
    // 极端环境同步异常：静默
  }
}

/** chat 就地展示数据（受限问答结果卡） */
export interface AskChatEntry {
  /** 用户问句（回显溯源） */
  question: string
  /** 厨娘回答文本（已含兜底文案，非空） */
  answer: string
  /** 本次 ask 的 trace ID（取证线索） */
  traceId: string
}

/** 请求/落库失败的统一降级文案（单一出口，避免多路错误提示堆叠；搜索对话流复用） */
export const ASK_FAILED_MESSAGE = '厨娘暂时走神了，请稍后再试'

export const useAskStore = defineStore('ask', {
  state: () => ({
    /** ask 请求进行中标记（跨页面共用，防重复提交；首页按钮 loading 亦读取此态） */
    asking: false,
    /** chat 就地展示数据（null = 无待展示回答；新提问发起时清空旧回答） */
    chat: null as AskChatEntry | null,
  }),
  actions: {
    /**
     * 提交自然语言问句（唯一 ask 消费入口；首页 / 选食材页共用）。
     * 消费顺序：空输入守卫 → postAsk → resolveAskAction 意图分流 → 各分支副作用。
     * @param text 用户输入原文（内部自行 trim；空/空白输入不发请求）
     * @returns 无
     * @throws 不抛出（请求与各分支副作用失败均收敛为单一降级提示）
     */
    async submitQuestion(text: string): Promise<void> {
      const t = text.trim()
      // 空输入守卫（A1）：单条提示，不发请求
      if (isBlankQuestion(t)) {
        toastWarning('请输入内容')
        return
      }
      // 防重复提交：进行中直接忽略后续触发（回车连按 / 按钮连点）
      if (this.asking) return
      this.asking = true
      // 新提问清空上一条 chat 回答，避免旧结果串场
      this.chat = null
      try {
        const res = await postAsk(t)
        const action = resolveAskAction(res)
        if (action.type === 'blocked') {
          // 命中风控一票否决（G-01）：写 W-05 数据源后跳拦截页，行为与既有链路一致
          const recommendStore = useRecommendStore()
          recommendStore.blockedPayload = action.payload
          recommendStore.traceId = action.payload.trace_id || res.trace_id
          navigateTo(ROUTE_BLOCKED)
          return
        }
        if (action.type === 'recipe_search') {
          // 搜索命中：按 ids 拉详情落推荐态（askMode 置位，推荐页守卫放行）
          // 第 4 参透传 res.request_id：「查看调度详情」跳 trace 查询串联取证
          const recommendStore = useRecommendStore()
          await recommendStore.applyAskResults(action.recipeIds, t, res.trace_id, res.request_id)
          navigateTo(ROUTE_RECOMMEND)
          return
        }
        // chat / 其他意图：就地展示回答（视图渲染，含免责小字）
        this.chat = { question: t, answer: action.answer, traceId: res.trace_id }
      } catch {
        // 单一降级：请求失败或 ask 结果落库失败，均收敛为同一条提示
        toastError(ASK_FAILED_MESSAGE)
      } finally {
        this.asking = false
      }
    },

    /**
     * 收起 chat 回答卡（视图「收起」按钮调用）。
     * @returns 无
     */
    clearChat(): void {
      this.chat = null
    },
  },
})
