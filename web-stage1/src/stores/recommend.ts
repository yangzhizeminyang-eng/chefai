/**
 * 文件职责：推荐结果状态（W-02 数据源）。
 * - results：三档推荐结果（can_cook_now / missing_1_2 / need_more 由 match_level 区分）；
 * - blockedPayload：一票否决短路响应暂存（供 W-05 拦截页读取）；
 * - traceId / partialNotice / filtered / showFilteredItems：面板与展示开关所需字段。
 */
import { defineStore } from 'pinia'
import { postRecommend } from '@/api/endpoints'
import type { ApiError, BlockedResponse, RecommendResponseWithFiltered, RecommendResultItem } from '@/api/types'
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
    /** 最近一次成功请求的 trace ID（跳转调度面板用） */
    traceId: '',
    /** 一票否决短路响应暂存（W-05 拦截页数据源；进入 /blocked 前必须非空） */
    blockedPayload: null as BlockedResponse | null,
    /** 布尔硬过滤计数（allergen / dietary_restriction / difficulty） */
    filtered: {} as { allergen?: number; dietary_restriction?: number; difficulty?: number },
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
          this.results = []
        } else {
          const ok = res as Exclude<RecommendOutcome, BlockedResponse> as RecommendResponseWithFiltered
          this.results = ok.results ?? []
          this.filtered = ok.filtered_by ?? {}
          this.traceId = ok.trace_id ?? ''
          this.partialNotice = (ok.partial_failures ?? []).join('；')
          this.notice = ok.notice ?? ''
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
     * 清空推荐状态（重新选择食材后调用）。
     */
    reset(): void {
      this.results = []
      this.error = null
      this.partialNotice = ''
      this.notice = ''
      this.traceId = ''
      this.blockedPayload = null
      this.filtered = {}
      this.filteredItems = []
      this.lastRequestKey = ''
    },
  },
})
