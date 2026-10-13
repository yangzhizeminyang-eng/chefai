<script setup lang="ts">
/**
 * 文件级注释：营养环形占比图（业务组件）。
 * 阶段一营养区（MeView/RecipeDetailView 营养块）占比语义迁移为小程序轻量环图：
 * - conic-gradient + 内圆遮罩（::after 挖空）实现环形比例，不引入第三方图表；
 *   兼容性说明：极低版本基础库不支持 conic-gradient 时整环退化为底色，比例语义
 *   由下方图例列表完整承载（退化为比例条亦可接受，页面可自行换用条形布局）；
 * - items 项带 percent（>0）按 percent 直取；否则按 value 占总和归一化计算；
 * - 颜色按语义变量循环取（primary/info/warning/success/danger），深浅色自动适配；
 * - 下方图例列表（色点 + label + value + unit）；无数据渲染空态。
 * 使用约束：由页面根 .page/.dark 提供主题变量上下文。
 */
import { computed } from 'vue'

/** 营养环图条目 */
export interface NutritionRingItem {
  /** 营养素名（如「蛋白质」） */
  label: string
  /** 数值（如 35；percent 缺省时按 value 归一化算占比） */
  value: number
  /** 单位（如「g」） */
  unit: string
  /** 已算好的百分比（可选，0~100；提供则优先于 value 归一化） */
  percent?: number
}

/** 环形分段色（语义变量循环；CSS 变量在 conic-gradient 中原生可用） */
const RING_COLORS: string[] = [
  'var(--color-primary)',
  'var(--color-info)',
  'var(--color-warning)',
  'var(--color-success)',
  'var(--color-danger)',
]

/** 组件入参 */
const props = defineProps<{
  /** 营养条目列表（空数组 → 空态） */
  items: NutritionRingItem[]
}>()

/** 是否有可绘制数据（至少一项 value 或 percent > 0） */
const hasData = computed(
  () => props.items.length > 0 && props.items.some((it) => it.value > 0 || (it.percent ?? 0) > 0),
)

/** 环形分段（start/end 百分比 + 颜色），percent 优先，value 归一化兜底 */
const segments = computed(() => {
  if (!hasData.value) return []
  const raw = props.items.map((it) => it.percent ?? 0)
  const hasPercent = raw.some((p) => p > 0)
  let values: number[]
  if (hasPercent) {
    values = raw
  } else {
    const total = props.items.reduce((sum, it) => sum + Math.max(0, it.value), 0)
    values = total > 0 ? props.items.map((it) => (Math.max(0, it.value) / total) * 100) : []
  }
  // 累计占比切弧段（clamp 到 0~100 防浮点越界）
  let acc = 0
  const result: Array<{ start: number; end: number; color: string }> = []
  props.items.forEach((_, idx) => {
    const size = Math.max(0, Math.min(100, values[idx] ?? 0))
    const start = Math.min(100, acc)
    acc += size
    const end = Math.min(100, acc)
    if (end > start) result.push({ start, end, color: RING_COLORS[idx % RING_COLORS.length] ?? '' })
  })
  return result
})

/** conic-gradient 背景串（从 12 点方向顺时针；分段间补 0.5% 缝隙避免色块粘连锯齿） */
const ringBackground = computed(() => {
  const stops = segments.value.map(
    (seg) => `${seg.color} ${seg.start}% ${Math.max(seg.start + 0.1, seg.end - 0.5)}%`,
  )
  // 剩余部分以页面底色补满（视觉留白，不表达数据）
  return `conic-gradient(from 0deg, ${stops.join(', ')}, var(--bg-page) 0)`
})
</script>

<template>
  <view class="nutrition-ring">
    <!-- 无数据空态 -->
    <view v-if="!hasData" class="nutrition-ring__empty">
      <text class="nutrition-ring__empty-text">暂无营养数据</text>
    </view>

    <template v-else>
      <!-- 环形占比图：conic-gradient + 内圆遮罩（兼容性退化说明见文件级注释） -->
      <view class="nutrition-ring__chart">
        <view class="nutrition-ring__ring" :style="{ background: ringBackground }" />
        <view class="nutrition-ring__center">
          <text class="nutrition-ring__center-text">估算占比</text>
        </view>
      </view>

      <!-- 图例列表：色点 + label + value + unit（比例语义的完整承载通道） -->
      <view class="nutrition-ring__legend">
        <view v-for="(it, idx) in items" :key="it.label" class="nutrition-ring__legend-item">
          <view
            class="nutrition-ring__legend-dot"
            :style="{ background: RING_COLORS[idx % RING_COLORS.length] }"
          />
          <text class="nutrition-ring__legend-label">{{ it.label }}</text>
          <text class="nutrition-ring__legend-value">{{ it.value }}{{ it.unit }}</text>
        </view>
      </view>
    </template>
  </view>
</template>

<style scoped lang="scss">
.nutrition-ring {
  box-sizing: border-box;
  display: block;
  width: 100%;
}

.nutrition-ring__empty {
  display: flex;
  justify-content: center;
  padding: var(--space-lg) 0;
}

.nutrition-ring__empty-text {
  font-size: var(--font-size-sm);
  color: var(--text-tertiary);
}

.nutrition-ring__chart {
  position: relative;
  width: 320rpx;
  height: 320rpx;
  margin: 0 auto;
}

/* 环：conic-gradient 比例色 */
.nutrition-ring__ring {
  position: absolute;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  border-radius: var(--radius-pill);
}

/* 内圆遮罩：卡片底色挖空成环（变量色，深色自动适配） */
.nutrition-ring__center {
  position: absolute;
  top: 50%;
  left: 50%;
  width: 200rpx;
  height: 200rpx;
  transform: translate(-50%, -50%);
  border-radius: var(--radius-pill);
  background: var(--bg-card);
  display: flex;
  align-items: center;
  justify-content: center;
}

.nutrition-ring__center-text {
  font-size: var(--font-size-sm);
  color: var(--text-tertiary);
}

.nutrition-ring__legend {
  margin-top: var(--space-md);
  display: flex;
  flex-direction: column;
  gap: var(--space-xs);
}

.nutrition-ring__legend-item {
  display: flex;
  align-items: center;
  min-height: var(--hit-min);
  gap: var(--space-sm);
}

.nutrition-ring__legend-dot {
  flex-shrink: 0;
  width: 20rpx;
  height: 20rpx;
  border-radius: var(--radius-pill);
}

.nutrition-ring__legend-label {
  flex: 1;
  font-size: var(--font-size-sm);
  color: var(--text-primary);
}

.nutrition-ring__legend-value {
  font-size: var(--font-size-sm);
  color: var(--text-secondary);
}
</style>
