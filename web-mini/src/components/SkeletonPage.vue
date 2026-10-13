<script setup lang="ts">
/**
 * 文件级注释：页面加载骨架（五态-加载态，安全组件，主包内置）。
 * 阶段一「加载中」语义迁移为小程序骨架屏：骨架灰块 + 微光扫动动画（CSS animation），
 * 明确禁止全屏白屏转圈（不渲染任何 spinner，只渲染骨架占位）：
 * - type = 'list'：rows 条「圆头像块 + 两行文本线」；
 * - type = 'detail'：大图块 + 标题行 + rows 段落行；
 * - type = 'grid'：两列卡片块（rows 控制行数，每行 2 块）；
 * - 灰块全部用变量色渐变（--bg-page/--divider），深色模式自动适配。
 * 使用约束：由页面根 .page/.dark 提供主题变量上下文。
 */
import { computed } from 'vue'

/** 骨架形态（决定条目内部结构） */
export type SkeletonType = 'list' | 'detail' | 'grid'

/** 组件入参 */
const props = withDefaults(
  defineProps<{
    /** 骨架条目数（list 为条数；grid 为行数，每行 2 块；detail 为段落行数） */
    rows?: number
    /** 骨架形态：list 列表 / detail 详情 / grid 网格 */
    type?: SkeletonType
  }>(),
  { rows: 3, type: 'list' },
)

/** 形态修饰类 */
const typeClass = computed(() => `is-${props.type}`)

/** 重复条目索引（模板 v-for 用；rows 上限 12 防异常大值） */
const rowList = computed(() =>
  Array.from({ length: Math.max(1, Math.min(12, props.rows)) }, (_, i) => i),
)
</script>

<template>
  <view class="skeleton-page" :class="typeClass">
    <!-- list：圆头像块 + 两行文本线 -->
    <template v-if="type === 'list'">
      <view v-for="i in rowList" :key="i" class="skeleton-page__row">
        <view class="skeleton-page__avatar shimmer" />
        <view class="skeleton-page__lines">
          <view class="skeleton-page__line shimmer" />
          <view class="skeleton-page__line skeleton-page__line--short shimmer" />
        </view>
      </view>
    </template>

    <!-- detail：大图块 + 标题行 + 段落行 -->
    <template v-else-if="type === 'detail'">
      <view class="skeleton-page__hero shimmer" />
      <view class="skeleton-page__title shimmer" />
      <view v-for="i in rowList" :key="i" class="skeleton-page__line shimmer" />
    </template>

    <!-- grid：两列卡片块 -->
    <template v-else>
      <view class="skeleton-page__grid">
        <template v-for="i in rowList" :key="i">
          <view class="skeleton-page__cell shimmer" />
          <view class="skeleton-page__cell shimmer" />
        </template>
      </view>
    </template>
  </view>
</template>

<style scoped lang="scss">
.skeleton-page {
  box-sizing: border-box;
  display: block;
  width: 100%;
}

/* 微光扫动动画（变量色渐变，深色自动适配） */
.shimmer {
  background: linear-gradient(90deg, var(--bg-page) 25%, var(--divider) 37%, var(--bg-page) 63%);
  background-size: 400% 100%;
  animation: skeleton-shimmer 1.4s ease infinite;
}

@keyframes skeleton-shimmer {
  0% {
    background-position: 100% 50%;
  }

  100% {
    background-position: 0 50%;
  }
}

/* list 行：头像块 + 文本线 */
.skeleton-page__row {
  display: flex;
  align-items: center;
  gap: var(--space-sm);
  min-height: var(--hit-min);
  padding: var(--space-sm) 0;
}

.skeleton-page__avatar {
  flex-shrink: 0;
  width: 96rpx;
  height: 96rpx;
  border-radius: var(--radius-ctrl);
}

.skeleton-page__lines {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: var(--space-xs);
}

.skeleton-page__line {
  height: 28rpx;
  border-radius: var(--radius-ctrl);

  &--short {
    width: 60%;
  }
}

/* detail：大图 + 标题 + 段落 */
.skeleton-page__hero {
  width: 100%;
  height: 320rpx;
  border-radius: var(--radius-card);
}

.skeleton-page__title {
  height: 40rpx;
  width: 50%;
  margin: var(--space-md) 0;
  border-radius: var(--radius-ctrl);
}

/* grid：两列卡片 */
.skeleton-page__grid {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-sm);
}

.skeleton-page__cell {
  box-sizing: border-box;
  width: calc((100% - var(--space-sm)) / 2);
  height: 220rpx;
  border-radius: var(--radius-card);
}
</style>
