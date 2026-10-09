/**
 * 文件职责：个人中心状态（/v1/favorites、/v1/history、/v1/signature-dishes、
 * /v1/settings、/v1/member/*、/v1/feedback、/v1/me/* 数据源）。
 * - favorites/history/signature：收藏（分组）/ 历史 / 拿手菜三块只读列表；
 * - settings：字号/单位/语音/提醒（PUT 保存，字号档位由页面作用于根 CSS 变量）；
 * - member：套餐与支付开关 / 会员状态与额度 / 订单列表（模拟支付联调）；
 * - exportMe/deleteAccount：数据导出与注销。
 * 各块独立三态（loading/error），进入 /me 页时由页面按需分区拉取。
 */
import { defineStore } from 'pinia'
import {
  deleteFavorite,
  deleteMeAccount,
  getFavorites,
  getHistory,
  getMeExport,
  getMemberMe,
  getMemberOrders,
  getMemberPlan,
  getSettings,
  getSignatureDishes,
  postFeedback,
  postMemberMockPay,
  postMemberOrder,
  putSettings,
} from '@/api/endpoints'
import type {
  ApiError,
  FavoriteItem,
  HistoryItem,
  MeExportData,
  MemberMeResponse,
  MemberOrdersResponse,
  MemberPlanResponse,
  SettingsData,
  SignatureDish,
} from '@/api/types'

export const useMeStore = defineStore('me', {
  state: () => ({
    /* ── 收藏 / 历史 / 拿手菜 ── */
    /** 收藏条目（当前分组过滤后的结果） */
    favorites: [] as FavoriteItem[],
    /** 收藏分组名列表（后端返回全部分组） */
    favoriteGroups: [] as string[],
    /** 收藏加载中 */
    favoritesLoading: false,
    /** 收藏加载错误 */
    favoritesError: null as ApiError | null,
    /** 烹饪历史（后端倒序） */
    history: [] as HistoryItem[],
    /** 历史加载中 */
    historyLoading: false,
    /** 历史加载错误 */
    historyError: null as ApiError | null,
    /** 拿手菜列表 */
    signature: [] as SignatureDish[],
    /** 拿手菜加载中 */
    signatureLoading: false,
    /** 拿手菜加载错误 */
    signatureError: null as ApiError | null,

    /* ── 设置 ── */
    /** 用户设置（null = 尚未加载，页面用默认值渲染） */
    settings: null as SettingsData | null,
    /** 设置保存中 */
    settingsSaving: false,
    /** 设置加载/保存错误 */
    settingsError: null as ApiError | null,

    /* ── 会员 ── */
    /** 套餐与支付开关 */
    plans: null as MemberPlanResponse | null,
    /** 会员状态与额度 */
    memberMe: null as MemberMeResponse | null,
    /** 订单列表 */
    orders: [] as MemberOrdersResponse['items'],
    /** 会员区加载中 */
    memberLoading: false,
    /** 会员区错误 */
    memberError: null as ApiError | null,
  }),
  actions: {
    /**
     * 拉取收藏（可按分组过滤）。
     * @param group 分组名（可选，缺省全部）
     * @returns 无
     */
    async loadFavorites(group?: string): Promise<void> {
      this.favoritesLoading = true
      this.favoritesError = null
      try {
        const res = await getFavorites(group)
        this.favorites = res.items ?? []
        this.favoriteGroups = res.groups ?? []
      } catch (e) {
        this.favoritesError = e as ApiError
        this.favorites = []
      } finally {
        this.favoritesLoading = false
      }
    },

    /**
     * 删除收藏（本地同步移除）。
     * @param recipeId 菜谱 ID
     * @returns 无
     */
    async removeFavorite(recipeId: number): Promise<void> {
      await deleteFavorite(recipeId)
      this.favorites = this.favorites.filter((f) => f.recipe_id !== recipeId)
    },

    /**
     * 拉取烹饪历史。
     * @returns 无
     */
    async loadHistory(): Promise<void> {
      this.historyLoading = true
      this.historyError = null
      try {
        const res = await getHistory()
        this.history = res.items ?? []
      } catch (e) {
        this.historyError = e as ApiError
        this.history = []
      } finally {
        this.historyLoading = false
      }
    },

    /**
     * 拉取拿手菜。
     * @returns 无
     */
    async loadSignature(): Promise<void> {
      this.signatureLoading = true
      this.signatureError = null
      try {
        const res = await getSignatureDishes()
        this.signature = res.items ?? []
      } catch (e) {
        this.signatureError = e as ApiError
        this.signature = []
      } finally {
        this.signatureLoading = false
      }
    },

    /**
     * 拉取用户设置。
     * @returns 无
     */
    async loadSettings(): Promise<void> {
      this.settingsError = null
      try {
        this.settings = await getSettings()
      } catch (e) {
        this.settingsError = e as ApiError
      }
    },

    /**
     * 保存用户设置（本地同步，字号档位立即生效由页面处理）。
     * @param settings 全量设置
     * @returns 无
     */
    async saveSettings(settings: SettingsData): Promise<void> {
      this.settingsSaving = true
      this.settingsError = null
      try {
        const saved = await putSettings(settings)
        this.settings = saved
      } catch (e) {
        this.settingsError = e as ApiError
        throw e
      } finally {
        this.settingsSaving = false
      }
    },

    /**
     * 拉取会员区数据（套餐/状态额度/订单三段并行，任一失败置空兜底）。
     * @returns 无
     */
    async loadMember(): Promise<void> {
      this.memberLoading = true
      this.memberError = null
      const results = await Promise.allSettled([
        getMemberPlan(),
        getMemberMe(),
        getMemberOrders(),
      ])
      this.plans = results[0].status === 'fulfilled' ? results[0].value : null
      this.memberMe = results[1].status === 'fulfilled' ? results[1].value : null
      this.orders = results[2].status === 'fulfilled' ? (results[2].value.items ?? []) : []
      const firstRejected = results.find((r) => r.status === 'rejected')
      this.memberError = firstRejected && firstRejected.status === 'rejected'
        ? firstRejected.reason as ApiError
        : null
      this.memberLoading = false
    },

    /**
     * 创建订单 → 模拟支付 → 刷新订单与会员状态（购买主链路）。
     * @param productType 套餐类型
     * @returns 支付完成时间（ISO 8601）
     */
    async purchase(productType: 'monthly' | 'quarterly' | 'yearly'): Promise<string> {
      const order = await postMemberOrder(productType)
      const paid = await postMemberMockPay(order.order_no)
      await this.loadMember()
      return paid.paid_at
    },

    /**
     * 提交意见反馈。
     * @param content 反馈内容
     * @param type 类型（bug / suggestion / other）
     * @returns 回执号
     */
    async submitFeedback(content: string, type: 'bug' | 'suggestion' | 'other'): Promise<string> {
      const res = await postFeedback(content, type)
      return res.receipt_no
    },

    /**
     * 导出个人数据（返回 JSON 对象，由页面触发浏览器下载）。
     * @returns 导出数据
     */
    async exportData(): Promise<MeExportData> {
      return getMeExport()
    },

    /**
     * 注销账号（服务端删除）。
     * @returns 无
     */
    async deleteAccount(): Promise<void> {
      await deleteMeAccount()
    },
  },
})
