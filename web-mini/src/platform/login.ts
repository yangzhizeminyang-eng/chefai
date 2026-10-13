/**
 * 文件职责：微信登录平台适配——uni.login 取 code → 后端换令牌；任何失败静默降级匿名。
 * 降级口径（PRD-Q-5）：/v1/auth/wx-login 本期后端未实现（预期 404），
 * wxLogin() 绝不向用户抛错——失败返回 { ok: false, anonymous: true } 并附
 * LOGIN_FALLBACK_TEXT 文案（from '@shared/constants'），调用方负责 toast；
 * 成功把令牌持久化到 storage（aicook_session_token）。
 * 注：匿名数据合并（同 anonymous_id 的历史档案/库存归入正式账号）在后端完成，
 * 前端仅透传 merged 标记。
 */
import { LOGIN_FALLBACK_TEXT } from '@shared/constants'
import { postWxLogin } from '@/api/endpoints'
import { set as storageSet } from '@/utils/storage'

/** 会话令牌持久化键 */
export const SESSION_TOKEN_KEY = 'aicook_session_token'

/** 微信登录结果（ok=false 时调用方应降级为匿名会话，message 为可直投 toast 的文案） */
export interface WxLoginResult {
  /** 登录是否成功 */
  ok: boolean
  /** 会话令牌（成功时返回） */
  token?: string
  /** 是否合并了历史匿名数据（成功时返回；合并在后端完成） */
  merged?: boolean
  /** 是否降级为匿名（失败时恒 true） */
  anonymous?: boolean
  /** 失败提示文案（成功时缺省；失败时为 LOGIN_FALLBACK_TEXT） */
  message?: string
}

/**
 * 微信登录全流程：uni.login 取 code → postWxLogin 换令牌 → 持久化令牌。
 * 任何环节失败（uni.login 失败 / 接口 404 / 网络异常）均不抛错，返回降级结果。
 * @returns WxLoginResult：成功 { ok: true, token, merged }；失败 { ok: false, anonymous: true, message }
 * @throws 不抛出（内部全量 try/catch，登录失败永不阻断主流程）
 */
export async function wxLogin(): Promise<WxLoginResult> {
  try {
    const code = await new Promise<string>((resolve, reject) => {
      try {
        uni.login({
          provider: 'weixin',
          success: (res) => {
            if (res.code) resolve(res.code)
            else reject(new Error('login: empty code'))
          },
          fail: (err) => reject(new Error(err?.errMsg ?? 'login:fail')),
        })
      } catch (e) {
        reject(e instanceof Error ? e : new Error('login:sync-fail'))
      }
    })
    const resp = await postWxLogin(code)
    storageSet(SESSION_TOKEN_KEY, resp.token)
    return { ok: true, token: resp.token, merged: resp.merged }
  } catch {
    // 404（后端本期未实现）/ code 获取失败 / 网络异常：统一降级匿名，不向用户抛错
    return { ok: false, anonymous: true, message: LOGIN_FALLBACK_TEXT }
  }
}
