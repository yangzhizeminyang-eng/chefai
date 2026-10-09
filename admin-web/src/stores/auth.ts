/**
 * 文件职责：登录态全局状态（token / 角色 / 用户名）。
 * - 持久化到 localStorage，刷新页面不丢失；
 * - 提供只读角色判断与写操作统一拦截提示。
 */
import { computed, ref } from 'vue'
import { defineStore } from 'pinia'
import { ElMessage } from 'element-plus'

import { ROLE_KEY, TOKEN_KEY, USERNAME_KEY, login as loginApi } from '@/api/admin'
import type { AdminRole } from '@/api/admin'

export const useAuthStore = defineStore('auth', () => {
  /** 登录令牌（初始化自 localStorage） */
  const token = ref<string>(localStorage.getItem(TOKEN_KEY) ?? '')
  /** 当前角色（localStorage 无记录时按只读兜底，实际以接口返回为准） */
  const role = ref<AdminRole>((localStorage.getItem(ROLE_KEY) as AdminRole | null) ?? 'readonly')
  /** 当前用户名 */
  const username = ref<string>(localStorage.getItem(USERNAME_KEY) ?? '')

  /** 是否只读角色（写操作入口可见但点击被拦截提示） */
  const isReadonly = computed<boolean>(() => role.value === 'readonly')
  /** 是否超级管理员 */
  const isSuperAdmin = computed<boolean>(() => role.value === 'super_admin')

  /**
   * 登录并持久化登录态。
   * @param name 用户名
   * @param password 密码
   * @throws 登录接口失败时抛出原始错误（调用方负责提示）
   */
  async function login(name: string, password: string): Promise<void> {
    const result = await loginApi({ username: name, password })
    token.value = result.access_token
    role.value = result.role
    username.value = result.username
    localStorage.setItem(TOKEN_KEY, result.access_token)
    localStorage.setItem(ROLE_KEY, result.role)
    localStorage.setItem(USERNAME_KEY, result.username)
  }

  /** 退出登录并清理本地登录态 */
  function logout(): void {
    token.value = ''
    role.value = 'readonly'
    username.value = ''
    localStorage.removeItem(TOKEN_KEY)
    localStorage.removeItem(ROLE_KEY)
    localStorage.removeItem(USERNAME_KEY)
  }

  /**
   * 写操作统一守卫：只读角色弹出提示并拦截。
   * @returns 允许继续执行写操作返回 true
   */
  function ensureWritable(): boolean {
    if (isReadonly.value) {
      ElMessage.warning('当前为只读角色，仅可查看数据，无法执行写操作')
      return false
    }
    return true
  }

  return { token, role, username, isReadonly, isSuperAdmin, login, logout, ensureWritable }
})
