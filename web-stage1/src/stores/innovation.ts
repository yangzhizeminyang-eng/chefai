/**
 * 文件职责：AI 创新菜状态（/v1/innovation/* 数据源）。
 * - precheck → generate 主链路：预检命中拦截时暂存 blocked 信息（页面展示拦截话术卡）；
 * - current：当前生成的创新菜谱实体（含创新依据 / 营养 / 强制声明）；
 * - myRecipes：已采纳的「我的创新菜」（本次会话内存态，进入页面时可重拉）；
 * - generating：生成中标记（页面据此展示「正在基于食材性质与搭配规则创新…」动画）。
 */
import { defineStore } from 'pinia'
import {
  getInnovationRecipe,
  postInnovationAdopt,
  postInnovationFeedback,
  postInnovationGenerate,
  postInnovationPrecheck,
  postInnovationReuse,
} from '@/api/endpoints'
import type {
  ApiError,
  InnovationPrecheckResponse,
  InnovationRecipe,
} from '@/api/types'

export const useInnovationStore = defineStore('innovation', {
  state: () => ({
    /** 预检结果（null = 未预检） */
    precheck: null as InnovationPrecheckResponse | null,
    /** 当前生成的创新菜谱（null = 无结果） */
    current: null as InnovationRecipe | null,
    /** 已采纳的创新菜列表（内存态） */
    myRecipes: [] as InnovationRecipe[],
    /** 预检/生成进行中 */
    generating: false,
    /** 预检/生成错误（归一化 ApiError） */
    error: null as ApiError | null,
  }),
  actions: {
    /**
     * 预检 + 生成主链路：先 precheck，命中拦截则只存 blocked 信息；
     * 通过后再 generate，结果写入 current。
     * @param ingredients 食材名列表（至少 1 项）
     * @returns 无
     */
    async generate(ingredients: string[]): Promise<void> {
      this.generating = true
      this.error = null
      this.precheck = null
      this.current = null
      try {
        const pre = await postInnovationPrecheck(ingredients)
        this.precheck = pre
        if (pre.blocked) return
        this.current = await postInnovationGenerate(ingredients)
      } catch (e) {
        this.error = e as ApiError
      } finally {
        this.generating = false
      }
    },

    /**
     * 采纳当前创新菜：入库「我的创新菜」（本地去重追加）。
     * @param recipe 要采纳的创新菜谱（缺省取 current）
     * @returns 是否采纳成功
     */
    async adopt(recipe?: InnovationRecipe): Promise<boolean> {
      const target = recipe ?? this.current
      if (!target) return false
      await postInnovationAdopt(target.id)
      if (!this.myRecipes.some((r) => r.id === target.id)) {
        this.myRecipes = [target, ...this.myRecipes]
      }
      return true
    },

    /**
     * 复用创新菜：调 reuse 接口并把返回实体置为 current（页面可再走采纳/评分）。
     * @param id 创新菜谱 ID
     * @returns 是否可复用
     */
    async reuse(id: number): Promise<boolean> {
      this.generating = true
      this.error = null
      try {
        const res = await postInnovationReuse(id)
        if (res.ok && res.recipe) {
          this.current = res.recipe
          return true
        }
        return false
      } catch (e) {
        this.error = e as ApiError
        return false
      } finally {
        this.generating = false
      }
    },

    /**
     * 拉取创新菜详情（我的创新菜列表点开时）。
     * @param id 创新菜谱 ID
     * @returns 创新菜谱实体
     */
    async fetchById(id: number): Promise<InnovationRecipe> {
      const recipe = await getInnovationRecipe(id)
      this.current = recipe
      return recipe
    },

    /**
     * 提交创新菜评分反馈。
     * @param id 创新菜谱 ID
     * @param rating 评分 1~5
     * @param comment 文字评价（可选）
     * @returns 无
     */
    async sendFeedback(id: number, rating: number, comment?: string): Promise<void> {
      await postInnovationFeedback(id, { rating, comment })
    },

    /**
     * 清空当前生成结果（重新选择食材时调用，保留 myRecipes）。
     */
    resetCurrent(): void {
      this.current = null
      this.precheck = null
      this.error = null
    },
  },
})
