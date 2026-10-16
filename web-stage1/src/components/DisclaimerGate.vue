<script setup lang="ts">
/**
 * 组件职责：免责声明首次全屏弹窗（对齐 UI 清单 P-00）。
 * - 首次进入强制弹出：标题「使用前请阅读」+ PRD 三条固定免责条款；
 * - 未勾选「我已阅读并同意」时「进入」按钮置灰禁用；
 * - 勾选后点击「进入」：调 session.agreeDisclaimer()（POST /v1/consent/disclaimer，
 *   失败不阻塞——本地兜底）+ localStorage 记忆 disclaimer_agreed_v1=1；
 * - 已同意（本地记忆命中）则不弹。
 */
import { computed, ref } from 'vue'
import { useSessionStore } from '@/stores/session'
import { useAuthStore } from '@/stores/auth'

/** 会话 store（disclaimerAgreed 状态与同意动作） */
const session = useSessionStore()
/** 账号 store（登录墙：免责弹窗在登录/注册之后再出现） */
const authStore = useAuthStore()

/** 勾选框状态（未勾选 → 按钮禁用） */
const checked = ref(false)

/** 是否展示弹窗：已登录且未同意过免责声明 */
const visible = computed(() => authStore.isLoggedIn && !session.disclaimerAgreed)

/** PRD 三条固定免责条款（与产品文档逐字一致，不得改写） */
const CLAUSES: string[] = [
  '本产品提供的是烹饪与饮食参考建议，不构成医疗、营养治疗建议；',
  '所有食品安全提示以实物标签、产品说明及国家官方指南为准；',
  '如有食物过敏史、慢性疾病、孕期或哺乳期，请遵医嘱。',
]

/**
 * 点击「进入」：调同意接口（失败本地兜底）并关闭弹窗。
 * @returns 无
 */
async function onEnter(): Promise<void> {
  // agreeDisclaimer 内部已做失败兜底（本地记忆），不会抛出阻塞
  await session.agreeDisclaimer()
}
</script>

<template>
  <!-- 全屏遮罩弹窗：已同意或未登录（登录页）不渲染 -->
  <el-dialog
    :model-value="visible"
    fullscreen
    :show-close="false"
    :close-on-click-modal="false"
    :close-on-press-escape="false"
    class="disclaimer-gate-dialog"
    align-center
    aria-label="使用前请阅读"
  >
    <div class="gate-body">
      <h2 class="gate-title">使用前请阅读</h2>

      <!-- 三条固定免责条款 -->
      <ul class="gate-clauses">
        <li v-for="(clause, idx) in CLAUSES" :key="idx" class="gate-clause">
          {{ idx + 1 }}. {{ clause }}
        </li>
      </ul>

      <!-- 勾选框：未勾选时进入按钮置灰 -->
      <el-checkbox v-model="checked" class="gate-check" size="large">
        我已阅读并同意
      </el-checkbox>

      <!-- 进入按钮：未勾选 disabled（视觉置灰） -->
      <el-button
        type="primary"
        size="large"
        class="gate-enter-btn"
        :disabled="!checked"
        @click="onEnter"
      >
        进入
      </el-button>
    </div>
  </el-dialog>
</template>

<style scoped>
.gate-body {
  max-width: 640px;
  margin: 0 auto;
  padding: 48px 24px;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 24px;
}

.gate-title {
  font-size: 24px;
  font-weight: 600;
  margin: 0;
}

.gate-clauses {
  width: 100%;
  margin: 0;
  padding: 20px 24px;
  list-style: none;
  background: var(--color-info-bg);
  border: 1px solid var(--color-info-border);
  border-radius: 10px;
}

.gate-clause {
  font-size: var(--font-md);
  line-height: 1.8;
  color: var(--text-main);
}

.gate-check {
  font-size: var(--font-md);
}

.gate-enter-btn {
  min-width: 200px;
  min-height: 44px;
  font-size: var(--font-lg);
}
</style>
