/**
 * 文件职责：登录注册账号状态（JWT 双轨身份的前端侧）。
 * - token / 用户信息持久化 localStorage（aicook_user_token / aicook_user_info）；
 * - register()：注册即绑定当前匿名身份（后端按 X-Anonymous-Id 头升级原 user 行，
 *   匿名期间的档案/库存/收藏数据按 user_id 自然延续，无需搬迁）；
 * - login()：登录已有账号，成功后把 session.anonymousId 切到账号自身的 anonymous_id，
 *   保证同浏览器切换账号时匿名头与 JWT 指向同一 user 行；
 * - logout()：清空登录态并换发全新匿名会话——避免登出后下一个使用者看到上一账号数据。
 */
import { defineStore } from 'pinia'
import { getAuthMe, postLogin, postRegister } from '@/api/endpoints'
import { USER_TOKEN_KEY } from '@/api'
import type { AuthResponse, MeInfoResponse } from '@/api/types'
import { useSessionStore } from '@/stores/session'

/** 用户信息持久化键 */
const USER_INFO_KEY = 'aicook_user_info'

/** 本地持久化的用户信息结构 */
interface StoredUserInfo {
  user_id: number
  username: string
  nickname: string | null
  anonymous_id: string
}

/**
 * 安全读取 localStorage（隐私模式等场景下可能抛异常）。
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
 */
function safeSet(key: string, value: string): void {
  try {
    localStorage.setItem(key, value)
  } catch {
    // 忽略持久化失败
  }
}

/**
 * 安全删除 localStorage 键。
 */
function safeRemove(key: string): void {
  try {
    localStorage.removeItem(key)
  } catch {
    // 忽略
  }
}

export const useAuthStore = defineStore('auth', {
  state: () => {
    let info: StoredUserInfo | null = null
    try {
      info = JSON.parse(safeGet(USER_INFO_KEY) ?? 'null') as StoredUserInfo | null
    } catch {
      info = null
    }
    return {
      /** JWT（空串 = 未登录） */
      token: safeGet(USER_TOKEN_KEY) ?? '',
      /** 当前登录用户信息（null = 未登录） */
      user: info,
    }
  },
  getters: {
    isLoggedIn: (state) => Boolean(state.token),
    /** 展示昵称（缺省回退用户名） */
    displayName: (state) => state.user?.nickname || state.user?.username || '',
  },
  actions: {
    /** 登录/注册成功后的统一落地：持久化 token + 用户信息，切换匿名头对齐账号 */
    applyAuth(res: AuthResponse): void {
      this.token = res.access_token
      this.user = {
        user_id: res.user_id,
        username: res.username,
        nickname: res.nickname,
        anonymous_id: res.anonymous_id,
      }
      safeSet(USER_TOKEN_KEY, res.access_token)
      safeSet(USER_INFO_KEY, JSON.stringify(this.user))
      // 匿名头与账号对齐：JWT 失效时（过期瞬间的个别请求）匿名头也指向同一账号
      const sessionStore = useSessionStore()
      sessionStore.anonymousId = res.anonymous_id
      safeSet('aicook_anonymous_id', res.anonymous_id)
    },

    /**
     * 注册：后端绑定当前匿名身份，历史数据延续。
     */
    async register(username: string, password: string, nickname?: string): Promise<void> {
      const sessionStore = useSessionStore()
      await sessionStore.ensureAnonymousId()
      const res = await postRegister(username, password, nickname)
      this.applyAuth(res)
    },

    /**
     * 登录已有账号。
     */
    async login(username: string, password: string): Promise<void> {
      const res = await postLogin(username, password)
      this.applyAuth(res)
    },

    /**
     * 拉取当前登录用户信息（校验 token 有效性）；失败按登出处理。
     */
    async fetchMe(): Promise<void> {
      if (!this.token) return
      try {
        const me = (await getAuthMe()) as MeInfoResponse
        this.user = {
          user_id: me.user_id,
          username: me.username,
          nickname: me.nickname,
          anonymous_id: me.anonymous_id,
        }
        safeSet(USER_INFO_KEY, JSON.stringify(this.user))
      } catch {
        this.logout()
      }
    },

    /**
     * 退出登录：清空 token/用户信息，并换发全新匿名会话，
     * 保证登出后同浏览器不再展示上一账号的档案/库存/收藏。
     */
    logout(): void {
      this.token = ''
      this.user = null
      safeRemove(USER_TOKEN_KEY)
      safeRemove(USER_INFO_KEY)
      const sessionStore = useSessionStore()
      sessionStore.anonymousId = ''
      safeSet('aicook_anonymous_id', '')
      // 换发新匿名会话（失败不阻塞：懒获取会在下次需要时兜底）
      void sessionStore.ensureAnonymousId()
    },
  },
})
