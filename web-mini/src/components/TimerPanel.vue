<script setup lang="ts">
/**
 * 文件级注释：多路计时器面板（业务组件，烹饪引导页并行倒计时）。
 * 自 web-stage1 W-04 CookGuideView 计时区语义迁移：
 * - 数据源为 @shared/utils 的 TimerSnapshot[]（MultiTimer.list() 快照，页面驱动传入）；
 * - 组件内 200ms 心跳自刷新展示（onUnmounted 清理）：running 且带 dueAt 的计时器按
 *   绝对到期时间戳校准真实剩余（等价 getRemainingMs(t.dueAt) 的 Date.now() 口径，
 *   且纳入响应式 now 依赖），暂停/完成态展示快照 remainingSec（formatCountdown）；
 * - 每行：名称 + 剩余倒计时 + 删除按钮（emit remove(id)，热区 ≥88rpx）+ 新增按钮（emit add）；
 * - 空态提示（无计时器时）。
 * 使用约束：由页面根 .page/.dark 提供主题变量上下文。
 */
import { computed, onMounted, onUnmounted, ref } from 'vue'
import type { TimerSnapshot } from '@shared/utils/timer'
import { formatCountdown, formatRemainingMs } from '@shared/utils/timer'

/** 组件入参 */
const props = defineProps<{
  /** 计时器快照列表（页面驱动传入，组件内每 200ms 依 dueAt 校准展示） */
  timers: TimerSnapshot[]
}>()

/** 删除某路计时事件（参数 id 为 TimerSnapshot.id；页面调 MultiTimer.clear） */
const emit = defineEmits<{
  (e: 'remove', id: number): void
  (e: 'add'): void
}>()

/** 展示心跳基准时间（200ms 更新一次，驱动剩余时间重算） */
const now = ref(Date.now())

/** 心跳定时器句柄（null = 未启动；ReturnType 兼容各端计时器类型） */
let tickHandle: ReturnType<typeof setInterval> | null = null

// 挂载：启动 200ms 展示心跳
onMounted(() => {
  tickHandle = setInterval(() => {
    now.value = Date.now()
  }, 200)
})

// 卸载：清理心跳（组件内定时器必须自清，防泄漏）
onUnmounted(() => {
  if (tickHandle) {
    clearInterval(tickHandle)
    tickHandle = null
  }
})

/**
 * 单路计时器剩余展示文案。
 * - running 且有 dueAt：按绝对到期时间戳校准（切后台回前台后仍准确）；
 * - 其他（暂停/完成/无 dueAt）：展示快照 remainingSec。
 * @param t 计时器快照
 * @returns 「mm:ss」或「h:mm:ss」文案
 */
function remainingText(t: TimerSnapshot): string {
  // 读取 now 建立 200ms 心跳响应依赖（口径等价 getRemainingMs(t.dueAt)）
  void now.value
  if (t.status === 'running' && typeof t.dueAt === 'number') {
    return formatRemainingMs(t.dueAt - now.value)
  }
  return formatCountdown(t.remainingSec)
}

/** 空态判定（无任何计时器；computed 保持随 props 更新） */
const isEmpty = computed(() => props.timers.length === 0)

/**
 * 点击行内删除按钮：emit remove(id)（页面调 MultiTimer.clear(id)）。
 * @param id 计时器 ID
 * @returns 无
 */
function onRemove(id: number): void {
  emit('remove', id)
}

/**
 * 点击新增：emit add（页面决定新增默认计时或弹输入）。
 * @returns 无
 */
function onAdd(): void {
  emit('add')
}
</script>

<template>
  <view class="timer-panel">
    <!-- 空态提示 -->
    <view v-if="isEmpty" class="timer-panel__empty">
      <text class="timer-panel__empty-text">暂无计时器，点击下方按钮添加</text>
    </view>

    <!-- 计时器行：名称 + 剩余 + 删除 -->
    <view v-for="t in timers" :key="t.id" class="timer-panel__row">
      <view class="timer-panel__info">
        <text class="timer-panel__name">{{ t.name }}</text>
        <text class="timer-panel__status">
          {{ t.status === 'running' ? '计时中' : t.status === 'paused' ? '已暂停' : '已完成' }}
        </text>
      </view>
      <text class="timer-panel__remaining" :class="{ 'is-finished': t.status === 'finished' }">
        {{ remainingText(t) }}
      </text>
      <view class="timer-panel__remove" @click="onRemove(t.id)">删除</view>
    </view>

    <!-- 新增计时器按钮：热区 ≥88rpx -->
    <view class="timer-panel__add" @click="onAdd">＋ 添加计时器</view>
  </view>
</template>

<style scoped lang="scss">
.timer-panel {
  box-sizing: border-box;
  display: block;
  width: 100%;
}

.timer-panel__empty {
  display: flex;
  justify-content: center;
  padding: var(--space-lg) 0;
}

.timer-panel__empty-text {
  font-size: var(--font-size-sm);
  color: var(--text-tertiary);
}

.timer-panel__row {
  box-sizing: border-box;
  display: flex;
  align-items: center;
  min-height: var(--hit-min);
  padding: var(--space-xs) var(--space-sm);
  border-radius: var(--radius-ctrl);
  background: var(--bg-card);
  border: 1rpx solid var(--border-color);
  margin-bottom: var(--space-sm);
}

.timer-panel__info {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
}

.timer-panel__name {
  font-size: var(--font-size-base);
  font-weight: 600;
  line-height: 1.4;
  color: var(--text-primary);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.timer-panel__status {
  font-size: var(--font-size-sm);
  line-height: 1.4;
  color: var(--text-tertiary);
}

.timer-panel__remaining {
  font-size: var(--font-size-lg);
  font-weight: 600;
  color: var(--color-primary);
  font-variant-numeric: tabular-nums;
  margin: 0 var(--space-sm);

  /* 已完成：中性弱化 */
  &.is-finished {
    color: var(--text-tertiary);
  }
}

/* 删除按钮：热区 ≥88rpx */
.timer-panel__remove {
  box-sizing: border-box;
  display: flex;
  align-items: center;
  justify-content: center;
  min-width: var(--hit-min);
  min-height: var(--hit-min);
  border-radius: var(--radius-ctrl);
  background: var(--color-danger-bg);
  color: var(--color-danger);
  font-size: var(--font-size-sm);
}

/* 新增按钮：热区 ≥88rpx */
.timer-panel__add {
  display: flex;
  align-items: center;
  justify-content: center;
  min-height: var(--hit-min);
  border-radius: var(--radius-ctrl);
  border: 2rpx dashed var(--border-color);
  color: var(--color-info);
  font-size: var(--font-size-sm);
}
</style>
