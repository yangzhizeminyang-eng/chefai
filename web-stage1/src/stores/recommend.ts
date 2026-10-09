/**
 * 文件职责：推荐结果状态（W-02 数据源）。
 * - results：三档推荐结果（can_cook_now / missing_1_2 / need_more 由 match_level 区分）；
 * - blockedPayload：一票否决短路响应暂存（供 W-05 拦截页读取）；
 * - traceId / partialNotice / filtered / showFilteredItems：面板与展示开关所需字段；
 * - askMode / askQuestion + applyAskResults：ask 搜索结果直达态（「问厨娘」链路，
 *   按 recipe_ids 拉取菜谱详情落入推荐态，/recommend 路由守卫据此放行无已选食材的进入）。
 */
import { defineStore } from 'pinia'
import { getRecipe, postRecommend } from '@/api/endpoints'
import type {
  ApiError,
  BlockedResponse,
  RecommendResponseWithFiltered,
  RecommendResultItem,
  RecipeDetail,
} from '@/api/types'
import { recipeDetailToAskItem } from '@/utils/askFlow'
import { useIngredientsStore } from './ingredients'
import { useSessionStore } from './session'

/** 推荐响应（正常或短路二选一，运行时以 blocked 字段判别） */
type RecommendOutcome = Awaited<ReturnType<typeof postRecommend>>

export const useRecommendStore = defineStore('recommend', {
  state: () => ({
    /** 三档推荐结果列表（空数组 = 无匹配） */
    results: [] as RecommendResultItem[],
    /** 推荐请求进行中标记 */
    loading: false,
    /** 请求错误（归一化 ApiError） */
    error: null as ApiError | null,
    /** 部分 Agent 失败说明（非空时页面顶部展示「本次部分内容未能生成」条） */
    partialNotice: '',
    /** 保守模式标记（响应 safe_mode，§5.7/RL-4：风控不可用降级时页面顶部展示保守模式条） */
    safeMode: false,
    /** 最近一次成功请求的 trace ID（跳转调度面板用） */
    traceId: '',
    /** 最近一次请求的幂等键 request_id（响应回显；W-02 展示并串联 /trace?request_id= 查询） */
    requestId: '',
    /** 一票否决短路响应暂存（W-05 拦截页数据源；进入 /blocked 前必须非空） */
    blockedPayload: null as BlockedResponse | null,
    /** 布尔硬过滤计数（allergen / dietary_restriction / difficulty / equipment 设备维度） */
    filtered: {} as {
      allergen?: number
      dietary_restriction?: number
      difficulty?: number
      equipment?: number
    },
    /** 「显示被我过滤掉的菜」开关（W-02 展示控制） */
    showFilteredItems: false,
    /** 本次推荐使用的食材摘要（提交时快照，供 W-02 顶部展示） */
    usedIngredients: [] as string[],
    /** 附加提示文案（响应 notice 字段，非空时页面顶部如实展示） */
    notice: '',
    /** 被过滤菜谱清单（show_filtered=true 且后端返回清单时非空；否则以 filtered 计数展示） */
    filteredItems: [] as import('@/api/types').FilteredRecipeItem[],
    /** 最近一次请求指纹（已选食材 ID 组合 + 开关；相同且已有结果时不重复请求） */
    lastRequestKey: '',
    /** ask 结果直达态：true 表示当前 results 来自「问厨娘」搜索链路（守卫放行 + 视图差异化展示） */
    askMode: false,
    /** 触发 ask 搜索的用户问句（W-02 摘要栏展示，溯源用） */
    askQuestion: '',
  }),
  actions: {
    /**
     * 发起推荐请求：以 ingredients store 的已选食材为输入。
     * 响应为短路体时写入 blockedPayload；正常体时写 results/filtered/trace 等。
     * @param force 是否强制重发（重试按钮/开关切换用；缺省时相同请求指纹且已有结果则跳过）
     */
    async fetchRecommend(force = false): Promise<void> {
      const ingredientsStore = useIngredientsStore()
      const sessionStore = useSessionStore()
      // 手选路径接管：清 ask 结果直达态（摘要栏 / 路由守卫 / 视图分支随之回到手选语义）
      this.askMode = false
      this.askQuestion = ''
      // 防重复指纹：已选食材 ID 组合 + 展示开关（W-02 反复进出不重复打接口）
      const requestKey = JSON.stringify({
        ids: ingredientsStore.selectedList.map((s) => s.id),
        showFiltered: this.showFilteredItems,
      })
      if (!force && requestKey === this.lastRequestKey && this.results.length > 0 && !this.loading) {
        return
      }
      this.lastRequestKey = requestKey
      this.loading = true
      this.error = null
      this.partialNotice = ''
      this.safeMode = false
      this.notice = ''
      this.filteredItems = []
      // 快照已选食材名（W-02 摘要展示）
      this.usedIngredients = ingredientsStore.selectedList.map((s) => s.name)
      try {
        // 确保匿名 ID 存在（懒获取）
        await sessionStore.ensureAnonymousId()
        const res: RecommendOutcome = await postRecommend({
          // request_id 由 axios 拦截器自动注入
          request_id: '',
          client_type: 'web_stage1',
          ingredients: ingredientsStore.selectedList.map((s) => ({
            ingredient_id: s.id,
            quantity_level: 'enough',
          })),
          options: { show_filtered: this.showFilteredItems },
        })
        // 运行时判别：一票否决短路体（blocked=true）与正常体
        if ('blocked' in res && res.blocked) {
          this.blockedPayload = res as BlockedResponse
          this.traceId = res.trace_id ?? ''
          // 短路体同样回显幂等键，保证 W-05 → W-06 取证链路一致
          this.requestId = res.request_id ?? ''
          this.results = []
        } else {
          const ok = res as Exclude<RecommendOutcome, BlockedResponse> as RecommendResponseWithFiltered
          this.results = ok.results ?? []
          this.filtered = ok.filtered_by ?? {}
          this.traceId = ok.trace_id ?? ''
          // 幂等键回显：W-02 展示 + 「查看调度详情」跳 /trace?request_id= 用
          this.requestId = ok.request_id ?? ''
          this.partialNotice = (ok.partial_failures ?? []).join('；')
          this.notice = ok.notice ?? ''
          // 保守模式（§5.7/RL-4）：风控不可用降级标记，W-02 顶部展示保守模式条
          this.safeMode = ok.safe_mode === true
          // 双模式支持：清单模式（filtered 数组）与计数模式（filtered_by）都接收
          this.filteredItems = ok.filtered ?? []
          this.blockedPayload = null
        }
      } catch (e) {
        this.error = e as ApiError
      } finally {
        this.loading = false
      }
    },

    /**
     * 「问厨娘」搜索结果直达：按 ask 响应的 recipe_ids 并行拉取菜谱详情，
     * 映射为推荐卡片数据写入 results，进入 askMode（W-02 守卫放行 + 差异化展示）。
     * 全部详情拉取失败时抛错，由 ask store 统一降级 toast，不发生跳转。
     * @param recipeIds ask 响应携带的菜谱 ID 列表（非空，由 resolveAskAction 保证）
     * @param question 触发本次搜索的用户问句（溯源展示用）
     * @param traceId ask 响应的 trace ID（W-02 底部取证线索）
     * @returns 无
     * @exception 全部菜谱详情拉取失败时抛出 Error（调用方捕获后做单一降级提示）
     */
    async applyAskResults(recipeIds: number[], question: string, traceId: string): Promise<void> {
      // 并行拉详情，单个失败容忍（部分成功仍展示成功的部分）
      const settled: PromiseSettledResult<RecipeDetail>[] = await Promise.allSettled(
        recipeIds.map((id) => getRecipe(id)),
      )
      const items = settled.flatMap((s) =>
        s.status === 'fulfilled' ? [recipeDetailToAskItem(s.value, question)] : [],
      )
      if (items.length === 0) {
        // 全部失败视为本次 ask 消费失败：抛错走统一降级，避免落空列表进入 W-02 空态
        throw new Error('ASK_RESULTS_FETCH_FAILED')
      }
      this.results = items
      this.usedIngredients = []
      this.filtered = {}
      this.filteredItems = []
      this.partialNotice = ''
      this.notice = ''
      // 保守模式标记随 ask 结果一并清理：ask 链路不经过推荐风控管线，
      // 不清理会把上一次手选推荐的 safe_mode 条残留到 ask 结果页（状态泄漏）
      this.safeMode = false
      this.error = null
      this.traceId = traceId
      this.requestId = ''
      this.blockedPayload = null
      this.askMode = true
      this.askQuestion = question
      // ask 专属指纹：与手选路径指纹格式区分，进出 W-02 不误触发手选重拉
      this.lastRequestKey = `ask:${recipeIds.join(',')}`
    },

    /**
     * 清空推荐状态（重新选择食材后调用）。
     */
    reset(): void {
      this.results = []
      this.error = null
      this.partialNotice = ''
      this.safeMode = false
      this.notice = ''
      this.traceId = ''
      this.requestId = ''
      this.blockedPayload = null
      this.filtered = {}
      this.filteredItems = []
      this.lastRequestKey = ''
      this.askMode = false
      this.askQuestion = ''
    },
  },
})
