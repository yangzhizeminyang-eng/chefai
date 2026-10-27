<script setup lang="ts">
/** Shared navigation and the account/preferences drawer for the signed-in workspace. */
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import {
  ArrowDown,
  Avatar,
  ChatDotRound,
  Dish,
  House,
  Mic as MicIcon,
  Moon,
  Refrigerator,
  Setting,
  Sunny,
} from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import { useRouter } from 'vue-router'
import { useDarkMode } from '@/composables/useDarkMode'
import { useConfigStore } from '@/stores/config'
import { useAuthStore } from '@/stores/auth'
import { toggleVoiceAgent, voiceAgentEnabled } from '@/utils/voiceAgent'
import FeedbackFab from '@/components/FeedbackFab.vue'

const { isDark, toggle } = useDarkMode()
const configStore = useConfigStore()
const authStore = useAuthStore()
const router = useRouter()
const preferencesOpen = ref(false)
const recommendEnabled = computed(() => configStore.switches.recommend)

function closePreferences(): void {
  preferencesOpen.value = false
}

function openFeedback(): void {
  window.dispatchEvent(new CustomEvent('aicook:open-feedback'))
  closePreferences()
}

function onLogout(): void {
  ElMessage.success('已退出登录')
  authStore.logout()
  closePreferences()
  void router.replace('/login')
}

function onGlobalKeydown(event: KeyboardEvent): void {
  if (event.key === 'Escape') closePreferences()
}

onMounted(() => window.addEventListener('keydown', onGlobalKeydown))
onBeforeUnmount(() => window.removeEventListener('keydown', onGlobalKeydown))
</script>

<template>
  <aside class="app-sidebar">
    <div class="app-sidebar__top">
      <router-link class="app-sidebar__brand" to="/" aria-label="AI 厨娘首页">
        <span class="app-sidebar__brand-mark" aria-hidden="true"><el-icon><Dish /></el-icon></span>
        <span class="app-sidebar__brand-copy">
          <strong>AI 厨娘</strong>
          <small>智能烹饪助手</small>
        </span>
      </router-link>

      <nav class="app-sidebar__nav" aria-label="页面导航">
        <p class="app-sidebar__caption">厨房</p>
        <router-link class="app-sidebar__link" to="/">
          <el-icon><House /></el-icon><span>首页</span>
        </router-link>
        <router-link class="app-sidebar__link" to="/today">
          <el-icon><Dish /></el-icon><span>今天吃什么</span>
        </router-link>
        <el-tooltip content="推荐功能维护中" placement="right" :disabled="recommendEnabled">
          <span class="app-sidebar__link-wrap">
            <router-link
              class="app-sidebar__link"
              :class="{ 'app-sidebar__link--disabled': !recommendEnabled }"
              to="/recommend"
              :aria-disabled="!recommendEnabled"
              @click="!recommendEnabled && $event.preventDefault()"
            >
              <el-icon><Dish /></el-icon><span>推荐结果</span>
            </router-link>
          </span>
        </el-tooltip>

        <p class="app-sidebar__caption app-sidebar__caption--spaced">我的厨房</p>
        <router-link class="app-sidebar__link" to="/inventory">
          <el-icon><Refrigerator /></el-icon><span>食材库存</span>
        </router-link>
        <router-link class="app-sidebar__link" to="/profile">
          <el-icon><Avatar /></el-icon><span>家庭档案</span>
        </router-link>
        <router-link class="app-sidebar__link" :to="{ path: '/me', query: { section: 'settings' } }">
          <el-icon><Setting /></el-icon><span>设置</span>
        </router-link>
      </nav>
    </div>

    <div class="app-sidebar__bottom">
      <button
        class="app-sidebar__account-trigger"
        type="button"
        aria-haspopup="dialog"
        aria-controls="account-preferences"
        :aria-expanded="preferencesOpen"
        @click="preferencesOpen = !preferencesOpen"
      >
        <span class="app-sidebar__avatar"><el-icon><Avatar /></el-icon></span>
        <span class="app-sidebar__account-name" :title="authStore.displayName">{{ authStore.displayName }}</span>
        <el-icon class="app-sidebar__account-expand"><ArrowDown /></el-icon>
      </button>
    </div>

    <Transition name="account-drawer">
      <section
        v-if="preferencesOpen"
        id="account-preferences"
        class="account-drawer"
        role="dialog"
        aria-label="账户与偏好"
        @keydown.esc.stop="closePreferences"
      >
        <header class="account-drawer__header">
          <div><span>账户</span><strong>{{ authStore.displayName }}</strong></div>
          <button type="button" class="account-drawer__close" aria-label="关闭账户面板" @click="closePreferences">×</button>
        </header>
        <button class="account-drawer__row" type="button" @click="router.push('/me'); closePreferences()">
          <span class="account-drawer__icon"><el-icon><Avatar /></el-icon></span>
          <span class="account-drawer__copy"><strong>个人中心</strong><small>收藏、记录与个人数据</small></span>
          <el-icon class="account-drawer__navigate"><ArrowDown /></el-icon>
        </button>
        <button
          class="account-drawer__row"
          type="button"
          :aria-pressed="voiceAgentEnabled"
          @click="toggleVoiceAgent"
        >
          <span class="account-drawer__icon"><el-icon><MicIcon /></el-icon></span>
          <span class="account-drawer__copy"><strong>语音助手</strong><small>{{ voiceAgentEnabled ? '正在监听「厨娘」唤醒词' : '按需开启，使用麦克风' }}</small></span>
          <span class="account-drawer__state" :class="{ 'account-drawer__state--on': voiceAgentEnabled }">{{ voiceAgentEnabled ? '已开启' : '关闭' }}</span>
        </button>
        <button class="account-drawer__row" type="button" :aria-label="isDark ? '切换到明亮主题' : '切换到深色主题'" @click="toggle">
          <span class="account-drawer__icon"><el-icon><Sunny v-if="isDark" /><Moon v-else /></el-icon></span>
          <span class="account-drawer__copy"><strong>外观主题</strong><small>{{ isDark ? '深色厨房 · 全站同步' : '明亮厨房 · 全站同步' }}</small></span>
          <span class="account-drawer__state">切换</span>
        </button>
        <button class="account-drawer__row" type="button" @click="openFeedback">
          <span class="account-drawer__icon"><el-icon><ChatDotRound /></el-icon></span>
          <span class="account-drawer__copy"><strong>意见反馈</strong><small>告诉我们哪里还可以更好</small></span>
        </button>
        <button class="account-drawer__logout" type="button" @click="onLogout()">
          <span>退出登录</span><el-icon><ArrowDown /></el-icon>
        </button>
      </section>
    </Transition>

    <FeedbackFab :show-launcher="false" />
  </aside>
</template>

<style scoped>
.app-sidebar {
  position: sticky;
  top: 0;
  z-index: 20;
  display: flex;
  width: var(--sidebar-width);
  min-width: 0;
  height: 100dvh;
  min-height: 520px;
  flex-direction: column;
  justify-content: space-between;
  padding: 25px 12px 16px;
  color: var(--sidebar-text);
  border-right: 1px solid var(--sidebar-line);
  background: var(--sidebar-bg);
}

.app-sidebar__brand {
  display: flex;
  align-items: center;
  gap: 11px;
  padding: 0 7px 23px;
  color: inherit;
  border-bottom: 1px solid var(--sidebar-line);
  text-decoration: none;
}

.app-sidebar__brand-mark {
  display: grid;
  width: 42px;
  height: 42px;
  flex: 0 0 42px;
  place-items: center;
  color: var(--accent-deep);
  border: 1px solid var(--color-info-border);
  border-radius: 50%;
  background: var(--surface-raised);
  font-size: 21px;
}

.app-sidebar__brand-copy strong,
.app-sidebar__brand-copy small { display: block; }
.app-sidebar__brand-copy strong { color: var(--sidebar-text); font-family: Georgia, 'Noto Serif SC', serif; font-size: 17px; font-weight: 700; }
.app-sidebar__brand-copy small { margin-top: 4px; color: var(--sidebar-muted); font-size: 11px; }
.app-sidebar__nav { display: grid; gap: 5px; margin-top: 24px; }
.app-sidebar__caption { margin: 0 11px 6px; color: var(--sidebar-muted); font-size: 11px; font-weight: 700; }
.app-sidebar__caption--spaced { margin-top: 23px; }
.app-sidebar__link-wrap { display: block; }

.app-sidebar__link {
  display: flex;
  min-height: 42px;
  align-items: center;
  gap: 11px;
  padding: 0 11px;
  color: var(--sidebar-muted);
  border-radius: 7px;
  text-decoration: none;
  font-size: 13px;
  font-weight: 600;
  transition: color 180ms ease, background-color 180ms ease;
}

.app-sidebar__link .el-icon { font-size: 17px; }
.app-sidebar__link:hover { color: var(--sidebar-text); background: var(--sidebar-hover); }
.app-sidebar__link.router-link-exact-active { color: var(--sidebar-active-text); background: var(--sidebar-active); }
.app-sidebar__link--disabled { opacity: 0.48; cursor: not-allowed; }
.app-sidebar__link:focus-visible { outline: 2px solid var(--accent-deep); outline-offset: 2px; }

.app-sidebar__bottom { padding-top: 12px; border-top: 1px solid var(--sidebar-line); }
.app-sidebar__account-trigger {
  display: flex;
  width: 100%;
  min-width: 0;
  min-height: 46px;
  align-items: center;
  gap: 9px;
  padding: 4px 7px;
  color: var(--sidebar-text);
  border: 0;
  border-radius: 7px;
  background: transparent;
  text-align: left;
  cursor: pointer;
}
.app-sidebar__account-trigger:hover { background: var(--sidebar-hover); }
.app-sidebar__account-trigger:focus-visible { outline: 2px solid var(--accent-deep); outline-offset: 2px; }
.app-sidebar__avatar { display: grid; width: 32px; height: 32px; flex: 0 0 32px; place-items: center; color: var(--accent-deep); border: 1px solid var(--color-info-border); border-radius: 50%; background: var(--surface-soft); }
.app-sidebar__account-name { overflow: hidden; min-width: 0; color: var(--sidebar-text); font-size: 12px; text-overflow: ellipsis; white-space: nowrap; }
.app-sidebar__account-expand { margin-left: auto; color: var(--sidebar-muted); transition: transform 180ms ease; }
.app-sidebar__account-trigger[aria-expanded='true'] .app-sidebar__account-expand { transform: rotate(180deg); }

.account-drawer {
  position: absolute;
  z-index: 150;
  right: -12px;
  bottom: 76px;
  left: 12px;
  padding: 17px 14px 11px;
  color: var(--text-main);
  border: 1px solid var(--color-info-border);
  border-radius: 8px;
  background: var(--surface-raised);
  box-shadow: var(--shadow-soft);
}
.account-drawer__header { display: flex; align-items: flex-start; justify-content: space-between; padding: 0 1px 13px; border-bottom: 1px solid var(--color-info-border); }
.account-drawer__header div { display: grid; gap: 4px; }
.account-drawer__header span { color: var(--text-muted); font-size: 11px; }
.account-drawer__header strong { color: var(--text-main); font-size: 15px; }
.account-drawer__close { display: grid; width: 30px; height: 30px; place-items: center; color: var(--text-muted); border: 0; border-radius: 6px; background: transparent; font-size: 21px; cursor: pointer; }
.account-drawer__close:hover { color: var(--text-main); background: var(--surface-hover); }
.account-drawer__row { display: flex; width: 100%; min-height: 62px; align-items: center; gap: 10px; padding: 8px 1px; color: inherit; border: 0; border-bottom: 1px solid var(--color-info-border); background: transparent; text-align: left; cursor: pointer; }
.account-drawer__row:hover .account-drawer__copy strong { color: var(--accent-deep); }
.account-drawer__row:focus-visible, .account-drawer__close:focus-visible, .account-drawer__logout:focus-visible { outline: 2px solid var(--accent-deep); outline-offset: 2px; }
.account-drawer__icon { display: grid; width: 34px; height: 34px; flex: 0 0 34px; place-items: center; color: var(--accent-deep); border-radius: 6px; background: var(--surface-soft); font-size: 16px; }
.account-drawer__copy { display: grid; min-width: 0; flex: 1; gap: 4px; }
.account-drawer__copy strong { color: var(--text-main); font-size: 12px; font-weight: 650; }
.account-drawer__copy small { color: var(--text-muted); font-size: 10px; line-height: 1.4; }
.account-drawer__state { flex: 0 0 auto; color: var(--text-muted); font-size: 10px; }
.account-drawer__state--on { color: var(--accent-deep); font-weight: 700; }
.account-drawer__navigate { color: var(--text-muted); transform: rotate(-90deg); }
.account-drawer__logout { display: flex; width: 100%; min-height: 40px; align-items: center; justify-content: space-between; margin-top: 8px; padding: 0 2px; color: var(--color-danger); border: 0; background: transparent; font: inherit; font-size: 12px; cursor: pointer; }
.account-drawer__logout .el-icon { transform: rotate(-90deg); }

.account-drawer-enter-active,
.account-drawer-leave-active { transition: opacity 180ms ease, transform 220ms cubic-bezier(0.16, 1, 0.3, 1); }
.account-drawer-enter-from,
.account-drawer-leave-to { opacity: 0; transform: translateY(9px); }

@media (max-width: 900px) {
  .app-sidebar { position: sticky; z-index: 100; width: 100%; height: auto; min-height: 0; padding: 10px 18px 9px; color: var(--sidebar-text); background: var(--sidebar-bg); border-right: 0; border-bottom: 1px solid var(--sidebar-line); }
  .app-sidebar__top { display: flex; align-items: center; justify-content: space-between; gap: 16px; }
  .app-sidebar__brand { flex: 0 0 auto; padding: 0; border: 0; }
  .app-sidebar__brand-mark { width: 34px; height: 34px; flex-basis: 34px; font-size: 17px; }
  .app-sidebar__brand-copy strong { color: var(--sidebar-text); font-size: 15px; }
  .app-sidebar__brand-copy small { display: none; }
  .app-sidebar__nav { display: flex; min-width: 0; gap: 4px; margin: 0; overflow-x: auto; overscroll-behavior-inline: contain; scrollbar-width: none; }
  .app-sidebar__nav::-webkit-scrollbar { display: none; }
  .app-sidebar__caption { display: none; }
  .app-sidebar__link-wrap { flex: 0 0 auto; }
  .app-sidebar__link { flex: 0 0 auto; min-height: 38px; padding: 0 10px; font-size: 12px; white-space: nowrap; }
  .app-sidebar__link .el-icon { display: none; }
  .app-sidebar__link.router-link-exact-active { color: var(--sidebar-active-text); background: var(--sidebar-active); }
  .app-sidebar__bottom { position: absolute; top: 9px; right: 18px; width: min(176px, 38vw); padding: 0; border: 0; }
  .app-sidebar__account-trigger { min-height: 37px; padding: 2px 4px; }
  .app-sidebar__avatar { width: 29px; height: 29px; flex-basis: 29px; }
  .app-sidebar__account-name { color: var(--sidebar-text); font-size: 11px; }
  .account-drawer { position: fixed; top: 64px; right: 14px; bottom: auto; left: auto; width: min(330px, calc(100vw - 28px)); }
}

@media (max-width: 560px) {
  .app-sidebar { padding: 9px 13px 7px; }
  .app-sidebar__top { flex-wrap: wrap; gap: 7px 12px; }
  .app-sidebar__nav { width: 100%; margin-left: -3px; }
  .app-sidebar__link { min-height: 36px; padding: 0 9px; }
  .app-sidebar__bottom { top: 8px; right: 13px; width: min(152px, 42vw); }
  .app-sidebar__account-trigger { min-height: 34px; gap: 6px; }
  .app-sidebar__avatar { width: 27px; height: 27px; flex-basis: 27px; }
  .account-drawer { top: auto; right: 0; bottom: 0; left: 0; width: 100%; padding: 18px 18px max(18px, env(safe-area-inset-bottom)); border-radius: 12px 12px 0 0; }
}

@media (prefers-reduced-motion: reduce) {
  .app-sidebar__link, .app-sidebar__account-expand,
  .account-drawer-enter-active, .account-drawer-leave-active { transition-duration: 0.01ms; }
  .account-drawer-enter-from, .account-drawer-leave-to { transform: translateY(100%); }
}
</style>
