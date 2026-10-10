/**
 * 文件职责：「问厨娘」统一消费链路（POST /v1/ask 的唯一消费入口，修复闭环断裂缺陷）。
 * 背景：ask 响应（intent=recipe_search 含 recipe_ids / free_qa 含 answer / blocked）
 * 原先在 HomeView 与 SelectIngredientView 各自散落消费且互相矛盾（三路 toast 同时弹出、
 * 结果无人落地、/recommend 守卫弹回）。本 store 收敛为单一 action submitQuestion：
 * - 空输入：单条「请输入内容」警示，不发请求（工具 utils/askFlow.isBlankQuestion）；
 * - blocked：写入 recommend store 后跳 W-05（保持既有阻断行为不变）；
 * - recipe_search：按 recipe_ids 拉详情落 recommend store 推荐态后跳 /recommend
 *   （与手选食材同终端视图；守卫按 askMode 放行）；
 * - chat/其他意图：就地展示回答（chat 态由 AskChatCard 渲染，含免责小字）；
 * - 请求/落库失败：单一降级 toast「厨娘暂时走神了，请稍后再试」。
 * 意图分流判定为纯函数（utils/askFlow.resolveAskAction），可被 vitest 直接单测。
 */
import { defineStore } from 'pinia'
import { postAsk } from '@/api/endpoints'
import { isBlankQuestion, resolveAskAction } from '@/utils/askFlow'
import { toastError, toastWarning } from '@/utils/toast'
import router from '@/router'
import { useRecommendStore } from './recommend'

/** chat 就地展示数据（受限问答结果卡） */
export interface AskChatEntry {
  /** 用户问句（回显溯源） */
  question: string
  /** 厨娘回答文本（已含兜底文案，非空） */
  answer: string
  /** 本次 ask 的 trace ID（取证线索） */
  traceId: string
}

/** 请求/落库失败的统一降级文案（单一出口，避免多路错误提示堆叠） */
const ASK_FAILED_MESSAGE = '厨娘暂时走神了，请稍后再试'

export const useAskStore = defineStore('ask', {
  state: () => ({
    /** ask 请求进行中标记（跨视图共用，防重复提交；首页按钮 loading 亦读取此态） */
    asking: false,
    /** chat 就地展示数据（null = 无待展示回答；新提问发起时清空旧回答） */
    chat: null as AskChatEntry | null,
  }),
  actions: {
    /**
     * 提交自然语言问句（唯一 ask 消费入口；HomeView / SelectIngredientView 共用）。
     * 消费顺序：空输入守卫 → postAsk → resolveAskAction 意图分流 → 各分支副作用。
     * @param text 用户输入原文（内部自行 trim；空/空白输入不发请求）
     * @returns 无
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
          void router.push('/blocked')
          return
        }
        if (action.type === 'recipe_search') {
          // 搜索命中：按 ids 拉详情落推荐态（askMode 置位，/recommend 守卫放行）
          // 第 4 参透传 res.request_id：W-02「查看调度详情」跳 /trace?request_id= 串联取证
          const recommendStore = useRecommendStore()
          await recommendStore.applyAskResults(action.recipeIds, t, res.trace_id, res.request_id)
          void router.push('/recommend')
          return
        }
        // chat / 其他意图：就地展示回答（AskChatCard 渲染，含免责小字）
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
