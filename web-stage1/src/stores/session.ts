/**
 * 文件职责：匿名会话与免责同意状态。
 * - anonymous_id 懒获取（首次调用 API 需要时才请求 /v1/auth/anonymous）并持久化 localStorage；
 * - disclaimerAgreed：免责声明是否已同意（localStorage 记忆 disclaimer_agreed_v1=1）；
 * - agreeDisclaimer()：调 POST /v1/consent/disclaimer 落库，失败不阻塞（本地兜底记忆）。
 */
import { defineStore } from 'pinia'
import { postAnonymous, postConsent } from '@/api/endpoints'

/** 匿名 ID 持久化键 */
const ANON_KEY = 'aicook_anonymous_id'
/** 免责同意持久化键 */
const CONSENT_KEY = 'disclaimer_agreed_v1'

/**
 * 安全读取 localStorage（隐私模式等场景下可能抛异常）。
 * @param key 键名
 * @returns 值或 null
 */
function safeGet(key: string): string | null {
  try {
    return localStorage.getItem(key)
  } catch {
    return null
  }
}

/**
 * 安全写 localStorage。
 * @param key 键名
 * @param value 值
 */
function safeSet(key: string, value: string): void {
  try {
    localStorage.setItem(key, value)
  } catch {
    // 忽略持久化失败
  }
}

export const useSessionStore = defineStore('session', {
  state: () => ({
    /** 匿名用户 ID（懒获取，首次为空串） */
    anonymousId: (safeGet(ANON_KEY) ?? '') as string,
    /** 免责声明是否已同意（本地记忆 + 落库双轨） */
    disclaimerAgreed: safeGet(CONSENT_KEY) === '1',
  }),
  actions: {
    /**
     * 懒获取匿名 ID：已存在直接返回；否则调 /v1/auth/anonymous 创建并持久化。
     * @returns 匿名 ID（接口失败时本地生成兜底 ID，保证前端流程不阻塞）
     */
    async ensureAnonymousId(): Promise<string> {
      if (this.anonymousId) return this.anonymousId
      try {
        const res = await postAnonymous()
        this.anonymousId = res.anonymous_id
      } catch {
        // 后端不可用：本地生成兜底 ID（前端演示不依赖后端存活）
        this.anonymousId = `anon_local_${Date.now().toString(36)}${Math.random().toString(36).slice(2, 6)}`
      }
      safeSet(ANON_KEY, this.anonymousId)
      return this.anonymousId
    },

    /**
     * 同意免责声明：调 POST /v1/consent/disclaimer 落库；
     * 无论落库成败都写本地记忆（失败不阻塞进入——本地兜底）。
     */
    async agreeDisclaimer(): Promise<void> {
      try {
        await postConsent('DISCLAIMER_V1')
      } catch {
        // 落库失败不阻塞：仍以本地记忆放行
      }
      this.disclaimerAgreed = true
      safeSet(CONSENT_KEY, '1')
    },
  },
})
