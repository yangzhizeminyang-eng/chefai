/**
 * 文件职责：匿名会话与免责同意状态（自 web-stage1/src/stores/session.ts 逐行迁移）。
 * - anonymous_id 懒获取（首次调用 API 需要时才请求 /v1/auth/anonymous）并经 storage.ts 持久化；
 * - disclaimerAgreed：免责声明是否已同意（本地记忆 disclaimer_agreed_v1=1）；
 * - agreeDisclaimer()：调 POST /v1/consent/disclaimer 落库，失败不阻塞（本地兜底记忆）。
 * 平台差异：原直接读写浏览器存储的 try/catch 兜底改由 @/utils/storage 封装承担
 * （storage.get/set 内部全捕获，异常静默降级，语义与原 safeGet/safeSet 一致）。
 */
import { defineStore } from 'pinia'
import { postAnonymous, postConsent } from '@/api/endpoints'
import { get as storageGet, set as storageSet, ANONYMOUS_ID_KEY } from '@/utils/storage'

/** 匿名 ID 持久化键（与请求层 X-Anonymous-Id 头数据源同键，受 LRU 淘汰白名单豁免保护） */
const ANON_KEY = ANONYMOUS_ID_KEY

/** 免责同意持久化键 */
const CONSENT_KEY = 'disclaimer_agreed_v1'

export const useSessionStore = defineStore('session', {
  state: () => ({
    /** 匿名用户 ID（懒获取，首次为空串；初始化时从本地存储恢复，读取失败兜底空串） */
    anonymousId: storageGet<string>(ANON_KEY, '') ?? '',
    /** 免责声明是否已同意（本地记忆 + 落库双轨） */
    disclaimerAgreed: storageGet<string>(CONSENT_KEY) === '1',
  }),
  actions: {
    /**
     * 懒获取匿名 ID：已存在直接返回；否则调 /v1/auth/anonymous 创建并持久化。
     * @returns 匿名 ID（接口失败时本地生成兜底 ID，保证前端流程不阻塞）
     * @throws 不抛出（接口失败走本地兜底 ID，存储写入失败由 storage 层静默降级）
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
      storageSet(ANON_KEY, this.anonymousId)
      return this.anonymousId
    },

    /**
     * 同意免责声明：调 POST /v1/consent/disclaimer 落库；
     * 无论落库成败都写本地记忆（失败不阻塞进入——本地兜底）。
     * @returns 无
     * @throws 不抛出（落库失败静默，仍以本地记忆放行）
     */
    async agreeDisclaimer(): Promise<void> {
      try {
        await postConsent('DISCLAIMER_V1')
      } catch {
        // 落库失败不阻塞：仍以本地记忆放行
      }
      this.disclaimerAgreed = true
      storageSet(CONSENT_KEY, '1')
    },
  },
})
