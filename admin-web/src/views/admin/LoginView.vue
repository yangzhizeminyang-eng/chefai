<!-- 文件职责：后台登录页。表单校验通过后调用 auth store 登录，token 持久化至 localStorage 后进入看板。 -->
<script setup lang="ts">
/**
 * 登录页逻辑：用户名 / 密码校验 → 登录接口 → 跳转看板；失败展示后端 message。
 */
import { reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import type { FormInstance, FormRules } from 'element-plus'
import { ElMessage } from 'element-plus'

import { notifyApiError } from '@/api/admin'
import { useAuthStore } from '@/stores/auth'

const router = useRouter()
const auth = useAuthStore()

/** 登录表单数据 */
const form = reactive({
  username: '',
  password: '',
})
/** 表单引用（用于触发校验） */
const formRef = ref<FormInstance>()
/** 登录请求进行中标记 */
const loading = ref(false)

/** 表单校验规则 */
const rules: FormRules = {
  username: [{ required: true, message: '请输入用户名', trigger: 'blur' }],
  password: [{ required: true, message: '请输入密码', trigger: 'blur' }],
}

/**
 * 提交登录：校验通过后调用 store 登录，成功后跳转看板。
 */
async function handleLogin(): Promise<void> {
  const valid = await formRef.value?.validate().then(() => true).catch(() => false)
  if (!valid) return
  loading.value = true
  try {
    await auth.login(form.username, form.password)
    ElMessage.success('登录成功')
    router.push('/')
  } catch (e) {
    notifyApiError(e, '登录失败，请检查用户名或密码')
  } finally {
    loading.value = false
  }
}
</script>

<template>
  <div class="login-page">
    <el-card class="login-card" shadow="always">
      <div class="login-title">
        <h1>AI 厨娘 · 后台管理</h1>
        <p class="muted">请使用管理员账号登录</p>
      </div>
      <el-form ref="formRef" :model="form" :rules="rules" label-position="top" size="large" @keyup.enter="handleLogin">
        <el-form-item label="用户名" prop="username">
          <el-input v-model="form.username" placeholder="用户名" clearable autocomplete="username" />
        </el-form-item>
        <el-form-item label="密码" prop="password">
          <el-input v-model="form.password" type="password" show-password placeholder="密码" autocomplete="current-password" />
        </el-form-item>
        <el-button type="primary" class="login-btn" :loading="loading" @click="handleLogin">登 录</el-button>
      </el-form>
    </el-card>
  </div>
</template>

<style scoped>
.login-page {
  height: 100%;
  display: flex;
  align-items: center;
  justify-content: center;
  background: linear-gradient(135deg, var(--el-color-primary-light-9), var(--el-color-primary-light-5));
}

.login-card {
  width: 380px;
  padding: 8px 12px;
}

.login-title h1 {
  font-size: 20px;
  margin: 0 0 4px;
  text-align: center;
}

.login-title p {
  text-align: center;
  margin: 0 0 16px;
}

.login-btn {
  width: 100%;
  margin-top: 4px;
}
</style>
