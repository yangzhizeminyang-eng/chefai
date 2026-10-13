<script setup lang="ts">
/**
 * 文件级注释：食材选择网格（业务组件）。
 * 自 web-stage1/src/views/SelectIngredientView.vue 的分类宫格语义迁移（W-02 前置食材选择）：
 * - 分类标题 + 分类内食材网格（flex wrap，item 热区 ≥88rpx，选中态主色描边）；
 * - 顶部搜索框：本地关键字过滤展示列表——仅 UI 层派生（过滤只影响可见项，
 *   不参与「已选/未选」业务规则判定，业务规则由页面持有 selected 状态）；
 * - 分页：初始每分类渲染前 30 条，底部「加载更多」按钮扩展条数；
 *   页面 onReachBottom 时调用本组件 expose 的 loadMore() 触发增量渲染
 *   （261+ 条目一次性渲染有卡顿风险，切片渲染保证性能安全）；
 * - loading = true 时渲染骨架行（配合页面请求态）。
 * 使用约束：由页面根 .page/.dark 提供主题变量上下文。
 */
import { computed, ref } from 'vue'

/** 食材条目（id 供业务规则引用，name 供展示与搜索） */
export interface IngredientGridItem {
  /** 食材唯一标识（业务规则键，如 'tomato'） */
  id: string
  /** 食材展示名（如「番茄」） */
  name: string
}

/** 食材分类（分类名 + 该分类下食材列表） */
export interface IngredientGridCategory {
  /** 分类名（如「蔬菜」「肉禽」） */
  category: string
  /** 该分类下食材列表 */
  items: IngredientGridItem[]
}

/** 每分类初始渲染条数（超出走「加载更多」/loadMore 增量渲染） */
const PAGE_SIZE = 30

/** 组件入参 */
const props = withDefaults(
  defineProps<{
    /** 食材分类列表（页面从接口/本地词表组装） */
    categories: IngredientGridCategory[]
    /** 选中状态映射（id → 是否选中；业务规则由页面持有，组件只回传 toggle） */
    selected: Record<string, boolean>
    /** 加载态（true 渲染骨架行） */
    loading?: boolean
  }>(),
  { loading: false },
)

/** 切换选中事件（页面据 id 更新 selected 业务状态） */
const emit = defineEmits<{
  (e: 'toggle', id: string, name: string): void
}>()

/** 搜索关键字（本地过滤展示列表，仅 UI 层派生） */
const keyword = ref('')

/** 当前每分类渲染条数上限（loadMore 按页扩大） */
const renderLimit = ref(PAGE_SIZE)

/** 关键字过滤后的分类列表（仅 UI 层派生：过滤只影响可见项，不属业务规则） */
const filteredCategories = computed(() => {
  const kw = keyword.value.trim()
  if (!kw) return props.categories
  return props.categories
    .map((cat) => ({ ...cat, items: cat.items.filter((item) => item.name.includes(kw)) }))
    .filter((cat) => cat.items.length > 0)
})

/** 分页渲染后的分类列表（每分类前 renderLimit 条） */
const pagedCategories = computed(() =>
  filteredCategories.value.map((cat) => ({ ...cat, items: cat.items.slice(0, renderLimit.value) })),
)

/** 是否还有未渲染条目（控制「加载更多」按钮显隐） */
const hasMore = computed(() =>
  filteredCategories.value.some((cat) => cat.items.length > renderLimit.value),
)

/**
 * 增量渲染一页（供底部按钮与页面 onReachBottom 调用，已 expose）。
 * @returns 无
 */
function loadMore(): void {
  renderLimit.value += PAGE_SIZE
}

/** 暴露 loadMore 供页面 onReachBottom 调用 */
defineExpose({ loadMore })

/**
 * 搜索框输入事件：更新关键字（本地过滤展示列表，仅 UI 层派生）。
 * 参数用 Event 宽类型 + 内部收窄（detail.value），兼容小程序事件结构与模板类型检查。
 * @param e input 事件（detail.value 为输入内容）
 * @returns 无
 */
function onSearchInput(e: Event): void {
  const detail = (e as { detail?: { value?: string } }).detail
  keyword.value = detail?.value ?? ''
}

/**
 * 点击食材项：回传 toggle（id + name；选中判定由页面业务规则处理）。
 * @param item 被点击的食材条目
 * @returns 无
 */
function onToggle(item: IngredientGridItem): void {
  emit('toggle', item.id, item.name)
}
</script>

<template>
  <view class="ingredient-grid">
    <!-- 顶部搜索框：本地过滤展示列表（仅 UI 层派生，不属业务规则） -->
    <view class="ingredient-grid__search">
      <text class="ingredient-grid__search-icon">🔍</text>
      <input
        class="ingredient-grid__search-input"
        :value="keyword"
        placeholder="搜索食材"
        confirm-type="search"
        @input="onSearchInput"
      />
    </view>

    <!-- 加载骨架行 -->
    <view v-if="loading" class="ingredient-grid__skeleton">
      <view v-for="i in 8" :key="i" class="ingredient-grid__skeleton-chip" />
    </view>

    <!-- 分类网格 -->
    <template v-else>
      <view v-for="cat in pagedCategories" :key="cat.category" class="ingredient-grid__group">
        <text class="ingredient-grid__title">{{ cat.category }}</text>
        <view class="ingredient-grid__items">
          <view
            v-for="item in cat.items"
            :key="item.id"
            class="ingredient-grid__item"
            :class="{ 'is-active': selected[item.id] }"
            @click="onToggle(item)"
          >
            <text class="ingredient-grid__item-name">{{ item.name }}</text>
            <text v-if="selected[item.id]" class="ingredient-grid__item-check">✓</text>
          </view>
        </view>
      </view>

      <!-- 空结果态 -->
      <view v-if="pagedCategories.length === 0" class="ingredient-grid__empty">
        <text class="ingredient-grid__empty-text">没有找到匹配的食材</text>
      </view>

      <!-- 加载更多：点击或页面 onReachBottom（loadMore 已 expose）增量渲染 -->
      <view v-if="hasMore" class="ingredient-grid__more" @click="loadMore">加载更多</view>
    </template>
  </view>
</template>

<style scoped lang="scss">
.ingredient-grid {
  box-sizing: border-box;
  display: block;
  width: 100%;
}

/* 搜索框：热区 ≥88rpx，统一边框 */
.ingredient-grid__search {
  box-sizing: border-box;
  display: flex;
  align-items: center;
  gap: var(--space-xs);
  min-height: var(--hit-min);
  padding: 0 var(--space-sm);
  border: 1rpx solid var(--border-color);
  border-radius: var(--radius-ctrl);
  background: var(--bg-card);
}

.ingredient-grid__search-icon {
  font-size: var(--font-size-base);
}

.ingredient-grid__search-input {
  flex: 1;
  min-height: var(--hit-min);
  font-size: var(--font-size-sm);
  color: var(--text-primary);
}

/* 骨架行：灰块网格（变量色渐变，深色自动适配） */
.ingredient-grid__skeleton {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-sm);
  padding: var(--space-sm) 0;
}

.ingredient-grid__skeleton-chip {
  width: 140rpx;
  height: 72rpx;
  border-radius: var(--radius-ctrl);
  background: linear-gradient(90deg, var(--bg-page) 25%, var(--divider) 37%, var(--bg-page) 63%);
  background-size: 400% 100%;
  animation: grid-skeleton-loading 1.4s ease infinite;
}

@keyframes grid-skeleton-loading {
  0% {
    background-position: 100% 50%;
  }

  100% {
    background-position: 0 50%;
  }
}

.ingredient-grid__group {
  margin-top: var(--space-md);
}

.ingredient-grid__title {
  display: block;
  font-size: var(--font-size-base);
  font-weight: 600;
  line-height: 1.5;
  color: var(--text-primary);
}

.ingredient-grid__items {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-sm);
  margin-top: var(--space-sm);
}

/* 食材项：热区 ≥88rpx，选中态主色描边（✓ 图标 + 描边双表达，不依赖颜色单独传达） */
.ingredient-grid__item {
  box-sizing: border-box;
  display: flex;
  align-items: center;
  gap: 6rpx;
  min-height: var(--hit-min);
  padding: 0 var(--space-md);
  border: 2rpx solid var(--border-color);
  border-radius: var(--radius-pill);
  background: var(--bg-card);

  &.is-active {
    border-color: var(--color-primary);
    background: var(--color-primary-weak);
  }
}

.ingredient-grid__item-name {
  font-size: var(--font-size-sm);
  line-height: 1.4;
  color: var(--text-primary);
}

.ingredient-grid__item-check {
  font-size: var(--font-size-sm);
  font-weight: 700;
  color: var(--color-primary);
}

.ingredient-grid__empty {
  display: flex;
  justify-content: center;
  padding: var(--space-lg) 0;
}

.ingredient-grid__empty-text {
  font-size: var(--font-size-sm);
  color: var(--text-tertiary);
}

/* 加载更多按钮：热区 ≥88rpx，整行可点 */
.ingredient-grid__more {
  display: flex;
  align-items: center;
  justify-content: center;
  min-height: var(--hit-min);
  margin-top: var(--space-md);
  border-radius: var(--radius-ctrl);
  background: var(--bg-card);
  border: 1rpx solid var(--border-color);
  font-size: var(--font-size-sm);
  color: var(--color-info);
}
</style>
