/**
 * 文件职责：烹饪会话状态（W-04 分步引导数据源；自 web-stage1/src/stores/cooking.ts 逐行迁移）。
 * - session：后端会话实体（id/recipe_id/servings/current_step_no/status/allergen_conflict）；
 * - steps：本地步骤索引（菜谱步骤快照，切换纯本地 ≤300ms 不走网络）；
 * - restore：进入会话时恢复（后端 PATCH 断点 + 本地缓存双轨）；
 * - next/prev：本地切换步骤 + PATCH 持久化（静默失败不阻塞切换）。
 * 平台差异：原浏览器存储读写（含 JSON 手动序列化）统一改由 @/utils/storage 承担
 * （set 内部 JSON 序列化、get 内部反序列化并全捕获异常），键名前缀保持源码一致；
 * 断点续做缓存数据为会话实体 / 步骤快照（非敏感数据），可落持久化存储。
 */
import { defineStore } from 'pinia'
import { createCookingSession, patchCookingSession } from '@/api/endpoints'
import type { ApiError, CookingSession, RecipeStep } from '@shared/types'
import { get as storageGet, set as storageSet, remove as storageRemove } from '@/utils/storage'

/** 本地缓存键前缀（key = cook_steps_{sessionId}） */
const LOCAL_CACHE_PREFIX = 'cook_steps_'

/** 会话实体本地缓存键前缀（key = cook_session_{sessionId}，断点续做用） */
const SESSION_CACHE_PREFIX = 'cook_session_'

/** 步骤缓存条目结构（步骤快照 + 步骤游标 + 基准份数） */
interface StepCacheEntry {
  /** 菜谱步骤快照 */
  steps?: RecipeStep[]
  /** 步骤游标（1 起） */
  step_no?: number
  /** 菜谱基准份数（步骤用量提示缩放分母） */
  base_servings?: number
}

/** 步骤推进 PATCH 防抖窗口（毫秒）：800ms 内多次本地切换只发一次静默 PATCH */
const PERSIST_DEBOUNCE_MS = 800

/** 防抖定时器句柄（模块级单例，同一时刻只有一个进行中的会话） */
let persistTimer: ReturnType<typeof setTimeout> | null = null

export const useCookingStore = defineStore('cooking', {
  state: () => ({
    /** 当前烹饪会话（null = 无进行中会话） */
    session: null as CookingSession | null,
    /** 本地步骤快照（restore 时从菜谱数据写入；步骤切换只读此数组） */
    steps: [] as RecipeStep[],
    /** 菜谱基准份数（步骤用量提示缩放分母；会话份数 / 基准份数 = 缩放系数） */
    baseServings: 1,
    /** 会话创建/恢复请求进行中标记 */
    loading: false,
    /** 创建/恢复错误（归一化 ApiError） */
    error: null as ApiError | null,
  }),
  getters: {
    /**
     * 当前步骤序号（1 起；无会话为 0）。
     * @returns 序号
     */
    currentStepNo: (state): number => state.session?.current_step_no ?? 0,
    /**
     * 步骤总数。
     * @returns 总数
     */
    totalSteps: (state): number => state.steps.length,
    /**
     * 当前步骤对象（无则 null）。
     * @returns 当前步骤
     */
    currentStep: (state): RecipeStep | null =>
      state.session ? (state.steps[state.session.current_step_no - 1] ?? null) : null,
  },
  actions: {
    /**
     * 创建烹饪会话（POST /v1/cooking/sessions）并写入本地步骤快照。
     * @param recipeId 菜谱 ID
     * @param servings 份数
     * @param steps 菜谱步骤列表（详情页已加载，直接快照避免重复请求）
     * @param baseServings 菜谱基准份数（步骤用量提示缩放分母，可缺省按 servings 兜底）
     * @returns 创建的会话
     * @throws 创建失败时抛出归一化 ApiError（调用方提示，error 态同步写入）
     */
    async startSession(
      recipeId: number,
      servings: number,
      steps: RecipeStep[],
      baseServings?: number,
    ): Promise<CookingSession> {
      this.loading = true
      this.error = null
      try {
        const session = await createCookingSession({ recipe_id: recipeId, servings })
        this.session = session
        this.steps = steps
        // 基准份数：非法/缺省时以会话份数兜底（缩放系数 = 1，不会误缩放）
        this.baseServings = baseServings && baseServings >= 1 ? baseServings : servings
        // 本地缓存步骤（重进时断点续做兜底）；基准份数随步骤缓存一并持久化
        storageSet(`${LOCAL_CACHE_PREFIX}${session.id}`, {
          steps,
          step_no: session.current_step_no,
          base_servings: this.baseServings,
        })
        // 会话实体也入缓存（重进后 Pinia 内存态丢失，从本地存储恢复会话）
        this.writeLocalSession()
        return session
      } catch (e) {
        this.error = e as ApiError
        throw e
      } finally {
        this.loading = false
      }
    },

    /**
     * 恢复会话（重进断点续做）：本地缓存优先取步骤快照，step_no 以会话实体为准。
     * @param session 已从后端取回（或由详情页传入）的会话实体
     * @param fallbackSteps 本地缓存缺失时使用的步骤兜底（详情页数据）
     * @param fallbackBaseServings 基准份数兜底（缓存缺失时用，缺省以会话份数兜底）
     * @returns 无
     */
    restore(session: CookingSession, fallbackSteps: RecipeStep[] = [], fallbackBaseServings?: number): void {
      this.session = session
      /** 基准份数兜底值（缓存缺失时不误缩放：以会话份数兜底 → 缩放系数 1） */
      const baseFallback = fallbackBaseServings ?? session.servings ?? 1
      const cached = storageGet<StepCacheEntry | null>(`${LOCAL_CACHE_PREFIX}${session.id}`)
      if (cached) {
        this.steps = cached.steps ?? fallbackSteps
        this.baseServings =
          cached.base_servings && cached.base_servings >= 1 ? cached.base_servings : baseFallback
      } else {
        this.steps = fallbackSteps
        this.baseServings = baseFallback
      }
    },

    /**
     * 下一步（本地切换 ≤300ms 不走网络；PATCH 以 800ms 防抖静默持久化断点）。
     * @returns 无
     */
    async next(): Promise<void> {
      if (!this.session) return
      // 边界：已是最后一步则不推进
      if (this.session.current_step_no >= this.steps.length) return
      this.session.current_step_no += 1
      this.schedulePersist()
    },

    /**
     * 上一步（本地切换；第一步不回退；PATCH 以 800ms 防抖静默持久化断点）。
     * @returns 无
     */
    async prev(): Promise<void> {
      if (!this.session) return
      // 边界：已是第一步则不回退
      if (this.session.current_step_no <= 1) return
      this.session.current_step_no -= 1
      this.schedulePersist()
    },

    /**
     * 跳转到指定步骤（步骤列表抽屉用；本地切换 + 防抖持久化）。
     * @param no 目标步骤序号（1 起，越界自动收敛）
     * @returns 无
     */
    async jumpTo(no: number): Promise<void> {
      if (!this.session) return
      // 收敛到合法区间 [1, steps.length]
      const clamped = Math.min(Math.max(no, 1), this.steps.length || 1)
      this.session.current_step_no = clamped
      this.schedulePersist()
    },

    /**
     * 防抖持久化：立即写本地双缓存，800ms 内多次切换合并为一次静默 PATCH。
     * 步骤切换本身纯本地（≤300ms），网络持久化不阻塞交互。
     * @returns 无
     */
    schedulePersist(): void {
      this.writeLocalStepNo()
      this.writeLocalSession()
      if (persistTimer) clearTimeout(persistTimer)
      persistTimer = setTimeout(() => {
        persistTimer = null
        void this.persistStep()
      }, PERSIST_DEBOUNCE_MS)
    },

    /**
     * 将会话实体写入本地缓存 cook_session_{id}（断点续做恢复数据源之一）。
     * @returns 无
     */
    writeLocalSession(): void {
      if (!this.session) return
      storageSet(`${SESSION_CACHE_PREFIX}${this.session.id}`, this.session)
    },

    /**
     * 按会话 ID 恢复（W-04 断点续做入口）。
     * 恢复策略：① 内存 store 已是同会话且有步骤 → 直接复用（最快）；
     * ② 读本地缓存 cook_session_{id}（会话实体）+ cook_steps_{id}（步骤快照）恢复；
     * ③ 都无 → 返回 false（endpoints 无「查询会话」GET 接口，不做远端兜底，
     *    由页面提示并引导回选食材页重新发起）。
     * @param sessionId 路由中的会话 ID
     * @returns 是否恢复成功
     */
    restoreById(sessionId: string): boolean {
      // 策略①：内存命中
      if (this.session?.id === sessionId && this.steps.length > 0) return true
      // 策略②：本地缓存命中（storage.get 解析失败返回 undefined，缓存损坏自然走未恢复分支）
      const cached = storageGet<CookingSession | null>(`${SESSION_CACHE_PREFIX}${sessionId}`)
      if (!cached) return false
      try {
        const session = cached
        let steps: RecipeStep[] = []
        let baseServings = session.servings ?? 1
        const stepCache = storageGet<StepCacheEntry | null>(`${LOCAL_CACHE_PREFIX}${sessionId}`)
        if (stepCache) {
          steps = stepCache.steps ?? []
          // 基准份数随步骤缓存恢复；旧缓存无该字段时以会话份数兜底（缩放系数 1，不误缩放）
          baseServings =
            stepCache.base_servings && stepCache.base_servings >= 1 ? stepCache.base_servings : baseServings
        }
        this.restore(session, steps, baseServings)
        return true
      } catch {
        // 缓存损坏视为未恢复
        return false
      }
    },

    /**
     * 清理会话：删除本地双缓存（cook_session_{id} / cook_steps_{id}）并重置 store。
     * 做菜完成或用户放弃时调用。
     * @returns 无
     */
    clearSession(): void {
      if (this.session) {
        storageRemove(`${SESSION_CACHE_PREFIX}${this.session.id}`)
        storageRemove(`${LOCAL_CACHE_PREFIX}${this.session.id}`)
      }
      if (persistTimer) {
        clearTimeout(persistTimer)
        persistTimer = null
      }
      this.session = null
      this.steps = []
      this.baseServings = 1
    },

    /**
     * PATCH 持久化当前步骤（静默失败：本地状态已更新，不阻塞烹饪流程）。
     * @returns 无
     * @throws 不抛出（断点持久化失败静默，以本地状态为准，下次切换再试）
     */
    async persistStep(): Promise<void> {
      if (!this.session) return
      try {
        await patchCookingSession(this.session.id, { current_step_no: this.session.current_step_no })
      } catch {
        // 断点持久化失败不阻塞：以本地状态为准，下次切换再试
      }
    },

    /**
     * 写本地步骤号缓存（重进兜底）。
     * @returns 无
     */
    writeLocalStepNo(): void {
      if (!this.session) return
      const key = `${LOCAL_CACHE_PREFIX}${this.session.id}`
      const parsed = storageGet<StepCacheEntry | null>(key)
      if (parsed) {
        parsed.step_no = this.session.current_step_no
        storageSet(key, parsed)
      }
    },
  },
})
