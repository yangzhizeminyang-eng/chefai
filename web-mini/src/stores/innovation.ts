/**
 * 文件职责：AI 创新菜状态（/v1/innovation/* 数据源；自 web-stage1/src/stores/innovation.ts
 * 逐行迁移，轮询实现等价抽离）。
 * - precheck → generate 主链路（M-01 异步任务化）：前端预检命中拦截时暂存 blocked
 *   信息（页面展示拦截话术卡）；通过后提交异步 job（POST /v1/innovation/jobs）并
 *   以 2.5s 间隔轮询任务状态（总上限 100s），与后端五态状态机对应：
 *   pending/running 继续等待 → succeeded 取 recipe 写入 current；failed 归一为
 *   GENERATION_FAILED 走 error 态；blocked 映射为 precheck 结构复用页面拦截卡；
 *   轮询超上限抛 TIMEOUT 走 error 态；
 * - current：当前生成的创新菜谱实体（含创新依据 / 营养 / 强制声明）；
 * - myRecipes：已采纳的「我的创新菜」（本次会话内存态，进入页面时可重拉）；
 * - generating：生成中标记（页面据此展示生成动画）。
 * 阶段二新增（平台适配，小程序页面 onHide 可暂停）：轮询由内联 for(;;) 循环抽离为
 * startPolling(jobId) / stopPolling()，对外行为（终态判定、状态写入、超时归一）与
 * 原实现一致；另导出 pausePolling() / resumePolling()——pause 清除定时器并记录暂停态、
 * resume 在轮询窗口内恢复调度（重新等待一个轮询间隔后继续），轮询 promise 保持挂起。
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
  InnovationJobStatusResponse,
  InnovationPrecheckResponse,
  InnovationRecipe,
} from '@shared/types'

/** 轮询间隔（毫秒）：与后端 job 状态机更新粒度对齐，可按环境调优 */
const POLL_INTERVAL_MS = 2500

/** 轮询总时长上限（毫秒）：100s 覆盖后端 25s LLM 硬超时 + 排队余量，可按环境调优 */
const POLL_TOTAL_LIMIT_MS = 100000

/* ── 轮询模块级状态（单例：同一时刻至多一个进行中的生成任务轮询） ── */

/** 轮询定时器句柄（null = 无待触发 tick） */
let pollTimer: ReturnType<typeof setTimeout> | null = null
/** 轮询中的任务 ID（null = 未在轮询） */
let pollJobId: string | null = null
/** 本轮轮询的截止时刻（毫秒时间戳；fake timers 单测下同样受控推进） */
let pollDeadline = 0
/** 暂停标记（pausePolling 置位、resumePolling 复位；暂停期间不调度下一轮 tick） */
let pollPaused = false
/** 轮询终态已结算标记（防重复 resolve / reject） */
let pollSettled = false
/** 轮询 promise 的 resolve 句柄（succeeded / blocked / stopPolling 时调用） */
let pollResolve: (() => void) | null = null
/** 轮询 promise 的 reject 句柄（failed / TIMEOUT / 查询异常时调用） */
let pollReject: ((err: ApiError) => void) | null = null

/** innovation store 实例类型（模块级轮询辅助函数入参用） */
type InnovationStore = ReturnType<typeof useInnovationStore>

/**
 * 结束轮询并清理模块级状态（终态处理与 stopPolling 共用的内部辅助）。
 * @returns 无
 */
function settlePolling(): void {
  pollSettled = true
  pollJobId = null
  if (pollTimer) {
    clearTimeout(pollTimer)
    pollTimer = null
  }
}

/**
 * 调度下一轮轮询 tick（内部辅助；暂停 / 已结算时不调度）。
 * @param store innovation store 实例（tick 内写状态用）
 * @returns 无
 */
function schedulePollTick(store: InnovationStore): void {
  if (pollPaused || pollSettled) return
  pollTimer = setTimeout(() => {
    void pollTick(store)
  }, POLL_INTERVAL_MS)
}

/**
 * 单轮轮询：超时判定 → 查询任务状态 → 终态分发（succeeded/failed/blocked）或继续调度。
 * @param store innovation store 实例
 * @returns 无
 * @throws 不抛出（异常路径经轮询 promise 的 reject 回传 generate 统一写 error 态）
 */
async function pollTick(store: InnovationStore): Promise<void> {
  if (pollSettled || pollPaused || !pollJobId) return
  if (Date.now() >= pollDeadline) {
    // 轮询超上限：按超时错误走页面 error 态（可重试）
    settlePolling()
    pollReject?.({ code: 'TIMEOUT', message: '生成超时，请重试' } as ApiError)
    pollReject = null
    return
  }
  let status: InnovationJobStatusResponse
  try {
    status = await getInnovationJob(pollJobId)
  } catch (e) {
    // 查询失败：按原语义终止轮询，错误交由 generate 统一写 error 态
    settlePolling()
    pollReject?.(e as ApiError)
    pollReject = null
    return
  }
  if (pollSettled) return
  if (status.status === 'succeeded') {
    // 成功：取完整创新菜谱（结构同同步 generate）
    store.current = status.recipe ?? null
    settlePolling()
    pollResolve?.()
    pollResolve = null
    return
  }
  if (status.status === 'failed') {
    // 失败：归一为可重试的业务错误
    settlePolling()
    pollReject?.({ code: 'GENERATION_FAILED', message: status.error || '生成失败，请重试' } as ApiError)
    pollReject = null
    return
  }
  if (status.status === 'blocked') {
    // 风控拦截：映射为 precheck 结构（ok/blocked/rule_id/message），复用页面拦截卡
    const issue = status.issues?.[0]
    store.precheck = {
      ok: false,
      blocked: true,
      rule_id: issue?.rule_id,
      message: issue?.message,
    }
    settlePolling()
    pollResolve?.()
    pollResolve = null
    return
  }
  // pending / running：中间态，继续下一轮轮询
  schedulePollTick(store)
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
     * ③ startPolling 轮询 GET /v1/innovation/jobs/{id}（2.5s 间隔、总上限 100s）：
     *    - succeeded → 取完整 recipe（含 is_ai_innovated / disclaimer）写入 current；
     *    - failed → 归一为 { code:'GENERATION_FAILED', message: error || 兜底文案 } 抛出；
     *    - blocked → 映射为 precheck 结构（页面复用拦截卡展示）后返回；
     *    - pending / running → 继续下一轮；
     *    - 超上限仍无终态 → 归一为 { code:'TIMEOUT', message:'生成超时，请重试' } 抛出。
     * 轮询间隔与总上限为模块常量可调（POLL_INTERVAL_MS / POLL_TOTAL_LIMIT_MS）。
     * @param ingredients 食材名列表（至少 1 项）
     * @returns 无
     * @throws 不抛出（failed / TIMEOUT / 查询异常统一写 error 态）
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
        // ③ 轮询任务状态直至终态或超上限（抽离为 startPolling，支持页面 onHide 暂停）
        await this.startPolling(job.job_id)
      } catch (e) {
        this.error = e as ApiError
      } finally {
        this.generating = false
      }
    },

    /**
     * 启动指定任务的轮询（阶段二抽离；generate 第 ③ 步内部调用，页面一般不直调）。
     * 返回的 promise 在终态（succeeded / blocked）时 resolve，failed / TIMEOUT /
     * 查询异常时 reject；pause 期间 promise 保持挂起，stopPolling 未终态时立即 resolve 收尾。
     * @param jobId 任务 ID（postInnovationJobCreate 返回）
     * @returns 轮询终态 promise（终态判定与状态写入在 pollTick 内完成）
     */
    startPolling(jobId: string): Promise<void> {
      // 清理上一次残留轮询（若有）：防双定时器并发（残留 promise 若存在会先被收尾）
      this.stopPolling()
      pollJobId = jobId
      pollDeadline = Date.now() + POLL_TOTAL_LIMIT_MS
      pollPaused = false
      pollSettled = false
      return new Promise<void>((resolve, reject) => {
        pollResolve = resolve
        pollReject = reject
        schedulePollTick(this)
      })
    },

    /**
     * 停止轮询并清理模块级状态（页面 onUnload / 放弃等待时调用）。
     * 未到终态时轮询 promise 以 resolve 收尾（generate 正常返回，无结果写入）。
     * @returns 无
     */
    stopPolling(): void {
      if (pollTimer) {
        clearTimeout(pollTimer)
        pollTimer = null
      }
      pollJobId = null
      pollPaused = false
      if (!pollSettled) {
        pollSettled = true
        pollResolve?.()
      }
      pollResolve = null
      pollReject = null
    },

    /**
     * 暂停轮询（页面 onHide 时调用）：清除待触发定时器并记录暂停态，
     * 不结算轮询 promise；已到终态 / 未在轮询时为无操作。
     * @returns 无
     */
    pausePolling(): void {
      if (pollSettled || !pollJobId) return
      pollPaused = true
      if (pollTimer) {
        clearTimeout(pollTimer)
        pollTimer = null
      }
    },

    /**
     * 恢复轮询（页面 onShow 时调用）：仅在处于暂停态且仍在轮询窗口内时生效，
     * 重新等待一个轮询间隔后继续查询；已结算 / 未暂停 / 未在轮询时为无操作。
     * @returns 无
     */
    resumePolling(): void {
      if (!pollPaused || pollSettled || !pollJobId) return
      pollPaused = false
      schedulePollTick(this)
    },

    /**
     * 采纳当前创新菜：入库「我的创新菜」（本地去重追加）。
     * @param recipe 要采纳的创新菜谱（缺省取 current）
     * @returns 是否采纳成功
     * @throws 接口失败时抛出归一化 ApiError（调用方提示）
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
     * @throws 不抛出（失败写 error 态并返回 false）
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
     * @throws 接口失败时抛出归一化 ApiError（调用方提示）
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
     * @throws 接口失败时抛出归一化 ApiError（调用方提示）
     */
    async sendFeedback(id: number, rating: number, comment?: string): Promise<void> {
      await postInnovationFeedback(id, { rating, comment })
    },

    /**
     * 清空当前生成结果（重新选择食材时调用，保留 myRecipes）。
     * @returns 无
     */
    resetCurrent(): void {
      this.current = null
      this.precheck = null
      this.error = null
    },
  },
})
