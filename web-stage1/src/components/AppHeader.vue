<script setup lang="ts">
/**
 * 组件职责：应用顶部条（App 壳头部）。
 * - 左：产品标识「🍳 AI 厨娘・智能烹饪助手」；
 * - 中：导航（router-link：首页 /、选择食材 /select、推荐结果 /recommend、
 *   家庭档案 /profile、我的冰箱 /inventory、我的 /me、调度面板 /trace）；
 *   推荐入口读 config store，switches.recommend=false 时 disabled + tooltip「推荐功能维护中」；
 * - 右：深色模式切换按钮（useDarkMode）；
 * - 页面级：FeedbackFab（全局反馈 FAB + 弹窗，fixed 定位挂在头部随壳渲染）。
 */
import { computed } from 'vue'
import { Mic as MicIcon } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import { useRouter } from 'vue-router'
import { useDarkMode } from '@/composables/useDarkMode'
import { useConfigStore } from '@/stores/config'
import { useAuthStore } from '@/stores/auth'
import { toggleVoiceAgent, voiceAgentEnabled } from '@/utils/voiceAgent'
import FeedbackFab from '@/components/FeedbackFab.vue'

/** 深色模式组合式函数（单例状态） */
const { isDark, toggle } = useDarkMode()
/** 远程开关 store（控制推荐入口置灰） */
const configStore = useConfigStore()
/** 账号 store（头部昵称与退出登录） */
const authStore = useAuthStore()
const router = useRouter()

/** 推荐入口是否可用（远程开关关闭 → 置灰） */
const recommendEnabled = computed(() => configStore.switches.recommend)

/** 退出登录（二次确认）：回到登录页，匿名会话换新避免残留上一账号数据 */
function onLogout(): void {
  ElMessage.success('已退出登录')
  authStore.logout()
  void router.replace('/login')
}
</script>

<template>
  <header class="app-header">
    <!-- 左：产品标识 -->
    <div class="app-header__brand">🍳 AI 厨娘・智能烹饪助手</div>

    <!-- 中：页面导航（阶段一无导航框架，单页切换） -->
    <nav class="app-header__nav" aria-label="页面导航">
      <router-link class="app-header__link" to="/">首页</router-link>
      <router-link class="app-header__link" to="/select">选择食材</router-link>

      <!-- 推荐入口：远程开关关闭时置灰 + tooltip 说明 -->
      <el-tooltip
        content="推荐功能维护中"
        placement="bottom"
        :disabled="recommendEnabled"
      >
        <span class="app-header__link-wrap">
          <router-link
            class="app-header__link"
            :class="{ 'app-header__link--disabled': !recommendEnabled }"
            to="/recommend"
            :aria-disabled="!recommendEnabled"
            @click="!recommendEnabled && $event.preventDefault()"
          >
            推荐结果
          </router-link>
        </span>
      </el-tooltip>

      <router-link class="app-header__link" to="/profile">家庭档案</router-link>
      <router-link class="app-header__link" to="/inventory">我的冰箱</router-link>
      <router-link class="app-header__link" to="/me">我的</router-link>
      <router-link class="app-header__link" to="/trace">调度面板</router-link>
    </nav>

    <!-- 右：账号（昵称 + 退出）+ 语音助手开关 + 深色模式切换 -->
    <div class="app-header__actions">
      <span v-if="authStore.isLoggedIn" class="app-header__user" title="当前登录账号">
        👤 {{ authStore.displayName }}
      </span>
      <el-button
        v-if="authStore.isLoggedIn"
        class="app-header__logout-btn"
        size="small"
        text
        type="info"
        @click="onLogout"
      >
        退出
      </el-button>
      <el-tooltip
        :content="voiceAgentEnabled ? '语音助手监听中：说「嗨，厨娘」唤醒' : '开启语音助手：说「嗨，厨娘」唤醒'" placement="bottom"
      >
        <el-button
          class="app-header__voice-btn"
          circle
          :type="voiceAgentEnabled ? 'primary' : 'default'"
          :aria-label="voiceAgentEnabled ? '关闭语音助手' : '开启语音助手'"
          :title="voiceAgentEnabled ? '关闭语音助手' : '开启语音助手（说「嗨，厨娘」唤醒）'"
          @click="toggleVoiceAgent"
        >
          <el-icon><MicIcon /></el-icon>
        </el-button>
      </el-tooltip>

      <el-button
        class="app-header__dark-btn"
        :icon="isDark ? undefined : undefined"
        circle
        :aria-label="isDark ? '切换到浅色模式' : '切换到深色模式'"
        :title="isDark ? '切换到浅色模式' : '切换到深色模式'"
        @click="toggle"
      >
        <!-- 图标随模式切换：Sunny（当前深色，点回浅色）/ Moon（当前浅色，点去深色） -->
        <el-icon v-if="isDark"><ElIconSunny /></el-icon>
        <el-icon v-else><ElIconMoon /></el-icon>
      </el-button>
    </div>

    <!-- 全局反馈 FAB：fixed 定位（视觉在右下角），随壳渲染保证全页面可见 -->
    <FeedbackFab />
  </header>
</template>

<style scoped>
.app-header__actions {
  display: flex;
  align-items: center;
  gap: 8px;
}

.app-header__user {
  max-width: 140px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-size: var(--font-sm);
  color: var(--text-main);
}

.app-header__logout-btn {
  padding: 4px 6px;
}

.app-header {
  position: sticky;
  top: 0;
  z-index: 100;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  height: var(--header-height);
  padding: 0 20px;
  background: var(--card-bg);
  border-bottom: 1px solid var(--color-info-border);
}

.app-header__brand {
  font-size: var(--font-md);
  font-weight: 600;
  white-space: nowrap;
}

.app-header__nav {
  display: flex;
  align-items: center;
  gap: 8px;
}

.app-header__link {
  display: inline-block;
  padding: 6px 14px;
  border-radius: 6px;
  font-size: var(--font-sm);
  color: var(--text-main);
  text-decoration: none;
  transition: background-color 0.2s ease;
}

.app-header__link:hover {
  background: var(--color-info-bg);
}

/* 路由激活态 */
.app-header__link.router-link-active {
  background: var(--color-info-bg);
  font-weight: 600;
}

/* 远程开关关闭：置灰 + 禁止点击 */
.app-header__link--disabled {
  color: var(--color-info);
  opacity: 0.55;
  cursor: not-allowed;
}

.app-header__link-wrap {
  display: inline-block;
}
</style>
