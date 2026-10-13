/**
 * 文件职责：家庭档案状态（/v1/profile/* 数据源；自 web-stage1/src/stores/profile.ts 逐行迁移）。
 * - family：家庭档案（成员列表 + 口味 + 过敏原）；skill：厨艺与设备；goal：饮食目标；
 * - loadAll()：三段并行拉取（任一失败互不影响，各自置空兜底）；
 * - 成员新增走 POST /v1/profile/members，编辑走 PUT /v1/profile/members/{id}，
 *   删除走 DELETE，动作成功后本地同步刷新列表；
 * - sensitiveConsented：首次填写过敏原的 PIPL 单独同意是否已落库（内存态，页面据此弹层）。
 * 历史修复保留（NEW-01，T8 复测发现）：档案的全部读写操作前必须先 ensureAnonReady
 * （确保匿名 ID 已懒获取），否则请求层不带 X-Anonymous-Id，后端会为该请求临时新建
 * 匿名用户——过敏原档案被挂到「孤儿用户」，后续推荐用另一匿名 ID 检索时查不到档案，
 * 过敏原布尔硬过滤失效（RL-6 回归风险）。
 * 平台差异（安全适配，文档 §10.2 PIPL 最小化）：
 * - sensitiveConsented 以 storage.ts 的 memSet/memGet 承载（纯内存态，不落明文），
 *   新增 markSensitiveConsented action 供页面写（直接赋值 state 亦不破坏行为）；
 * - 本 store 不向持久化存储写任何家庭成员明文（过敏原/健康目标仅存服务端与内存态）。
 */
import { defineStore } from 'pinia'
import {
  deleteFamilyMember,
  getDietGoal,
  getFamilyProfile,
  getSkillProfile,
  postFamilyMember,
  putDietGoal,
  putFamilyMember,
  putFamilyProfile,
  putSkillProfile,
} from '@/api/endpoints'
import type { ApiError, DietGoal, FamilyMember, FamilyProfile, SkillProfile } from '@shared/types'
import { memGet as storageMemGet, memSet as storageMemSet } from '@/utils/storage'
import { useSessionStore } from './session'

/** sensitiveConsented 内存态键（storage.ts memoryStore，不落明文） */
const SENSITIVE_CONSENT_MEM_KEY = 'profile_sensitive_consent'

/**
 * 确保匿名会话 ID 就绪（NEW-01 前置，函数）。
 * @returns 匿名 ID（后端不可用时为本地兜底 ID，流程不阻塞）
 * @throws 不抛出（ensureAnonymousId 内部失败走本地兜底）
 */
async function ensureAnonReady(): Promise<string> {
  return useSessionStore().ensureAnonymousId()
}

export const useProfileStore = defineStore('profile', {
  state: () => ({
    /** 家庭档案（null = 尚未加载） */
    family: null as FamilyProfile | null,
    /** 厨艺与设备档案（null = 尚未加载） */
    skill: null as SkillProfile | null,
    /** 饮食目标（null = 尚未加载） */
    goal: null as DietGoal | null,
    /** 档案加载中标记 */
    loading: false,
    /** 档案加载错误（归一化 ApiError） */
    error: null as ApiError | null,
    /** 保存中标记（成员增删改 / 整体保存共用） */
    saving: false,
    /** PIPL 过敏原敏感同意是否已落库（内存态，经 storage.ts memoryStore 承载，不落明文） */
    sensitiveConsented: storageMemGet<boolean>(SENSITIVE_CONSENT_MEM_KEY, false) === true,
  }),
  actions: {
    /**
     * 标记 PIPL 敏感同意已落库（阶段二新增平台适配：同步写内存态，跨页面/实例重建保持）。
     * @returns 无
     */
    markSensitiveConsented(): void {
      this.sensitiveConsented = true
      storageMemSet(SENSITIVE_CONSENT_MEM_KEY, true)
    },

    /**
     * 并行拉取家庭档案 / 厨艺设备 / 饮食目标（三段互不阻塞）。
     * @returns 无
     * @throws 不抛出（各段失败置空兜底，首段错误写入 error 三态）
     */
    async loadAll(): Promise<void> {
      // 匿名 ID 就绪先行（NEW-01）：避免读侧请求为空身份（GET family 无家庭会自动建档，防孤儿用户）
      await ensureAnonReady()
      this.loading = true
      this.error = null
      const results = await Promise.allSettled([
        getFamilyProfile(),
        getSkillProfile(),
        getDietGoal(),
      ])
      this.family = results[0].status === 'fulfilled' ? results[0].value : null
      this.skill = results[1].status === 'fulfilled' ? results[1].value : null
      this.goal = results[2].status === 'fulfilled' ? results[2].value : null
      // 任一段失败：以第一段错误归一呈现（页面走异常态 + 重试）
      const firstRejected = results.find((r) => r.status === 'rejected')
      this.error = firstRejected && firstRejected.status === 'rejected'
        ? firstRejected.reason as ApiError
        : null
      this.loading = false
    },

    /**
     * 新增家庭成员（POST /v1/profile/members），成功后本地追加。
     * @param member 新成员数据（无 id）
     * @returns 创建后的成员（含 id）
     * @throws 接口失败时抛出归一化 ApiError（调用方提示）
     */
    async addMember(member: Omit<FamilyMember, 'id'>): Promise<FamilyMember> {
      // 匿名 ID 就绪先行（NEW-01 / RL-6：过敏原必须挂在当前会话用户下，硬过滤才能立即生效）
      await ensureAnonReady()
      this.saving = true
      try {
        const created = await postFamilyMember(member)
        if (this.family) {
          this.family = { ...this.family, members: [...this.family.members, created] }
        }
        return created
      } finally {
        this.saving = false
      }
    },

    /**
     * 更新家庭成员（PUT /v1/profile/members/{id}），成功后本地替换。
     * @param member 完整成员数据（含 id）
     * @returns 更新后的成员
     * @throws 接口失败时抛出归一化 ApiError（调用方提示）
     */
    async updateMember(member: FamilyMember): Promise<FamilyMember> {
      // 匿名 ID 就绪先行（NEW-01：同 addMember，防孤儿用户）
      await ensureAnonReady()
      this.saving = true
      try {
        const updated = await putFamilyMember(member.id, member)
        if (this.family) {
          this.family = {
            ...this.family,
            members: this.family.members.map((m) => (m.id === updated.id ? updated : m)),
          }
        }
        return updated
      } finally {
        this.saving = false
      }
    },

    /**
     * 删除家庭成员（DELETE /v1/profile/members/{id}），成功后本地移除。
     * @param id 成员 ID
     * @returns 无
     * @throws 接口失败时抛出归一化 ApiError（调用方提示）
     */
    async removeMember(id: number): Promise<void> {
      // 匿名 ID 就绪先行（NEW-01：同 addMember，防孤儿用户）
      await ensureAnonReady()
      this.saving = true
      try {
        await deleteFamilyMember(id)
        if (this.family) {
          this.family = { ...this.family, members: this.family.members.filter((m) => m.id !== id) }
        }
      } finally {
        this.saving = false
      }
    },

    /**
     * 整体保存家庭档案（PUT /v1/profile/family，成员列表全量覆盖）。
     * @param name 家庭名称
     * @param members 全量成员列表
     * @returns 保存后的档案
     * @throws 接口失败时抛出归一化 ApiError（调用方提示）
     */
    async saveFamily(name: string, members: FamilyMember[]): Promise<FamilyProfile> {
      // 匿名 ID 就绪先行（NEW-01：同 addMember，防孤儿用户）
      await ensureAnonReady()
      this.saving = true
      try {
        const saved = await putFamilyProfile({ name, members })
        this.family = saved
        return saved
      } finally {
        this.saving = false
      }
    },

    /**
     * 保存厨艺与设备档案（PUT /v1/profile/skill）。
     * @param skill 厨艺等级与设备列表
     * @returns 保存后的档案
     * @throws 接口失败时抛出归一化 ApiError（调用方提示）
     */
    async saveSkill(skill: SkillProfile): Promise<SkillProfile> {
      // 匿名 ID 就绪先行（NEW-01：同 addMember，防孤儿用户）
      await ensureAnonReady()
      this.saving = true
      try {
        const saved = await putSkillProfile(skill)
        this.skill = saved
        return saved
      } finally {
        this.saving = false
      }
    },

    /**
     * 保存饮食目标（PUT /v1/profile/diet-goal）。
     * @param goal 目标与备注
     * @returns 保存后的目标
     * @throws 接口失败时抛出归一化 ApiError（调用方提示）
     */
    async saveGoal(goal: DietGoal): Promise<DietGoal> {
      // 匿名 ID 就绪先行（NEW-01：同 addMember，防孤儿用户）
      await ensureAnonReady()
      this.saving = true
      try {
        const saved = await putDietGoal(goal)
        this.goal = saved
        return saved
      } finally {
        this.saving = false
      }
    },
  },
})
