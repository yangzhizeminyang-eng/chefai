/**
 * 文件职责：首页聚合状态（GET /v1/home 数据源）。
 * - data：入口可用性 / 未完成会话 / 临期食材 / 档案提示 / 时令分类；
 * - load()：拉取聚合数据并维护三态；后端不可用时 data 为 null（页面走异常态兜底）；
 * - 临期提醒的当日关闭记忆由页面用 localStorage `aicook_expiry_dismissed_{date}` 处理，
 *   本 store 不持久化 UI 态。
 */
import { defineStore } from 'pinia'
import { getHome } from '@/api/endpoints'
import type { ApiError, HomeResponse } from '@/api/types'

export const useHomeStore = defineStore('home', {
  state: () => ({
    /** 首页聚合数据（null = 尚未加载成功） */
    data: null as HomeResponse | null,
    /** 加载中标记 */
    loading: false,
    /** 加载错误（归一化 ApiError，null 表示无错） */
    error: null as ApiError | null,
  }),
  getters: {
    /**
     * 是否存在进行中的烹饪会话（「继续上次的菜」卡片显隐）。
     * @returns 有未完成会话为 true
     */
    hasUnfinished: (state): boolean => !!state.data?.unfinished_session,
    /**
     * 是否已建档（未建档时展示黄条引导）。
     * @returns 已建档为 true（数据未加载时默认视为已建档，避免误报）
     */
    hasProfile: (state): boolean => state.data?.profile_hint.has_profile ?? true,
  },
  actions: {
    /**
     * 拉取首页聚合数据（每次进入首页调用，保证临期/未完成会话新鲜）。
     * @returns 无
     */
    async load(): Promise<void> {
      this.loading = true
      this.error = null
      try {
        this.data = await getHome()
      } catch (e) {
        this.error = e as ApiError
        this.data = null
      } finally {
        this.loading = false
      }
    },
  },
})
