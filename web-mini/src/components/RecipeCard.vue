<script setup lang="ts">
/**
 * 文件级注释：推荐结果卡片（业务组件）。
 * 自 web-stage1/src/components/RecipeCard.vue 迁移：阶段一卡片为「封面 + 菜名 +
 * 耗时/难度/热量/覆盖率 + 缺料折叠」的宽卡；小程序端按 Task 5 规格收敛为
 * 「左封面（RecipeCover sm）+ 右信息（菜名、时长/难度小徽标、过敏原徽标）+ 底部免责小字」
 * 的列表行卡，整卡可点（emit click，由页面负责跳转详情），整卡热区 ≥88rpx。
 * - item 为本地宽松接口 RecipeCardLike（页面以推荐/收藏/当季等列表条目适配传入）；
 * - 过敏原徽标「含过敏原 N 项」红点样式（danger 语义），无过敏原不渲染；
 * - 底部免责小字固定取 @shared/constants 的 DISCLAIMER_TEXT（不散落硬编码）。
 * 使用约束：由页面根 .page/.dark 提供主题变量上下文。
 */
import { computed } from 'vue'
import { DISCLAIMER_TEXT } from '@shared/constants'
import RecipeCover from './RecipeCover.vue'

/** 卡片条目宽松接口（页面侧列表数据的最小字段集） */
export interface RecipeCardLike {
  /** 菜谱 ID（页面跳转详情用） */
  id: string
  /** 菜名 */
  name: string
  /** 总耗时（分钟，可选；缺省展示「时长未标注」） */
  total_time?: number
  /** 难度编码（可选；easy/medium/hard → 中文标签，未知编码原样展示） */
  difficulty?: string
  /** 过敏原列表（可选；非空渲染「含过敏原 N 项」徽标） */
  allergens?: string[]
  /** 封面图 URL（可选；缺省走 RecipeCover 色板占位回落） */
  cover_url?: string
}

/** 组件入参 */
const props = defineProps<{
  /** 列表条目（契约对齐 RecipeCardLike） */
  item: RecipeCardLike
}>()

/** 卡片点击事件（整卡可点；跳转逻辑由页面处理） */
const emit = defineEmits<{ (e: 'click'): void }>()

/** 难度编码 → 中文标签（对齐阶段一 easy/medium/hard 口径） */
const DIFFICULTY_LABELS: Record<string, string> = {
  easy: '简单',
  medium: '中等',
  hard: '较难',
}

/** 时长展示文案（total_time 缺省如实标注「时长未标注」） */
const timeText = computed(() =>
  typeof props.item.total_time === 'number' ? `${props.item.total_time} 分钟` : '时长未标注',
)

/** 难度展示文案（未知编码原样展示） */
const difficultyText = computed(() => DIFFICULTY_LABELS[props.item.difficulty ?? ''] ?? '')

/** 过敏原徽标文案（空数组/缺省不渲染） */
const allergenText = computed(() =>
  props.item.allergens && props.item.allergens.length > 0
    ? `含过敏原 ${props.item.allergens.length} 项`
    : '',
)

/**
 * 整卡点击：向外 emit click（页面负责跳详情，组件不做路由依赖）。
 * @returns 无
 */
function onClick(): void {
  emit('click')
}
</script>

<template>
  <!-- 整卡可点：min-height ≥88rpx（内容天然超出），点击热区覆盖全卡 -->
  <view class="recipe-card" @click="onClick">
    <!-- 左封面：sm 缩略方图（无图走色板首字占位） -->
    <RecipeCover
      class="recipe-card__cover"
      :name="item.name"
      :cover-url="item.cover_url"
      :palette-seed="item.id"
      size="sm"
    />
    <!-- 右信息列 -->
    <view class="recipe-card__body">
      <text class="recipe-card__name">{{ item.name }}</text>
      <view class="recipe-card__meta">
        <text class="recipe-card__meta-item">⏱ {{ timeText }}</text>
        <text v-if="difficultyText" class="recipe-card__meta-item">🍳 {{ difficultyText }}</text>
        <!-- 过敏原徽标：红点样式（danger 语义），无过敏原不渲染 -->
        <view v-if="allergenText" class="recipe-card__allergen">
          <view class="recipe-card__dot" />
          <text class="recipe-card__allergen-text">{{ allergenText }}</text>
        </view>
      </view>
      <!-- 底部免责小字：G-02 语义， DISCLAIMER_TEXT 常量收口 -->
      <text class="recipe-card__disclaimer">{{ DISCLAIMER_TEXT }}</text>
    </view>
  </view>
</template>

<style scoped lang="scss">
.recipe-card {
  box-sizing: border-box;
  display: flex;
  gap: var(--space-sm);
  min-height: var(--hit-min);
  padding: var(--space-sm);
  border-radius: var(--radius-card);
  background: var(--bg-card);
  box-shadow: var(--shadow-card);
  overflow: hidden;
}

.recipe-card__cover {
  margin: 0;
}

.recipe-card__body {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
}

.recipe-card__name {
  font-size: var(--font-size-base);
  font-weight: 600;
  line-height: 1.4;
  color: var(--text-primary);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.recipe-card__meta {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: var(--space-xs) var(--space-sm);
  margin-top: var(--space-xs);
}

.recipe-card__meta-item {
  font-size: var(--font-size-sm);
  line-height: 1.5;
  color: var(--text-secondary);
}

/* 过敏原徽标：红点 + 文字（danger 语义，图标 + 文字双表达） */
.recipe-card__allergen {
  display: flex;
  align-items: center;
  gap: 6rpx;
}

.recipe-card__dot {
  width: 12rpx;
  height: 12rpx;
  border-radius: var(--radius-pill);
  background: var(--color-danger);
}

.recipe-card__allergen-text {
  font-size: var(--font-size-sm);
  line-height: 1.5;
  color: var(--color-danger);
}

/* 底部免责小字：弱化灰字 */
.recipe-card__disclaimer {
  margin-top: var(--space-xs);
  font-size: var(--font-size-sm);
  line-height: 1.4;
  color: var(--text-tertiary);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
</style>
