<script setup lang="ts">
/**
 * 视图职责：W-04 分步引导页（灶台大字，对齐 UI 清单 W-04 行）。
 * 区块：① 顶部：过敏原警示条（会话 allergen_conflict 时）+「退出」按钮（二次确认）
 *       ② 进度：el-progress + 「第 X 步 / 共 Y 步」
 *       ③ 主体大字：步骤描述 ≥32px（cook-step-text）+ 本步用量提示 ≥20px + 预计耗时
 *       ④ 新手要点区：key_point + failure_tips（折叠可展开）
 *       ⑤ 底部操作：「上一步」「下一步」大按钮（纯本地切换 ≤300ms；store 更新 +
 *          800ms 防抖静默 PATCH）；第一步禁用上一步；最后一步「下一步」变「完成」
 *       ⑥「步骤列表」按钮 → el-drawer 全量步骤可点击跳转。
 * Task 9 增强：
 *       ⑦ 多路计时器（右下抽屉，≥3 路并行倒计时，本地 MultiTimer 实现，
 *          归零 el-notification 提示，不依赖网络）；
 *       ⑧ 屏幕常亮（Wake Lock API：进入页面申请、离开/隐藏释放，try/catch 静默降级）；
 *       ⑨「求助」按钮（弹窗输入问题 → POST /v1/cooking/sessions/{id}/help →
 *          三态展示：回答列表 / 拦截话术 / 429 当日超限提示）。
 * 断点续做恢复策略：内存 store（同会话 id 直接复用）→ localStorage
 * cook_session_{id}（会话实体）+ cook_steps_{id}（步骤快照与步骤号）→ 都无则提示并回 /select
 * （endpoints 无「查询会话」GET 接口，阶段一不做远端兜底）。
 */
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage, ElMessageBox, ElNotification } from 'element-plus'
import { Timer as TimerIcon } from '@element-plus/icons-vue'
import { finishCookingSession, postCookingHelp } from '@/api/endpoints'
import type { ApiError } from '@/api/types'
import { useCookingStore } from '@/stores/cooking'
import { MultiTimer, formatCountdown, type TimerSnapshot } from '@/utils/timer'
import AllergenAlertBar from '@/components/AllergenAlertBar.vue'

/** 路由（取 :sessionId 与退出/完成跳转） */
const route = useRoute()
const router = useRouter()
/** 烹饪 store：会话 / 本地步骤索引 / 本地切换动作 */
const cookingStore = useCookingStore()

/** 会话恢复失败标记（内存与本地缓存均无 → 提示后回 /select） */
const restoreFailed = ref(false)
/** 「完成」请求进行中 */
const finishing = ref(false)
/** 步骤列表抽屉可见性 */
const drawerVisible = ref(false)

/** 当前步骤对象（来自 store getter） */
const currentStep = computed(() => cookingStore.currentStep)

/** 是否最后一步（「下一步」变「完成」） */
const isLast = computed(
  () => cookingStore.totalSteps > 0 && cookingStore.currentStepNo >= cookingStore.totalSteps,
)

/** 进度百分比 = 当前步 / 总步数 */
const progressPercent = computed(() => {
  if (cookingStore.totalSteps === 0) return 0
  return Math.round((cookingStore.currentStepNo / cookingStore.totalSteps) * 100)
})

/**
 * 秒数转可读耗时（步骤展示）。
 * @param sec 耗时秒数（0 表示无需等待）
 * @returns 可读文案
 */
function formatDuration(sec: number): string {
  if (!sec || sec <= 0) return '无需等待'
  if (sec < 60) return `${sec} 秒`
  return `约 ${Math.round(sec / 60)} 分钟`
}

/**
 * 退出烹饪引导：ElMessageBox 二次确认（进度保留在会话与本地缓存）。
 * 确认后先把未落地的防抖 PATCH 立即落库，再回食材选择页。
 * @returns 无
 */
function onExit(): void {
  ElMessageBox.confirm('退出后进度将保留，确认退出？', '退出烹饪引导', {
    confirmButtonText: '确认退出',
    cancelButtonText: '继续做菜',
    type: 'warning',
  })
    .then(() => {
      // 将防抖中的断点立即落库，保证下次断点续做准确
      void cookingStore.persistStep()
      void router.push('/select')
    })
    .catch(() => {
      // 用户取消：继续做菜，无操作
    })
}

/**
 * 最后一步点「完成」：调 finishCookingSession 结束会话 → 提示成功 →
 * 清理本地缓存与 store → 回食材选择页。
 * @returns 无
 */
async function onFinish(): Promise<void> {
  if (!cookingStore.session || finishing.value) return
  finishing.value = true
  try {
    await finishCookingSession(cookingStore.session.id)
    ElMessage.success('做菜完成')
    cookingStore.clearSession()
    void router.push('/select')
  } catch (e) {
    ElMessage.error((e as ApiError).message || '完成失败，请重试')
  } finally {
    finishing.value = false
  }
}

/**
 * 底部主按钮点击：非最后一步 → 本地下一步；最后一步 → 完成会话。
 * @returns 无
 */
function onPrimaryAction(): void {
  if (isLast.value) {
    void onFinish()
  } else {
    void cookingStore.next()
  }
}

/**
 * 步骤列表抽屉点击跳转（本地切换 + 防抖持久化）。
 * @param no 目标步骤序号
 * @returns 无
 */
function onJump(no: number): void {
  drawerVisible.value = false
  void cookingStore.jumpTo(no)
}

/**
 * 恢复失败后的返回动作：回食材选择页。
 * @returns 无
 */
function goSelect(): void {
  void router.push('/select')
}

/* ═══ Task 9 增强 ⑦：多路计时器 ═══ */

/** 计时器抽屉可见性 */
const timerDrawerVisible = ref(false)
/** 全部计时器快照（onChange 同步，供渲染） */
const timerList = ref<TimerSnapshot[]>([])
/** 多路计时器实例（非响应式，状态经 onChange 同步到 timerList） */
const multiTimer = new MultiTimer((event) => {
  timerList.value = event.timers
  if (event.type === 'finish' && event.id != null) {
    const t = event.timers.find((x) => x.id === event.id)
    ElNotification({
      title: '计时结束',
      message: `「${t?.name ?? '计时器'}」时间到了，看看锅里的情况`,
      type: 'warning',
      duration: 8000,
    })
  }
})

/** 新计时器名称 */
const newTimerName = ref('')
/** 新计时器分钟数 */
const newTimerMinutes = ref(5)
/** 快捷预设（常用烹饪时长，≥3 路并行的典型场景） */
const QUICK_PRESETS: Array<{ name: string; minutes: number }> = [
  { name: '焯水', minutes: 1 },
  { name: '煎制', minutes: 3 },
  { name: '炖煮', minutes: 5 },
  { name: '焖煮', minutes: 8 },
  { name: '蒸制', minutes: 10 },
]
/** 是否有运行中计时（底部按钮角标） */
const hasRunningTimer = computed(() => timerList.value.some((t) => t.status === 'running'))

/**
 * 打开计时器抽屉。
 * @returns 无
 */
function openTimerDrawer(): void {
  timerDrawerVisible.value = true
}

/**
 * 新增一路计时（抽屉表单：名称 + 分钟数）。
 * @returns 无
 */
function addTimer(): void {
  const minutes = Number(newTimerMinutes.value)
  if (!Number.isFinite(minutes) || minutes <= 0 || minutes > 180) {
    ElMessage.warning('请输入 1~180 分钟之间的时长')
    return
  }
  const name = newTimerName.value.trim() || `计时 ${multiTimer.list().length + 1}`
  multiTimer.start(name, minutes * 60)
  newTimerName.value = ''
  newTimerMinutes.value = 5
}

/**
 * 新增快捷预设计时。
 * @param preset 预设项
 * @returns 无
 */
function addPreset(preset: { name: string; minutes: number }): void {
  multiTimer.start(`${preset.name} ${preset.minutes} 分钟`, preset.minutes * 60)
}

/**
 * 暂停某路计时。
 * @param id 计时器 ID
 * @returns 无
 */
function pauseTimer(id: number): void {
  multiTimer.pause(id)
}

/**
 * 恢复某路计时。
 * @param id 计时器 ID
 * @returns 无
 */
function resumeTimer(id: number): void {
  multiTimer.resume(id)
}

/**
 * 重置某路计时（回满量）。
 * @param id 计时器 ID
 * @returns 无
 */
function resetTimer(id: number): void {
  multiTimer.reset(id)
}

/**
 * 移除某路计时。
 * @param id 计时器 ID
 * @returns 无
 */
function clearTimer(id: number): void {
  multiTimer.clear(id)
}

/* ═══ Task 9 增强 ⑧：屏幕常亮（Wake Lock API）═══ */

/** Wake Lock 能力的最小类型视图（规避 lib.dom 版本差异，运行时特性检测） */
interface WakeLockSentinelLike {
  released: boolean
  release: () => Promise<void>
}
type NavigatorWithWakeLock = Navigator & {
  wakeLock?: { request: (type: 'screen') => Promise<WakeLockSentinelLike> }
}

/** 当前持有的 Wake Lock 句柄（null = 未持有/不支持） */
let wakeLockSentinel: WakeLockSentinelLike | null = null

/**
 * 申请屏幕常亮（try/catch 静默降级：不支持/被拒均不影响烹饪流程）。
 * @returns 无
 */
async function requestWakeLock(): Promise<void> {
  try {
    const nav = navigator as NavigatorWithWakeLock
    if (!nav.wakeLock || wakeLockSentinel) return
    wakeLockSentinel = await nav.wakeLock.request('screen')
  } catch {
    // 不支持或用户拒绝：静默降级，不提示打断做菜
    wakeLockSentinel = null
  }
}

/**
 * 释放屏幕常亮（页面离开/隐藏时调用）。
 * @returns 无
 */
async function releaseWakeLock(): Promise<void> {
  try {
    await wakeLockSentinel?.release()
  } catch {
    // 释放失败无需处理
  } finally {
    wakeLockSentinel = null
  }
}

/**
 * 页面可见性恢复时重新申请（系统在后台会自动释放 Wake Lock）。
 * @returns 无
 */
function onVisibilityChange(): void {
  if (document.visibilityState === 'visible') {
    void requestWakeLock()
  }
}

/* ═══ Task 9 增强 ⑨：烹饪求助 ═══ */

/** 求助弹窗可见性 */
const helpVisible = ref(false)
/** 求助问题输入 */
const helpQuestion = ref('')
/** 求助请求进行中 */
const helpLoading = ref(false)
/** 求助展示态：idle 输入 / answers 回答列表 / blocked 拦截话术 / limit 当日超限 */
const helpState = ref<'idle' | 'answers' | 'blocked' | 'limit'>('idle')
/** 回答列表 */
const helpAnswers = ref<string[]>([])
/** 拦截话术（blocked 时） */
const helpBlockedMessage = ref('')

/**
 * 打开求助弹窗（重置为输入态）。
 * @returns 无
 */
function openHelp(): void {
  helpQuestion.value = ''
  helpState.value = 'idle'
  helpAnswers.value = []
  helpBlockedMessage.value = ''
  helpVisible.value = true
}

/**
 * 提交求助：POST /v1/cooking/sessions/{id}/help。
 * - 正常 → 回答列表态；
 * - 返回体带 blocked → 拦截话术态；
 * - 429（当日超限）→ 超限提示态；其余错误 → ElMessage。
 * @returns 无
 */
async function onHelpSubmit(): Promise<void> {
  const question = helpQuestion.value.trim()
  if (!question || !cookingStore.session) return
  helpLoading.value = true
  try {
    const res = await postCookingHelp(cookingStore.session.id, question)
    if ('blocked' in res && res.blocked) {
      helpBlockedMessage.value = res.message ?? res.title ?? '该问题未通过安全检查，请换一种问法'
      helpState.value = 'blocked'
      return
    }
    helpAnswers.value = 'answers' in res ? (res.answers ?? []) : []
    helpState.value = 'answers'
  } catch (e) {
    const err = e as ApiError
    if (err.code === 429) {
      helpState.value = 'limit'
    } else {
      ElMessage.error(err.message || '求助失败，请重试')
    }
  } finally {
    helpLoading.value = false
  }
}

// 挂载即恢复会话：内存 store → 本地缓存；都无则提示并回 /select。
// 同步申请屏幕常亮（做菜过程锁屏会打断引导）。
onMounted(() => {
  const sessionId = route.params.sessionId as string
  const restored = cookingStore.restoreById(sessionId)
  if (!restored) {
    restoreFailed.value = true
    ElMessage.warning('未找到进行中的烹饪会话，请重新从菜谱发起')
    void router.replace('/select')
    return
  }
  void requestWakeLock()
  document.addEventListener('visibilitychange', onVisibilityChange)
})

// 卸载：释放 Wake Lock、停掉全部计时器、解绑可见性监听
onBeforeUnmount(() => {
  document.removeEventListener('visibilitychange', onVisibilityChange)
  void releaseWakeLock()
  multiTimer.clearAll()
})
</script>

<template>
  <section class="page-card cook-page">
    <!-- 恢复失败兜底（通常已被 replace 离开） -->
    <el-empty v-if="restoreFailed" description="会话不存在或已结束">
      <el-button type="primary" @click="goSelect">返回选食材</el-button>
    </el-empty>

    <!-- 步骤数据缺失兜底：会话在但步骤快照为空 -->
    <el-empty v-else-if="cookingStore.totalSteps === 0" description="步骤数据缺失，无法继续引导">
      <el-button type="primary" @click="goSelect">返回选食材</el-button>
    </el-empty>

    <template v-else>
      <!-- ① 顶部：过敏原警示条（冲突时）+ 退出 -->
      <div class="cook-top">
        <div class="cook-alert-slot">
          <AllergenAlertBar
            :allergens="cookingStore.session?.allergen_conflict ?? []"
            conflict
          />
        </div>
        <el-button class="cook-exit" size="large" @click="onExit">退出</el-button>
      </div>

      <!-- ② 进度：百分比 + 第 X 步 / 共 Y 步 -->
      <div class="cook-progress">
        <el-progress
          class="cook-progress-bar"
          :percentage="progressPercent"
          :stroke-width="14"
          :format="() => `${progressPercent}%`"
        />
        <span class="cook-progress-text">第 {{ cookingStore.currentStepNo }} 步 / 共 {{ cookingStore.totalSteps }} 步</span>
      </div>

      <!-- ③ 主体大字步骤 -->
      <div class="cook-main">
        <p class="cook-step-no">第 {{ currentStep?.no }} 步</p>
        <!-- 大字 ≥32px：灶台 50cm 可读 -->
        <p class="cook-step-text">{{ currentStep?.description }}</p>
        <!-- 本步用量提示 ≥20px -->
        <p v-if="currentStep?.amount_hint" class="cook-amount-hint">
          本步用量：{{ currentStep.amount_hint }}
        </p>
        <p class="cook-duration">⏱ 预计耗时：{{ formatDuration(currentStep?.duration_sec ?? 0) }}</p>

        <!-- ④ 新手要点区：要点 + 失败补救（折叠可展开） -->
        <el-collapse v-if="currentStep?.tips || currentStep?.rescue" class="cook-tips">
          <el-collapse-item title="新手要点 / 失败补救" name="tips">
            <p v-if="currentStep?.tips" class="cook-tip-line">要点：{{ currentStep.tips }}</p>
            <p v-if="currentStep?.rescue" class="cook-tip-line">失败补救：{{ currentStep.rescue }}</p>
          </el-collapse-item>
        </el-collapse>
      </div>

      <!-- ⑤ 底部操作：上一步 / 下一步（本地切换）+ 计时器 / 求助 / 步骤列表 -->
      <div class="cook-actions">
        <el-button
          class="cook-btn"
          size="large"
          :disabled="cookingStore.currentStepNo <= 1"
          @click="cookingStore.prev()"
        >
          上一步
        </el-button>
        <el-button
          class="cook-btn cook-btn--primary"
          type="primary"
          size="large"
          :loading="finishing"
          @click="onPrimaryAction"
        >
          {{ isLast ? '完成' : '下一步' }}
        </el-button>
        <el-button class="cook-btn" size="large" @click="openTimerDrawer">
          <el-icon v-if="hasRunningTimer" class="cook-btn-icon"><TimerIcon /></el-icon>
          计时器
        </el-button>
        <el-button class="cook-btn" size="large" @click="openHelp">求助</el-button>
        <el-button class="cook-btn" size="large" @click="drawerVisible = true">步骤列表</el-button>
      </div>

      <!-- ⑥ 步骤列表抽屉：全量步骤可点击跳转 -->
      <el-drawer v-model="drawerVisible" title="步骤列表" size="380px">
        <div
          v-for="step in cookingStore.steps"
          :key="step.no"
          class="drawer-step"
          :class="{ 'drawer-step--active': step.no === cookingStore.currentStepNo }"
          role="button"
          @click="onJump(step.no)"
        >
          <span class="drawer-step-no">第 {{ step.no }} 步</span>
          <span class="drawer-step-desc">{{ step.description }}</span>
        </div>
      </el-drawer>

      <!-- ⑦ 多路计时器抽屉（右下，≥3 路并行倒计时） -->
      <el-drawer v-model="timerDrawerVisible" title="并行计时器" size="380px" direction="rtl">
        <!-- 快捷预设 -->
        <p class="timer-label">快捷计时：</p>
        <div class="timer-presets">
          <el-button
            v-for="p in QUICK_PRESETS"
            :key="p.name"
            size="small"
            @click="addPreset(p)"
          >
            {{ p.name }} {{ p.minutes }} 分钟
          </el-button>
        </div>

        <!-- 自定义计时 -->
        <div class="timer-form">
          <el-input v-model="newTimerName" size="small" maxlength="12" placeholder="名称（可选）" class="timer-name" />
          <el-input-number v-model="newTimerMinutes" :min="1" :max="180" size="small" controls-position="right" class="timer-min" />
          <span class="timer-unit">分钟</span>
          <el-button type="primary" size="small" @click="addTimer">开始</el-button>
        </div>

        <el-divider />

        <!-- 计时列表 -->
        <el-empty v-if="timerList.length === 0" description="还没有计时，先加一路" :image-size="64" />
        <div v-else class="timer-list">
          <div
            v-for="t in timerList"
            :key="t.id"
            class="timer-item"
            :class="{ 'timer-item--done': t.status === 'finished' }"
          >
            <div class="timer-head">
              <span class="timer-name">{{ t.name }}</span>
              <el-tag size="small" :type="t.status === 'finished' ? 'danger' : t.status === 'paused' ? 'info' : 'success'">
                {{ t.status === 'finished' ? '已结束' : t.status === 'paused' ? '已暂停' : '计时中' }}
              </el-tag>
            </div>
            <p class="timer-remaining" :class="{ 'timer-remaining--done': t.status === 'finished' }">
              {{ formatCountdown(t.remainingSec) }}
            </p>
            <div class="timer-actions">
              <el-button v-if="t.status === 'running'" size="small" @click="pauseTimer(t.id)">暂停</el-button>
              <el-button v-if="t.status === 'paused'" size="small" type="primary" @click="resumeTimer(t.id)">继续</el-button>
              <el-button size="small" @click="resetTimer(t.id)">重置</el-button>
              <el-button size="small" type="danger" plain @click="clearTimer(t.id)">移除</el-button>
            </div>
          </div>
        </div>
      </el-drawer>

      <!-- ⑨ 求助弹窗：输入 → 回答列表 / 拦截话术 / 超限提示 三态 -->
      <el-dialog v-model="helpVisible" title="做菜求助" width="440px" align-center>
        <!-- 输入态 -->
        <el-input
          v-if="helpState === 'idle'"
          v-model="helpQuestion"
          type="textarea"
          :rows="3"
          maxlength="100"
          placeholder="卡住了？问问厨娘，如：糖色炒苦了还能救吗"
        />

        <!-- 回答列表态 -->
        <div v-else-if="helpState === 'answers'" class="help-answers">
          <p v-if="helpAnswers.length === 0" class="help-empty">厨娘暂时没有好建议，请注意安全操作</p>
          <div v-for="(a, i) in helpAnswers" :key="i" class="help-answer">
            {{ a }}
          </div>
        </div>

        <!-- 拦截话术态 -->
        <el-alert
          v-else-if="helpState === 'blocked'"
          type="warning"
          title="该问题未通过安全检查"
          :description="helpBlockedMessage"
          :closable="false"
          show-icon
        />

        <!-- 当日超限态 -->
        <el-alert
          v-else
          type="info"
          title="今日求助次数已用完"
          description="今天的求助额度用完了，明天再来问吧；紧急情况请先关火处理，安全第一。"
          :closable="false"
          show-icon
        />

        <template #footer>
          <template v-if="helpState === 'idle'">
            <el-button @click="helpVisible = false">取消</el-button>
            <el-button type="primary" :loading="helpLoading" @click="onHelpSubmit">发送求助</el-button>
          </template>
          <template v-else-if="helpState === 'answers'">
            <el-button @click="helpState = 'idle'">再问一个</el-button>
            <el-button type="primary" @click="helpVisible = false">好的</el-button>
          </template>
          <template v-else-if="helpState === 'blocked'">
            <el-button @click="helpState = 'idle'">换个问法</el-button>
            <el-button type="primary" @click="helpVisible = false">知道了</el-button>
          </template>
          <template v-else>
            <el-button type="primary" @click="helpVisible = false">知道了</el-button>
          </template>
        </template>
      </el-dialog>
    </template>
  </section>
</template>

<style scoped>
.cook-page {
  min-height: calc(100vh - var(--header-height) - 88px);
  display: flex;
  flex-direction: column;
}

/* ── 顶部：警示条 + 退出 ── */
.cook-top {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
}

.cook-alert-slot {
  flex: 1;
  min-width: 0;
}

/* 无冲突时警示条不渲染，占位避免退出按钮跳动 */
.cook-alert-slot:empty {
  display: none;
}

.cook-exit {
  flex-shrink: 0;
  min-height: 44px;
}

/* ── 进度 ── */
.cook-progress {
  display: flex;
  align-items: center;
  gap: 14px;
  margin: 16px 0 8px;
}

.cook-progress-bar {
  flex: 1;
}

.cook-progress-text {
  flex-shrink: 0;
  font-size: var(--font-md);
  font-weight: 600;
  color: var(--text-main);
}

/* ── 主体大字 ── */
.cook-main {
  flex: 1;
  display: flex;
  flex-direction: column;
  justify-content: center;
  padding: 20px 8px;
  text-align: center;
}

.cook-step-no {
  margin: 0 0 12px;
  font-size: var(--font-md);
  color: var(--color-info);
}

/* 烹饪专档大字：≥32px（50cm 可读），深浅模式均用主文字色保证对比度 */
.cook-step-text {
  margin: 0 auto 16px;
  max-width: 720px;
  font-size: 34px;
  font-weight: 700;
  line-height: 1.6;
  color: var(--text-main);
  overflow-wrap: anywhere;
}

/* 本步用量提示 ≥20px */
.cook-amount-hint {
  margin: 0 auto 12px;
  max-width: 720px;
  font-size: 21px;
  font-weight: 600;
  line-height: 1.6;
  color: var(--color-warning);
}

.cook-duration {
  margin: 0 auto 8px;
  font-size: var(--font-lg);
  color: var(--text-main);
}

.cook-tips {
  max-width: 720px;
  margin: 12px auto 0;
  text-align: left;
}

.cook-tip-line {
  margin: 6px 0;
  font-size: var(--font-md);
  line-height: 1.8;
  color: var(--text-main);
}

/* ── 底部操作：大按钮（≥44pt 点击区域）── */
.cook-actions {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 18px;
  padding: 12px 0 4px;
}

.cook-btn {
  min-width: 132px;
  min-height: 52px;
  font-size: var(--font-lg);
}

.cook-btn--primary {
  min-width: 160px;
}

/* ── 步骤抽屉 ── */
.drawer-step {
  display: flex;
  flex-direction: column;
  gap: 4px;
  padding: 12px 14px;
  margin-bottom: 8px;
  border: 1px solid var(--color-info-border);
  border-radius: 8px;
  cursor: pointer;
}

.drawer-step--active {
  border-color: var(--el-color-primary);
  background: var(--el-color-primary-light-9);
}

.drawer-step-no {
  font-size: var(--font-sm);
  font-weight: 600;
  color: var(--el-color-primary);
}

.drawer-step-desc {
  font-size: var(--font-md);
  line-height: 1.6;
  color: var(--text-main);
}

/* ── Task 9 ⑦：计时器抽屉 ── */
.cook-btn-icon {
  margin-right: 4px;
}

.timer-label {
  margin: 0 0 8px;
  font-size: var(--font-sm);
  color: var(--color-info);
}

.timer-presets {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-bottom: 14px;
}

.timer-form {
  display: flex;
  align-items: center;
  gap: 8px;
}

.timer-name {
  flex: 1;
}

.timer-min {
  width: 96px;
}

.timer-unit {
  flex-shrink: 0;
  font-size: var(--font-sm);
  color: var(--color-info);
}

.timer-list {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.timer-item {
  padding: 12px 14px;
  border: 1px solid var(--color-info-border);
  border-radius: 10px;
}

.timer-item--done {
  border-color: var(--color-danger-border);
  background: var(--color-danger-bg);
}

.timer-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
}

.timer-name {
  font-weight: 600;
  color: var(--text-main);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.timer-remaining {
  margin: 8px 0;
  font-size: 32px;
  font-weight: 700;
  font-variant-numeric: tabular-nums;
  color: var(--text-main);
  text-align: center;
}

.timer-remaining--done {
  color: var(--color-danger);
}

.timer-actions {
  display: flex;
  gap: 6px;
}

/* ── Task 9 ⑨：求助弹窗 ── */
.help-answers {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.help-answer {
  padding: 10px 12px;
  border: 1px solid var(--color-info-border);
  border-radius: 8px;
  background: var(--color-info-bg);
  font-size: var(--font-md);
  line-height: 1.7;
  color: var(--text-main);
}

.help-empty {
  margin: 0;
  font-size: var(--font-sm);
  color: var(--color-info);
}
</style>
