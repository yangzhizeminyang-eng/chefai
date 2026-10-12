/**
 * 文件职责：AI 创新菜状态（/v1/innovation/* 数据源）。
 * - precheck → generate 主链路（M-01 异步任务化）：前端预检命中拦截时暂存 blocked
 *   信息（页面展示拦截话术卡）；通过后提交异步 job（POST /v1/innovation/jobs）并
 *   以 2.5s 间隔轮询任务状态（总上限 100s），与后端五态状态机对应：
 *   pending/running 继续等待 → succeeded 取 recipe 写入 current；failed 归一为
 *   GENERATION_FAILED 走 error 态；blocked 映射为 precheck 结构复用页面拦截卡；
 *   轮询超上限抛 TIMEOUT 走 error 态；
 * - current：当前生成的创新菜谱实体（含创新依据 / 营养 / 强制声明）；
 * - myRecipes：已采纳的「我的创新菜」（本次会话内存态，进入页面时可重拉）；
 * - generating：生成中标记（页面据此展示「已提交生成任务，正在基于食材性质与
 *   搭配规则创新…完成后自动展示（通常 10–60 秒）」动画）。
 */
import { defineStore } from 'pinia'
import {
  getInnovationJob,
  getInnovationRecipe,
  postInnovationAdopt,
  postInnovationFeedback,
  postInnovationJobCreate,
  postInnovationPrecheck,
  postInnovationReuse,
} from '@/api/endpoints'
import type {
  ApiError,
  InnovationPrecheckResponse,
  InnovationRecipe,
} from '@/api/types'

/** 轮询间隔（毫秒）：与后端 job 状态机更新粒度对齐，可按环境调优 */
const POLL_INTERVAL_MS = 2500

/** 轮询总时长上限（毫秒）：100s 覆盖后端 25s LLM 硬超时 + 排队余量，可按环境调优 */
const POLL_TOTAL_LIMIT_MS = 100000

/**
 * 等待指定毫秒（轮询间隔的 sleep 封装，便于 fake timers 单测控制节奏）。
 * @param ms 等待时长（毫秒）
 * @returns Promise，到时 resolve
 */
function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms))
}

export const useInnovationStore = defineStore('innovation', {
  state: () => ({
    /** 预检结果（null = 未预检；blocked 时页面展示拦截卡） */
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
     * 预检 + 生成主链路（M-01 异步任务化）：
     * ① 前端 precheck 保留（拦截卡提前展示，命中拦截省一次任务提交）；
     * ② 提交异步生成任务（POST /v1/innovation/jobs，202 秒回）；
     * ③ 以 2.5s 间隔轮询 GET /v1/innovation/jobs/{id}（总上限 100s）：
     *    - succeeded → 取完整 recipe（含 is_ai_innovated / disclaimer）写入 current；
     *    - failed → 归一为 { code:'GENERATION_FAILED', message: error || 兜底文案 } 抛出；
     *    - blocked → 映射为 precheck 结构（页面复用拦截卡展示）后返回；
     *    - pending / running → 继续下一轮；
     *    - 超上限仍无终态 → 归一为 { code:'TIMEOUT', message:'生成超时，请重试' } 抛出。
     * 轮询间隔与总上限为模块常量可调（POLL_INTERVAL_MS / POLL_TOTAL_LIMIT_MS）。
     * @param ingredients 食材名列表（至少 1 项）
     * @returns 无
     */
    async generate(ingredients: string[]): Promise<void> {
      this.generating = true
      this.error = null
      this.precheck = null
      this.current = null
      try {
        // ① 前端预检保留：命中拦截立即展示拦截卡
        const pre = await postInnovationPrecheck(ingredients)
        this.precheck = pre
        if (pre.blocked) return
        // ② 提交异步生成任务（后端 202 秒回，LLM 在服务端异步执行）
        const job = await postInnovationJobCreate(ingredients)
        // ③ 轮询任务状态直至终态或超上限
        const deadline = Date.now() + POLL_TOTAL_LIMIT_MS
        for (;;) {
          await sleep(POLL_INTERVAL_MS)
          if (Date.now() >= deadline) {
            // 轮询超上限：按超时错误走页面 error 态（可重试）
            throw { code: 'TIMEOUT', message: '生成超时，请重试' } as ApiError
          }
          const status = await getInnovationJob(job.job_id)
          if (status.status === 'succeeded') {
            // 成功：取完整创新菜谱（结构同同步 generate）
            this.current = status.recipe ?? null
            return
          }
          if (status.status === 'failed') {
            // 失败：归一为可重试的业务错误
            throw { code: 'GENERATION_FAILED', message: status.error || '生成失败，请重试' } as ApiError
          }
          if (status.status === 'blocked') {
            // 风控拦截：映射为 precheck 结构（ok/blocked/rule_id/message），复用页面拦截卡
            const issue = status.issues?.[0]
            this.precheck = {
              ok: false,
              blocked: true,
              rule_id: issue?.rule_id,
              message: issue?.message,
            }
            return
          }
          // pending / running：中间态，继续下一轮轮询
        }
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
