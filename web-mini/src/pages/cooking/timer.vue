<!--
  文件级注释：P-16 计时器页（多路并发 ≥3 路，W-04 计时区拆页落点）。
  自 web-stage1 CookGuideView 计时抽屉语义迁移，状态与校准机制：
  - 状态承载：页面内 MultiTimer 实例（@shared/utils/timer）+ storage 持久化
    cook_timers_{session_id}（断点续做语义对齐：退出页面计时仍在，重进恢复续跑）；
  - 后台校准（5 分钟误差 ≤3s 机制）：每路计时以 dueAt 绝对时间戳（Date.now() 口径）
    为权威——小程序切后台 setInterval 心跳被冻结，onShow 回前台时以
    getRemainingMs(dueAt) 差值重算真实剩余：
      · rem ≤ 0：已到期 → 补提示（vibrate + playAlertSound +「计时已到」弹层），
        条目按完成态清理（不恢复，finished 持久化过滤）；
      · rem 与快照 remainingSec 偏差 >1s：clear + start(name, rem) 重建校准
        （重建一次完成对齐，无累积误差——绝对时间戳保证回前台校准只做一次）；
  - 页面 onHide：timers 持久化 + flush 埋点（渲染心跳 TimerPanel 组件内自停——
    页面隐藏组件不渲染）；onShow：恢复/校准 + 过期补提示；
  - 完成提醒：页面内到期（finish 事件）→ playAlertSound + vibrate + 弹层；
  - 首次使用边界告知：storage 检查 timer_boundary_noted，未记录 → BaseDialog 一次性
    展示 TIMER_BOUNDARY_NOTE（切后台提醒可能延迟，建议停留小程序内）；
  - 订阅消息增强：添加计时器时 requestTimerSubscribe()（拒绝/未配置模板静默，
    PRD-Q-6 本地提醒为主路径），授权成功 trackEvent('subscribe_click')；
  - UI：TimerPanel（200ms 心跳展示 + dueAt 校准）+ 添加表单（分钟 + 名称可选）+
    快捷时长 chips（对齐源码 QUICK_PRESETS：焯水 1 / 煎制 3 / 炖煮 5 / 焖煮 8 / 蒸制 10）。
-->
<script setup lang="ts">
import { computed, ref } from 'vue'
import { onHide, onLoad, onShow, onUnload } from '@dcloudio/uni-app'
import { MultiTimer, getRemainingMs, type TimerSnapshot } from '@shared/utils/timer'
import { TIMER_BOUNDARY_NOTE } from '@shared/constants'
import { requestTimerSubscribe } from '@/platform/subscribe'
import { vibrate, playAlertSound } from '@/platform/device'
import { get as storageGet, set as storageSet } from '@/utils/storage'
import { toastWarning } from '@/utils/toast'
import { trackEvent, flushOnHide } from '@/utils/track'
import { useTheme } from '@/platform/theme'
import { useFontSize } from '@/platform/fontSize'
import TimerPanel from '@/components/TimerPanel.vue'
import BaseButton from '@/components-base/BaseButton.vue'
import BaseInput from '@/components-base/BaseInput.vue'
import BaseDialog from '@/components-base/BaseDialog.vue'

/** 计时器持久化键前缀（key = cook_timers_{sessionId}，断点续做语义） */
const TIMERS_KEY_PREFIX = 'cook_timers_'

/** 首次使用边界告知记忆键（一次性展示 TIMER_BOUNDARY_NOTE） */
const BOUNDARY_NOTED_KEY = 'timer_boundary_noted'

/** 快捷时长预设（对齐源码 QUICK_PRESETS：常用烹饪时长，≥3 路并行典型场景） */
const QUICK_PRESETS: Array<{ name: string; minutes: number }> = [
  { name: '焯水', minutes: 1 },
  { name: '煎制', minutes: 3 },
  { name: '炖煮', minutes: 5 },
  { name: '焖煮', minutes: 8 },
  { name: '蒸制', minutes: 10 },
]

/** 深色模式标记（根节点 class） */
const { isDark } = useTheme()
/** 字号档位 class（根节点 class） */
const { fontSizeClass } = useFontSize()

/** 路由注入的会话 ID（持久化键隔离；缺省 'local'） */
const sessionId = ref('local')

/** 持久化键（随 sessionId 变化） */
const timersKey = computed(() => `${TIMERS_KEY_PREFIX}${sessionId.value}`)

/** 计时器快照列表（MultiTimer onChange 同步，TimerPanel 渲染数据源） */
const timerList = ref<TimerSnapshot[]>([])

/** 多路计时器实例（页面级；到期 finish 事件触发提醒） */
const multiTimer = new MultiTimer((event) => {
  timerList.value = event.timers
  if (event.type === 'finish' && event.id != null) {
    // 页面内到期提醒：提醒音 + 震动 + 弹层（本地提醒为主路径，PRD-Q-6）
    playAlertSound()
    vibrate()
    expiredNames.value.push(timerList.value.find((t) => t.id === event.id)?.name ?? '计时器')
    expiredDialogVisible.value = true
    // 完成态持久化清理（finished 条目不落盘）
    persistTimers()
  }
})

/** 新计时器名称（可选） */
const newTimerName = ref('')

/** 新计时器分钟数（数字输入；快捷 chips / guide 页 quickTimer 传参预填） */
const newTimerMinutes = ref('5')

/** 是否存在运行中计时（提示条展示） */
const hasRunning = computed(() => timerList.value.some((t) => t.status === 'running'))

/** 「计时已到」弹层可见性（到期项名单展示） */
const expiredDialogVisible = ref(false)

/** 本轮到期计时器名称列表（弹层文案） */
const expiredNames = ref<string[]>([])

/** 首次边界告知弹层可见性（一次性） */
const boundaryDialogVisible = ref(false)

/** 恢复时收集的过期项（onShow 补提示去重用） */
const pendingExpired = ref<string[]>([])

/**
 * 持久化计时器快照（函数）。
 * running（含 dueAt 绝对时间戳）/ paused 条目落盘；finished 条目过滤
 * （完成态持久化清理，恢复时不再展示已完成项）。
 * @returns 无
 * @throws 不抛出（storage 内部静默降级）
 */
function persistTimers(): void {
  const snapshot = timerList.value
    .filter((t) => t.status === 'running' || t.status === 'paused')
    .map((t) => ({ ...t }))
  storageSet(timersKey.value, snapshot)
}

/**
 * 从 storage 恢复计时器（onLoad 首次进入时调用，函数）。
 * 恢复策略（断点续做语义）：
 * - running 且 rem > 0：multiTimer.start(name, rem) 续跑（dueAt 按 now+rem 重算，
 *   与原 dueAt 差 ≤1s，校准机制兜底）；
 * - running 且 rem ≤ 0：已过期 → 记入 pendingExpired（onShow 补提示），不恢复；
 * - paused：按剩余量 start 后立即 pause（源码无暂停恢复场景，总时长近似为剩余量，
 *   注释说明降级语义）；
 * - finished：不恢复（完成态持久化清理）。
 * @returns 无
 * @throws 不抛出（缓存损坏 / 非法条目逐条跳过）
 */
function restoreTimers(): void {
  const cached = storageGet<TimerSnapshot[]>(timersKey.value, [])
  if (!Array.isArray(cached) || cached.length === 0) return
  for (const t of cached) {
    if (!t || typeof t.name !== 'string' || typeof t.durationSec !== 'number') continue
    if (t.status === 'running' && typeof t.dueAt === 'number') {
      const remSec = Math.ceil(getRemainingMs(t.dueAt) / 1000)
      if (remSec > 0) {
        multiTimer.start(t.name, remSec, t.repeat)
      } else {
        // 后台期间已到期：补提示名单，条目按完成态清理
        pendingExpired.value.push(t.name)
      }
    } else if (t.status === 'paused' && t.remainingSec > 0) {
      // 暂停恢复：按剩余量重建后立即暂停（总时长近似为剩余量，降级语义）
      const id = multiTimer.start(t.name, t.remainingSec, t.repeat)
      if (id != null) multiTimer.pause(id)
    }
    // finished：完成态清理，不恢复
  }
  if (pendingExpired.value.length > 0) {
    expiredNames.value = [...pendingExpired.value]
    expiredDialogVisible.value = true
    playAlertSound()
    vibrate()
    pendingExpired.value = []
    persistTimers()
  }
}

/**
 * 回前台校准（onShow 调用）：逐条以 getRemainingMs(dueAt) 重算真实剩余。
 * 校准只发生一次（绝对时间戳权威），5 分钟计时后台停留误差 ≤3s（心跳冻结不累积）。
 * @returns 无
 * @throws 不抛出
 */
function resyncFromDueAt(): void {
  const expired: string[] = []
  for (const t of multiTimer.list()) {
    if (t.status !== 'running' || typeof t.dueAt !== 'number') continue
    const remSec = Math.ceil(getRemainingMs(t.dueAt) / 1000)
    if (remSec <= 0) {
      // 后台已到期：补提示 + 移除（完成态清理）
      multiTimer.clear(t.id)
      expired.push(t.name)
      continue
    }
    if (Math.abs(remSec - t.remainingSec) > 1) {
      // 心跳冻结偏移：重建校准（clear + start 按真实剩余量，误差 ≤1s）
      multiTimer.clear(t.id)
      multiTimer.start(t.name, remSec, t.repeat)
    }
  }
  if (expired.length > 0) {
    expiredNames.value = expired
    expiredDialogVisible.value = true
    playAlertSound()
    vibrate()
    persistTimers()
  }
}

/**
 * 添加一路计时（表单提交）：校验 1~180 分钟 → multiTimer.start →
 * 订阅消息授权（拒绝/未配置静默）→ 重置表单。
 * @returns 无
 */
function addTimer(): void {
  const minutes = Number(newTimerMinutes.value)
  if (!Number.isFinite(minutes) || minutes <= 0 || minutes > 180) {
    toastWarning('请输入 1~180 分钟之间的时长')
    return
  }
  const name = newTimerName.value.trim() || `计时 ${multiTimer.list().length + 1}`
  multiTimer.start(name, minutes * 60)
  newTimerName.value = ''
  newTimerMinutes.value = '5'
  // 订阅消息增强（PRD-Q-6）：添加计时器时请求授权；拒绝/失败/模板未配置静默返回 false，
  // 用户点击授权同意才上报 subscribe_click（本地提醒始终为主路径，不阻断）
  void requestTimerSubscribe().then((accepted) => {
    if (accepted) trackEvent('subscribe_click', { session_id: sessionId.value })
  })
}

/**
 * 添加快捷预设计时（chips 点击）。
 * @param preset 预设项（name + minutes）
 * @returns 无
 */
function addPreset(preset: { name: string; minutes: number }): void {
  multiTimer.start(`${preset.name} ${preset.minutes} 分钟`, preset.minutes * 60)
  void requestTimerSubscribe().then((accepted) => {
    if (accepted) trackEvent('subscribe_click', { session_id: sessionId.value })
  })
}

/**
 * 移除某路计时（TimerPanel remove emit 落点）+ 持久化同步。
 * @param id 计时器 ID
 * @returns 无
 */
function onRemoveTimer(id: number): void {
  multiTimer.clear(id)
  persistTimers()
}

/**
 * 「计时已到」弹层确认：关闭弹层并持久化清理。
 * @returns 无
 */
function onExpiredConfirm(): void {
  expiredDialogVisible.value = false
  expiredNames.value = []
  persistTimers()
}

/**
 * 首次边界告知确认：写记忆键（一次性），之后不再弹。
 * @returns 无
 */
function onBoundaryConfirm(): void {
  boundaryDialogVisible.value = false
  storageSet(BOUNDARY_NOTED_KEY, true)
}

/**
 * onLoad：解析 session_id（guide 页 quickTimer 可带 minutes 快捷预填）→
 * 恢复持久化计时器 → 首次边界告知检查。
 * @param options 页面参数（session_id 可选；minutes 可选快捷预填）
 * @returns 无
 * @throws 不抛出
 */
onLoad((options) => {
  const sid = options?.session_id ? decodeURIComponent(options.session_id) : ''
  sessionId.value = sid || 'local'
  const quickMinutes = Number(options?.minutes)
  if (Number.isFinite(quickMinutes) && quickMinutes > 0 && quickMinutes <= 180) {
    newTimerMinutes.value = String(quickMinutes)
  }
  restoreTimers()
  if (!storageGet<boolean>(BOUNDARY_NOTED_KEY, false)) {
    boundaryDialogVisible.value = true
  }
})

// onShow：回前台立即重算（getRemainingMs(dueAt) 绝对时间戳校准）+ 过期补提示
onShow(() => {
  resyncFromDueAt()
})

/**
 * onHide：停止渲染更新（TimerPanel 组件内心跳随组件不可见自停——页面隐藏不触发渲染），
 * timers 持久化 + flush 埋点。
 * @returns 无
 * @throws 不抛出
 */
onHide(() => {
  persistTimers()
  flushOnHide()
})

/**
 * onUnload：timers 持久化（下次进入恢复续跑，计时语义以 dueAt 绝对时间戳为准）。
 * @returns 无
 * @throws 不抛出
 */
onUnload(() => {
  persistTimers()
})
</script>

<template>
  <view class="page" :class="[isDark ? 'dark' : '', fontSizeClass]">
    <view class="timer">
      <!-- 状态提示条：有运行中计时 + 边界说明（TIMER_BOUNDARY_NOTE 常量） -->
      <view v-if="hasRunning" class="timer__notice">
        <text class="timer__notice-text">{{ TIMER_BOUNDARY_NOTE }}</text>
      </view>

      <!-- 计时器面板：200ms 心跳展示 + dueAt 校准（组件内实现） -->
      <TimerPanel :timers="timerList" @remove="onRemoveTimer" @add="() => {}" />

      <!-- 快捷时长 chips（对齐源码 QUICK_PRESETS） -->
      <view class="timer__section">
        <text class="timer__label">快捷计时</text>
        <view class="timer__chips">
          <view
            v-for="p in QUICK_PRESETS"
            :key="p.name"
            class="timer__chip"
            @click="addPreset(p)"
          >
            {{ p.name }} {{ p.minutes }} 分钟
          </view>
        </view>
      </view>

      <!-- 添加表单：分钟（数字）+ 名称（可选） -->
      <view class="timer__section">
        <text class="timer__label">自定义计时</text>
        <view class="timer__form">
          <view class="timer__form-minutes">
            <BaseInput v-model="newTimerMinutes" type="number" placeholder="分钟" :maxlength="3" />
          </view>
          <view class="timer__form-name">
            <BaseInput v-model="newTimerName" type="text" placeholder="名称（可选）" :maxlength="12" />
          </view>
          <BaseButton @click="addTimer">开始</BaseButton>
        </view>
      </view>

      <!-- 「计时已到」弹层：到期补提示（回前台检测 / 页面内 finish 事件双路径共用） -->
      <BaseDialog
        :visible="expiredDialogVisible"
        title="计时已到"
        position="center"
        :mask-closable="false"
        @close="onExpiredConfirm"
      >
        <view class="timer__expired">
          <text class="timer__expired-text">
            {{ expiredNames.join('、') }}时间到了，看看锅里的情况
          </text>
          <BaseButton block @click="onExpiredConfirm">知道了</BaseButton>
        </view>
      </BaseDialog>

      <!-- 首次使用边界告知（一次性，TIMER_BOUNDARY_NOTE 常量逐字展示） -->
      <BaseDialog
        :visible="boundaryDialogVisible"
        title="计时提醒说明"
        position="center"
        @close="onBoundaryConfirm"
      >
        <view class="timer__expired">
          <text class="timer__expired-text">{{ TIMER_BOUNDARY_NOTE }}</text>
          <BaseButton block @click="onBoundaryConfirm">知道了</BaseButton>
        </view>
      </BaseDialog>
    </view>
  </view>
</template>

<style scoped lang="scss">
.timer {
  box-sizing: border-box;
  display: flex;
  flex-direction: column;
  gap: var(--space-md);
  padding: var(--space-md);
  padding-bottom: calc(var(--space-xl) + env(safe-area-inset-bottom));
}

/* 边界提示条 */
.timer__notice {
  box-sizing: border-box;
  padding: var(--space-xs) var(--space-sm);
  border-radius: var(--radius-ctrl);
  background: var(--color-info-bg);
}

.timer__notice-text {
  font-size: var(--font-size-sm);
  line-height: 1.6;
  color: var(--color-info);
}

/* 区块标题 */
.timer__section {
  display: flex;
  flex-direction: column;
  gap: var(--space-sm);
}

.timer__label {
  font-size: var(--font-size-sm);
  color: var(--text-secondary);
}

/* 快捷 chips */
.timer__chips {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-sm);
}

.timer__chip {
  display: flex;
  align-items: center;
  justify-content: center;
  min-height: var(--hit-min);
  padding: 0 var(--space-md);
  border-radius: 999rpx;
  border: 1rpx solid var(--border-color);
  background: var(--bg-card);
  font-size: var(--font-size-sm);
  color: var(--text-primary);
}

/* 添加表单 */
.timer__form {
  display: flex;
  align-items: center;
  gap: var(--space-sm);
}

.timer__form-minutes {
  flex-shrink: 0;
  width: 160rpx;
}

.timer__form-name {
  flex: 1;
  min-width: 0;
}

/* 弹层内容 */
.timer__expired {
  display: flex;
  flex-direction: column;
  gap: var(--space-md);
  padding: var(--space-sm) 0;
}

.timer__expired-text {
  font-size: var(--font-size-base);
  line-height: 1.6;
  color: var(--text-primary);
}
</style>
