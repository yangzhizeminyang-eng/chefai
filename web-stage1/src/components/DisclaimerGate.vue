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
    title="使用前请阅读"
    transition="instant-gate"
    class="disclaimer-gate-dialog"
    align-center
  >
    <div class="gate-scene" aria-hidden="true"></div>
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
:global(.disclaimer-gate-dialog.el-dialog.is-fullscreen) {
  --gate-countertop: #f5f0e8;
  --gate-ink: #26362e;
  --gate-green: #24483a;
  margin: 0;
  padding: 0;
  overflow: hidden;
  background: var(--gate-countertop);
  color: var(--gate-ink);
}

:global(.disclaimer-gate-dialog .el-dialog__header) {
  display: none;
}

:global(.disclaimer-gate-dialog .el-dialog__body) {
  position: relative;
  min-height: 100dvh;
  padding: 0;
  overflow: hidden;
}

.gate-scene {
  position: absolute;
  z-index: 0;
  top: 0;
  right: 0;
  width: min(34vw, 420px);
  height: clamp(128px, 20vh, 210px);
  pointer-events: none;
  background-image:
    linear-gradient(270deg, rgba(245, 240, 232, 0.04) 12%, rgba(245, 240, 232, 0.94) 100%),
    linear-gradient(180deg, rgba(245, 240, 232, 0.08), rgba(245, 240, 232, 0.52)),
    url('/images/login-prep-scene.png');
  background-size: cover;
  background-position: 88% 8%;
  mask-image: linear-gradient(135deg, transparent 0%, #000 43%);
}

.gate-body {
  position: relative;
  z-index: 1;
  min-height: 100dvh;
  max-width: 640px;
  margin: 0 auto;
  padding: clamp(36px, 8vh, 88px) 24px;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 24px;
}

.gate-title {
  color: var(--gate-ink);
  font-family: 'Noto Serif SC', 'Songti SC', Georgia, serif;
  font-size: 24px;
  font-weight: 600;
  line-height: 1.4;
  margin: 0;
}

.gate-clauses {
  width: 100%;
  margin: 0;
  padding: 20px 24px;
  list-style: none;
  background: #f2eddf;
  border: 1px solid #e3dccb;
  border-radius: 8px;
  box-shadow: 0 10px 26px rgba(83, 68, 45, 0.06);
}

.gate-clause {
  font-size: var(--font-md);
  line-height: 1.8;
  color: var(--gate-ink);
}

.gate-check {
  font-size: var(--font-md);
}

.gate-check :deep(.el-checkbox__inner) {
  width: 18px;
  height: 18px;
  border-color: #859287;
  border-radius: 4px;
  background: #fffdf8;
}

.gate-check :deep(.el-checkbox__input.is-checked .el-checkbox__inner) {
  border-color: var(--gate-green);
  background: var(--gate-green);
}

.gate-check :deep(.el-checkbox__input.is-focus .el-checkbox__inner) {
  border-color: var(--gate-green);
  box-shadow: 0 0 0 3px rgba(36, 72, 58, 0.16);
}

.gate-check :deep(.el-checkbox__label) {
  color: #26362e;
}

.gate-enter-btn {
  min-width: 200px;
  min-height: 46px;
  border: 0;
  border-radius: 10px;
  background: var(--gate-green);
  font-size: var(--font-lg);
  font-weight: 650;
  transition: background-color 180ms ease, box-shadow 180ms ease, transform 180ms ease;
}

.gate-enter-btn:hover:not(:disabled) {
  background: color-mix(in srgb, var(--gate-green) 88%, black 12%);
  box-shadow: 0 5px 14px rgba(36, 72, 58, 0.16);
  transform: translateY(-1px);
}

.gate-enter-btn:active:not(:disabled) {
  box-shadow: none;
  transform: translateY(1px) scale(0.995);
}

.gate-enter-btn:disabled {
  background: #9aa79f;
}

@media (max-width: 600px) {
  .gate-scene {
    width: 48vw;
    height: 120px;
    opacity: 0.75;
  }

  .gate-body {
    padding: 40px 20px;
    gap: 20px;
  }

  .gate-clauses {
    padding: 18px 16px;
  }

  .gate-clause {
    font-size: 15px;
  }
}

@media (prefers-reduced-motion: reduce) {
  .gate-enter-btn {
    transition: none;
  }
}
</style>
