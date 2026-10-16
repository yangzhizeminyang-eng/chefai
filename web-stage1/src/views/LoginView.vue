<script setup lang="ts">
/**
 * 视图职责：登录/注册页（路由 /login，账号管理入口）。
 * - 双 Tab：登录（用户名+密码）/ 注册（用户名+密码+可选昵称）；
 * - 注册自动绑定当前浏览器匿名身份：匿名期间产生的家庭档案/冰箱/收藏等数据
 *   按账号延续（后端升级原 user 行，不搬迁）；
 * - 成功后回跳来源页（route.query.redirect）或首页。
 */
import { reactive, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import type { FormInstance, FormRules } from 'element-plus'
import type { ApiError } from '@/api/types'
import { useAuthStore } from '@/stores/auth'

const route = useRoute()
const router = useRouter()
const authStore = useAuthStore()

/** 当前激活 Tab：login / register */
const activeTab = ref<'login' | 'register'>('login')
/** 提交中状态（防重复点击） */
const submitting = ref(false)

/** 登录表单 */
const loginFormRef = ref<FormInstance>()
const loginForm = reactive({ username: '', password: '' })
const loginRules: FormRules = {
  username: [{ required: true, message: '请输入用户名', trigger: 'blur' }],
  password: [{ required: true, message: '请输入密码', trigger: 'blur' }],
}

/** 注册表单 */
const registerFormRef = ref<FormInstance>()
const registerForm = reactive({ username: '', password: '', confirm: '', nickname: '' })
const registerRules: FormRules = {
  username: [
    { required: true, message: '请输入用户名', trigger: 'blur' },
    { min: 3, max: 30, message: '用户名 3~30 个字符', trigger: 'blur' },
  ],
  password: [
    { required: true, message: '请输入密码', trigger: 'blur' },
    { min: 6, max: 64, message: '密码至少 6 位', trigger: 'blur' },
  ],
  confirm: [
    {
      validator: (_rule, value: string, callback) => {
        if (value !== registerForm.password) callback(new Error('两次输入的密码不一致'))
        else callback()
      },
      trigger: 'blur',
    },
  ],
}

/** 提取后端归一错误文案 */
function errMessage(err: unknown): string {
  const e = err as ApiError
  return e?.message || '操作失败，请重试'
}

/** 登录提交 */
async function onLogin(): Promise<void> {
  const form = loginFormRef.value
  if (!form || submitting.value) return
  const valid = await form.validate().catch(() => false)
  if (!valid) return
  submitting.value = true
  try {
    await authStore.login(loginForm.username.trim(), loginForm.password)
    ElMessage.success('登录成功')
    redirectAfterAuth()
  } catch (err) {
    ElMessage.error(errMessage(err))
  } finally {
    submitting.value = false
  }
}

/** 注册提交 */
async function onRegister(): Promise<void> {
  const form = registerFormRef.value
  if (!form || submitting.value) return
  const valid = await form.validate().catch(() => false)
  if (!valid) return
  submitting.value = true
  try {
    await authStore.register(registerForm.username.trim(), registerForm.password,
      registerForm.nickname.trim() || undefined)
    ElMessage.success('注册成功，数据已迁移至你的账号')
    redirectAfterAuth()
  } catch (err) {
    ElMessage.error(errMessage(err))
  } finally {
    submitting.value = false
  }
}

/** 认证成功后回跳：来源页优先，缺省首页 */
function redirectAfterAuth(): void {
  const redirect = typeof route.query.redirect === 'string' ? route.query.redirect : '/'
  void router.replace(redirect.startsWith('/') ? redirect : '/')
}
</script>

<template>
  <div class="login-page">
    <div class="login-card">
      <div class="login-brand">🍳 AI 厨娘・智能烹饪助手</div>
      <p class="login-sub">登录后你的家庭档案、冰箱、收藏与烹饪历史将独立保存</p>

      <el-tabs v-model="activeTab" stretch>
        <el-tab-pane label="登录" name="login">
          <el-form
            ref="loginFormRef"
            :model="loginForm"
            :rules="loginRules"
            label-position="top"
            size="large"
            @keyup.enter="onLogin"
          >
            <el-form-item label="用户名" prop="username">
              <el-input v-model="loginForm.username" placeholder="请输入用户名" autocomplete="username" />
            </el-form-item>
            <el-form-item label="密码" prop="password">
              <el-input
                v-model="loginForm.password"
                type="password"
                show-password
                placeholder="请输入密码"
                autocomplete="current-password"
              />
            </el-form-item>
            <el-button
              class="login-submit"
              type="primary"
              size="large"
              :loading="submitting"
              @click="onLogin"
            >
              登录
            </el-button>
          </el-form>
        </el-tab-pane>

        <el-tab-pane label="注册" name="register">
          <el-form
            ref="registerFormRef"
            :model="registerForm"
            :rules="registerRules"
            label-position="top"
            size="large"
            @keyup.enter="onRegister"
          >
            <el-form-item label="用户名" prop="username">
              <el-input v-model="registerForm.username" placeholder="3~30 个字符" autocomplete="username" />
            </el-form-item>
            <el-form-item label="昵称（可选）" prop="nickname">
              <el-input v-model="registerForm.nickname" placeholder="不填默认使用用户名" maxlength="50" />
            </el-form-item>
            <el-form-item label="密码" prop="password">
              <el-input
                v-model="registerForm.password"
                type="password"
                show-password
                placeholder="至少 6 位"
                autocomplete="new-password"
              />
            </el-form-item>
            <el-form-item label="确认密码" prop="confirm">
              <el-input
                v-model="registerForm.confirm"
                type="password"
                show-password
                placeholder="再次输入密码"
                autocomplete="new-password"
              />
            </el-form-item>
            <el-button
              class="login-submit"
              type="primary"
              size="large"
              :loading="submitting"
              @click="onRegister"
            >
              注册并进入
            </el-button>
            <p class="login-hint">注册将自动继承当前浏览器内的临时数据（档案、冰箱、收藏等）</p>
          </el-form>
        </el-tab-pane>
      </el-tabs>
    </div>
  </div>
</template>

<style scoped>
.login-page {
  display: flex;
  align-items: center;
  justify-content: center;
  min-height: calc(100vh - var(--header-height) - 68px);
}

.login-card {
  width: 100%;
  max-width: 420px;
  padding: 28px 28px 20px;
  border-radius: 14px;
  background: var(--card-bg);
  border: 1px solid var(--color-info-border);
  box-shadow: 0 8px 28px rgba(0, 0, 0, 0.08);
}

.login-brand {
  font-size: var(--font-lg);
  font-weight: 700;
  text-align: center;
}

.login-sub {
  margin: 8px 0 4px;
  font-size: var(--font-sm);
  color: var(--color-info);
  text-align: center;
}

.login-submit {
  width: 100%;
  margin-top: 4px;
}

.login-hint {
  margin: 10px 0 0;
  font-size: var(--font-xs, 12px);
  color: var(--color-info);
  text-align: center;
}
</style>
