<script setup lang="ts">
/**
 * 视图职责：登录/注册页（路由 /login，账号管理入口）。
 * - 双 Tab：登录（用户名+密码）/ 注册（用户名+密码+可选昵称）；
 * - 注册自动绑定当前浏览器匿名身份：匿名期间产生的家庭档案/冰箱/收藏等数据
 *   按账号延续（后端升级原 user 行，不搬迁）；
 * - 成功后回跳来源页（route.query.redirect）或首页。
 */
import { onBeforeUnmount, onMounted, reactive, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import type { FormInstance, FormRules } from 'element-plus'
import type { ApiError } from '@/api/types'
import { useAuthStore } from '@/stores/auth'
import { ArrowRight, Dish } from '@element-plus/icons-vue'

const route = useRoute()
const router = useRouter()
const authStore = useAuthStore()

const loginPage = ref<HTMLElement>()
const visualOffset = ref({ x: 0, y: 0 })
const activeFoodDetail = ref<'salt' | 'scallion' | 'chili' | null>(null)
const loginHovered = ref(false)
const captionTyping = ref(false)
let pointerFrame = 0
let captionFrame = 0

function resetVisualOffset(): void {
  if (pointerFrame) cancelAnimationFrame(pointerFrame)
  pointerFrame = 0
  visualOffset.value = { x: 0, y: 0 }
}

function setLoginHover(hovered: boolean): void {
  if (window.matchMedia('(hover: hover) and (pointer: fine)').matches) {
    loginHovered.value = hovered
  }
}

function onPagePointerMove(event: PointerEvent): void {
  if (window.matchMedia('(max-width: 780px), (pointer: coarse), (prefers-reduced-motion: reduce)').matches) return
  if (event.target instanceof Element && event.target.closest('.login-visual__micro-zone')) {
    resetVisualOffset()
    return
  }
  if (pointerFrame) cancelAnimationFrame(pointerFrame)
  pointerFrame = requestAnimationFrame(() => {
    const bounds = loginPage.value?.getBoundingClientRect()
    if (!bounds) return
    visualOffset.value = {
      x: Math.max(-5, Math.min(5, ((event.clientX - bounds.left) / bounds.width - 0.5) * 10)),
      y: Math.max(-5, Math.min(5, ((event.clientY - bounds.top) / bounds.height - 0.5) * 10)),
    }
    pointerFrame = 0
  })
}

onBeforeUnmount(resetVisualOffset)

onMounted(() => {
  captionFrame = requestAnimationFrame(() => {
    captionTyping.value = true
    captionFrame = 0
  })
})

onBeforeUnmount(() => {
  if (captionFrame) cancelAnimationFrame(captionFrame)
})

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
  <div ref="loginPage" class="login-page" @pointermove="onPagePointerMove" @pointerleave="resetVisualOffset">
    <div class="login-shell">
      <header class="login-topbar">
        <router-link class="login-brand" to="/login" aria-label="AI 厨娘">
          <el-icon class="login-brand__mark" aria-hidden="true"><Dish /></el-icon>
          <span>AI 厨娘</span>
        </router-link>
      </header>

      <div class="login-content">
        <section class="login-form-panel" aria-labelledby="login-title">
        <div class="login-form-heading">
          <p class="login-form-heading__eyebrow">欢迎回家</p>
          <h1 id="login-title" class="login-title">{{ activeTab === 'login' ? '登录你的厨房' : '创建家庭账号' }}</h1>
          <p>登录后继续管理你的家庭饮食与菜谱</p>
        </div>

      <el-tabs v-model="activeTab" stretch class="login-tabs">
        <el-tab-pane label="登录" name="login">
          <el-form
            ref="loginFormRef"
            :model="loginForm"
            :rules="loginRules"
            class="login-form login-form--login"
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
              :class="{ 'login-submit--warm': loginHovered && !submitting }"
              :aria-label="submitting ? '正在登录' : '登录并继续'"
              @pointerenter="setLoginHover(true)"
              @pointerleave="setLoginHover(false)"
              @click="onLogin"
            >
              <span class="login-submit__labels" aria-hidden="true">
                <span class="login-submit__label login-submit__label--default">登录并继续</span>
                <span class="login-submit__label login-submit__label--warm">开饭咯</span>
              </span>
              <el-icon class="login-submit__arrow" aria-hidden="true"><ArrowRight /></el-icon>
              <span class="login-submit__rice" aria-hidden="true">🍚</span>
            </el-button>
          </el-form>
        </el-tab-pane>

        <el-tab-pane label="注册" name="register">
          <el-form
            ref="registerFormRef"
            :model="registerForm"
            :rules="registerRules"
            class="login-form login-form--register"
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
              创建账号并进入 <el-icon><ArrowRight /></el-icon>
            </el-button>
            <p class="login-hint">注册将自动继承当前浏览器内的临时数据（档案、冰箱、收藏等）</p>
          </el-form>
        </el-tab-pane>
      </el-tabs>
      <p class="login-privacy">你的家庭资料和烹饪记录仅保存在你的账号中</p>
        </section>

        <aside
          class="login-visual"
          :data-active-food="activeFoodDetail || undefined"
          :style="{ '--visual-x': `${visualOffset.x}px`, '--visual-y': `${visualOffset.y}px` }"
          aria-label="正在备菜的家庭厨房"
        >
          <img
            class="login-visual__image"
            src="/images/login-prep-scene.webp"
            alt="一双手在木砧板上整理香葱，旁边摆着香菜、辣椒与八角"
            width="1024"
            height="1024"
            decoding="async"
            fetchpriority="high"
          />
          <img
            class="login-visual__micro-image login-visual__micro-image--salt"
            src="/images/login-prep-scene.webp"
            alt=""
            aria-hidden="true"
            width="1024"
            height="1024"
            decoding="async"
          />
          <img
            class="login-visual__micro-image login-visual__micro-image--scallion"
            src="/images/login-prep-scene.webp"
            alt=""
            aria-hidden="true"
            width="1024"
            height="1024"
            decoding="async"
          />
          <img
            class="login-visual__micro-image login-visual__micro-image--chili"
            src="/images/login-prep-scene.webp"
            alt=""
            aria-hidden="true"
            width="1024"
            height="1024"
            decoding="async"
          />
          <span
            class="login-visual__micro-zone login-visual__micro-zone--salt"
            aria-hidden="true"
            @pointerenter="activeFoodDetail = 'salt'"
            @pointerleave="activeFoodDetail = null"
          />
          <span
            class="login-visual__micro-zone login-visual__micro-zone--scallion"
            aria-hidden="true"
            @pointerenter="activeFoodDetail = 'scallion'"
            @pointerleave="activeFoodDetail = null"
          />
          <span
            class="login-visual__micro-zone login-visual__micro-zone--chili"
            aria-hidden="true"
            @pointerenter="activeFoodDetail = 'chili'"
            @pointerleave="activeFoodDetail = null"
          />
          <span
            v-if="activeFoodDetail"
            class="login-visual__food-tip"
            role="status"
          >
            {{ activeFoodDetail === 'salt' ? '加一点点盐' : activeFoodDetail === 'chili' ? '切两个提香' : '最后撒一把' }}
          </span>
          <p class="login-visual__caption" :class="{ 'login-visual__caption--typing': captionTyping }">
            <span class="login-visual__caption-line">从手边的食材，</span>
            <span class="login-visual__caption-line">找到今天的那道菜。</span>
          </p>
        </aside>
      </div>
    </div>
  </div>
</template>

<style scoped>
.login-page {
  --login-countertop: #f5f0e8;
  --text-main: #26362e;
  --text-muted: #56655d;
  --accent-deep: #24483a;
  --surface-raised: #fffefa;
  --color-info-border: #d9ddd4;
  display: block;
  min-height: 100dvh;
  padding: 0;
  background: var(--login-countertop);
}

.login-shell {
  position: relative;
  width: 100%;
  min-height: 100dvh;
}

.login-topbar {
  position: absolute;
  z-index: 1;
  top: 28px;
  left: clamp(28px, 4.5vw, 72px);
}

.login-content {
  display: grid;
  min-height: 100dvh;
  grid-template-columns: minmax(390px, 0.92fr) minmax(0, 1.08fr);
  background: transparent;
}

.login-brand {
  display: inline-flex;
  align-items: center;
  gap: 10px;
  color: var(--accent-deep);
  font-family: 'Noto Serif SC', 'Songti SC', Georgia, serif;
  font-size: 25px;
  font-weight: 700;
  text-decoration: none;
}

.login-brand__mark {
  color: var(--accent-deep);
  font-size: 28px;
}

.login-form-panel {
  display: flex;
  flex-direction: column;
  justify-content: center;
  width: min(100%, 530px);
  align-self: center;
  margin: 0 auto;
  padding: clamp(34px, 5vw, 72px);
}

.login-form-heading__eyebrow {
  margin: 0 0 12px;
  color: var(--text-muted);
  font-size: 12px;
  font-weight: 700;
}

.login-form-heading h1 {
  margin: 0 0 8px;
  color: var(--text-main);
  font-family: 'Noto Serif SC', 'Songti SC', Georgia, serif;
  font-size: 32px;
  font-weight: 600;
  line-height: 1.35;
}

.login-title {
  animation: login-title-arrive 400ms cubic-bezier(0.16, 1, 0.3, 1) both;
}

@keyframes login-title-arrive {
  from { opacity: 0; filter: blur(5px); transform: translateY(5px); }
  to { opacity: 1; filter: blur(0); transform: translateY(0); }
}

@keyframes login-form-enter {
  from { opacity: 0; translate: 0 8px; }
  to { opacity: 1; translate: 0 0; }
}

.login-form-heading > p:last-child,
.login-privacy {
  margin: 0;
  color: var(--text-muted);
  font-size: 13px;
  line-height: 1.6;
}

.login-tabs {
  margin-top: 24px;
}

.login-tabs :deep(.el-tabs__item) {
  color: var(--text-muted);
  transition: color 180ms ease, font-weight 180ms ease;
}

.login-tabs :deep(.el-tabs__item.is-active) {
  color: var(--accent-deep);
  font-weight: 700;
}

.login-tabs :deep(.el-tabs__active-bar) {
  background: var(--accent-deep);
  border-radius: 999px;
  transform-origin: left center;
  transition: transform 280ms cubic-bezier(0.22, 1, 0.36, 1),
    width 280ms cubic-bezier(0.22, 1, 0.36, 1);
}

.login-tabs :deep(.el-tabs__nav-wrap::after) {
  background: var(--color-info-border);
}

.login-tabs :deep(.el-form-item__label) {
  color: var(--text-main);
  font-size: 13px;
  font-weight: 600;
}

.login-tabs :deep(.login-form--login .el-form-item),
.login-tabs :deep(.login-form--login .login-submit),
.login-tabs :deep(.login-form--register .el-form-item),
.login-tabs :deep(.login-form--register .login-submit) {
  animation: login-form-enter 320ms cubic-bezier(0.16, 1, 0.3, 1) both;
}

.login-tabs :deep(.login-form--login .el-form-item:nth-child(1)),
.login-tabs :deep(.login-form--register .el-form-item:nth-child(1)) {
  animation-delay: 450ms;
}

.login-tabs :deep(.login-form--login .el-form-item:nth-child(2)),
.login-tabs :deep(.login-form--register .el-form-item:nth-child(2)) {
  animation-delay: 750ms;
}

.login-tabs :deep(.login-form--register .el-form-item:nth-child(3)) {
  animation-delay: 1050ms;
}

.login-tabs :deep(.login-form--register .el-form-item:nth-child(4)) {
  animation-delay: 1350ms;
}

.login-tabs :deep(.login-form--login .login-submit) {
  animation-delay: 1050ms;
}

.login-tabs :deep(.login-form--register .login-submit) {
  animation-delay: 1650ms;
}

.login-tabs :deep(.el-input__wrapper) {
  min-height: 46px;
  border-radius: 6px;
  background: color-mix(in srgb, var(--login-countertop) 95%, white 5%);
  box-shadow: 0 0 0 1px var(--color-info-border) inset;
}

.login-tabs :deep(.el-input__wrapper.is-focus) {
  box-shadow: 0 0 0 1px var(--accent-deep) inset;
}

.login-tabs :deep(.el-input__inner:-webkit-autofill),
.login-tabs :deep(.el-input__inner:-webkit-autofill:hover),
.login-tabs :deep(.el-input__inner:-webkit-autofill:focus) {
  -webkit-text-fill-color: var(--text-main);
  caret-color: var(--text-main);
  -webkit-box-shadow: 0 0 0 1000px color-mix(in srgb, var(--login-countertop) 95%, white 5%) inset;
  transition: background-color 9999s ease-out 0s;
}

.login-submit {
  position: relative;
  display: flex;
  width: 100%;
  min-height: 46px;
  align-items: center;
  justify-content: center;
  gap: 8px;
  margin-top: 8px;
  border: 0;
  border-radius: 10px;
  background: var(--accent-deep);
  font-weight: 650;
  transition: background-color 180ms ease, transform 180ms ease, box-shadow 180ms ease;
}

.login-submit:hover {
  background: color-mix(in srgb, var(--accent-deep) 94%, #000 6%);
  box-shadow: 0 5px 14px rgba(36, 72, 58, 0.15);
  transform: translateY(-1px);
}

.login-submit:active {
  box-shadow: none;
  transform: translateY(1px) scale(0.995);
}

.login-submit :deep(.el-icon) {
  flex: 0 0 auto;
}

.login-submit__labels {
  display: grid;
  align-items: center;
}

.login-submit__label {
  grid-area: 1 / 1;
  transition: opacity 100ms ease;
}

.login-submit__label--warm {
  opacity: 0;
}

.login-submit__label--default {
  transition-delay: 100ms;
}

.login-submit--warm .login-submit__label--default {
  opacity: 0;
  transition-delay: 0ms;
}

.login-submit--warm .login-submit__label--warm {
  opacity: 1;
  transition-delay: 100ms;
}

.login-submit__arrow {
  transition: transform 180ms ease;
}

.login-submit--warm .login-submit__arrow {
  transform: translateX(2px);
}

.login-submit__rice {
  position: absolute;
  top: 50%;
  right: 18px;
  opacity: 0;
  font-size: 16px;
  line-height: 1;
  pointer-events: none;
  transform: translateY(-50%) scale(0.5) rotate(-12deg);
  transform-origin: center;
}

.login-submit--warm .login-submit__rice {
  animation: rice-pop 360ms cubic-bezier(0.16, 1, 0.3, 1) both;
}

@keyframes rice-pop {
  0% { opacity: 0; transform: translateY(-50%) scale(0.5) rotate(-12deg); }
  68% { opacity: 1; transform: translateY(-50%) scale(1.15) rotate(5deg); }
  100% { opacity: 1; transform: translateY(-50%) scale(1) rotate(0); }
}

.login-privacy {
  margin-top: 20px;
  text-align: center;
}

.login-visual {
  position: relative;
  min-width: 0;
  height: 100dvh;
  min-height: 560px;
  overflow: hidden;
  background: var(--login-countertop);
}

.login-visual__image {
  display: block;
  width: 100%;
  height: 100%;
  min-height: 464px;
  object-fit: cover;
  object-position: 54% center;
  transform: scale(1.02) translate3d(var(--visual-x, 0px), var(--visual-y, 0px), 0);
  transition: transform 180ms ease-out;
  -webkit-mask-image: linear-gradient(90deg, transparent 0, #000 200px, #000 100%);
  mask-image: linear-gradient(90deg, transparent 0, #000 200px, #000 100%);
}

.login-visual__micro-image {
  position: absolute;
  z-index: 1;
  inset: 0;
  width: 100%;
  height: 100%;
  min-height: 464px;
  object-fit: cover;
  object-position: 54% center;
  opacity: 0;
  pointer-events: none;
  transform: scale(var(--visual-scale, 1.02)) translate3d(var(--visual-x, 0px), var(--visual-y, 0px), 0);
  transition: opacity 120ms ease-out, transform 220ms cubic-bezier(0.16, 1, 0.3, 1);
  -webkit-mask-image: linear-gradient(90deg, transparent 0, #000 200px, #000 100%);
  mask-image: linear-gradient(90deg, transparent 0, #000 200px, #000 100%);
}

.login-visual__micro-image--salt {
  transform-origin: 18% 20%;
  -webkit-mask-image: radial-gradient(ellipse 9% 10% at 18% 20%, #000 38%, rgba(0, 0, 0, 0.84) 60%, transparent 100%);
  mask-image: radial-gradient(ellipse 9% 10% at 18% 20%, #000 38%, rgba(0, 0, 0, 0.84) 60%, transparent 100%);
}

.login-visual__micro-image--scallion {
  transform-origin: 56% 52%;
  -webkit-mask-image: radial-gradient(ellipse 17% 12% at 56% 52%, #000 38%, rgba(0, 0, 0, 0.84) 60%, transparent 100%);
  mask-image: radial-gradient(ellipse 17% 12% at 56% 52%, #000 38%, rgba(0, 0, 0, 0.84) 60%, transparent 100%);
}

.login-visual__micro-image--chili {
  transform-origin: 18% 69%;
  -webkit-mask-image: radial-gradient(ellipse 16% 7% at 18% 69%, #000 38%, rgba(0, 0, 0, 0.84) 60%, transparent 100%);
  mask-image: radial-gradient(ellipse 16% 7% at 18% 69%, #000 38%, rgba(0, 0, 0, 0.84) 60%, transparent 100%);
}

.login-visual[data-active-food='salt'] .login-visual__micro-image--salt,
.login-visual[data-active-food='scallion'] .login-visual__micro-image--scallion,
.login-visual[data-active-food='chili'] .login-visual__micro-image--chili {
  opacity: 1;
  --visual-scale: 1.07;
}

.login-visual__micro-zone {
  position: absolute;
  z-index: 2;
  display: none;
  cursor: default;
}

.login-visual__micro-zone--salt {
  top: 12%;
  left: 8%;
  width: 17%;
  height: 17%;
}

.login-visual__micro-zone--scallion {
  top: 38%;
  left: 36%;
  width: 38%;
  height: 30%;
}

.login-visual__micro-zone--chili {
  top: 59%;
  left: 7%;
  width: 25%;
  height: 20%;
}

.login-visual__food-tip {
  position: absolute;
  z-index: 3;
  padding: 6px 10px;
  border: 1px solid rgba(36, 72, 58, 0.14);
  border-radius: 7px;
  background: rgba(255, 254, 250, 0.94);
  box-shadow: 0 4px 12px rgba(31, 50, 41, 0.12);
  color: var(--accent-deep);
  font-size: 12px;
  font-weight: 600;
  line-height: 1.3;
  white-space: nowrap;
  pointer-events: none;
  animation: food-tip-arrive 180ms cubic-bezier(0.16, 1, 0.3, 1) both;
}

.login-visual[data-active-food='salt'] .login-visual__food-tip {
  top: 10%;
  left: 23%;
}

.login-visual[data-active-food='scallion'] .login-visual__food-tip {
  top: 38%;
  left: 57%;
}

.login-visual[data-active-food='chili'] .login-visual__food-tip {
  top: 62%;
  left: 26%;
}

@keyframes food-tip-arrive {
  from { opacity: 0; translate: 0 3px; }
  to { opacity: 1; translate: 0 0; }
}

.login-visual__caption {
  position: absolute;
  right: 22px;
  bottom: 22px;
  max-width: calc(100% - 44px);
  margin: 0;
  color: #17372c;
  font-family: 'Noto Serif SC', 'Songti SC', Georgia, serif;
  font-size: 16px;
  font-weight: 600;
  line-height: 1.65;
  text-wrap: balance;
  text-shadow: 0 1px 8px rgba(245, 240, 232, 0.55);
}

.login-visual__caption-line {
  display: block;
  white-space: nowrap;
}

.login-visual__caption--typing .login-visual__caption-line:first-child {
  width: 0;
  animation: caption-typewriter 900ms steps(7, end) forwards;
}

.login-visual__caption--typing .login-visual__caption-line:last-child {
  width: 0;
  animation: caption-typewriter 900ms steps(9, end) 900ms forwards;
}

@keyframes caption-typewriter {
  to { width: 9em; }
}

.login-visual__caption--typing .login-visual__caption-line:first-child {
  animation-name: caption-typewriter-first;
}

@keyframes caption-typewriter-first {
  to { width: 7em; }
}

@media (max-width: 780px) {
  .login-page {
    padding: 12px 18px 26px;
  }

  .login-topbar {
    position: static;
    min-height: 40px;
    padding: 0;
  }

  .login-brand {
    font-size: 21px;
  }

  .login-brand__mark {
    font-size: 24px;
  }

  .login-content {
    min-height: 0;
    grid-template-columns: minmax(0, 1fr);
  }

  .login-visual {
    grid-row: 1;
    height: min(88vw, 360px);
    min-height: 250px;
  }

  .login-visual__image {
    min-height: 0;
    object-position: 54% 44%;
    transform: scale(1.02) !important;
    transition: none;
    -webkit-mask-image: linear-gradient(180deg, #000 68%, transparent 100%);
    mask-image: linear-gradient(180deg, #000 68%, transparent 100%);
  }

  .login-visual__micro-image,
  .login-visual__micro-zone {
    display: none;
  }

  .login-visual__caption {
    right: 12px;
    bottom: 38px;
    font-size: 14px;
  }

  .login-form-panel {
    grid-row: 2;
    max-width: 540px;
    padding: 28px clamp(22px, 7vw, 42px) 30px;
  }

  .login-form-heading h1 {
    font-size: 28px;
  }
}

@media (min-width: 781px) and (max-height: 700px) {
  .login-topbar {
    top: 18px;
  }

  .login-content {
    min-height: 100dvh;
  }

  .login-form-panel {
    padding: 72px clamp(24px, 4vw, 52px) 20px;
  }

  .login-tabs {
    margin-top: 16px;
  }
}

.login-hint {
  margin: 16px 0 0;
  font-size: var(--font-xs, 12px);
  color: var(--color-info);
  line-height: 1.7;
  text-align: center;
}

@media (max-width: 420px) {
  .login-form-panel {
    padding: 24px 20px 24px;
  }
}

@media (prefers-reduced-motion: reduce) {
  .login-tabs :deep(.el-tabs__item),
  .login-tabs :deep(.el-tabs__active-bar),
  .login-submit,
  .login-submit__label,
  .login-submit__arrow {
    transition-duration: 0.01ms;
  }

  .login-submit__label {
    transition-delay: 0ms !important;
  }

  .login-submit__rice {
    animation: none !important;
    transform: translateY(-50%);
  }

  .login-submit--warm .login-submit__rice {
    opacity: 1;
  }

  .login-title {
    animation: none;
  }

  .login-tabs :deep(.login-form--login .el-form-item),
  .login-tabs :deep(.login-form--login .login-submit),
  .login-tabs :deep(.login-form--register .el-form-item),
  .login-tabs :deep(.login-form--register .login-submit) {
    animation: none;
  }

  .login-visual__image {
    transform: none !important;
    transition: none;
  }

  .login-visual__micro-image {
    display: none;
    transition: none;
  }

  .login-visual__food-tip {
    animation: none;
  }

  .login-visual__caption-line {
    width: auto !important;
    animation: none !important;
  }
}

@media (hover: hover) and (pointer: fine) and (min-width: 781px) {
  .login-visual__micro-zone {
    display: block;
  }
}
</style>
