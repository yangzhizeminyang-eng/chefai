<!--
  文件级注释：P-39 我的创新菜列表页（独立列表，非多步流程节点）。
  - 数据源：innovation.myRecipes（本会话采纳的创新菜内存列表，对齐源码 InnovateView
    「我的创新菜」Tab；后端无列表端点——/v1/innovation/recipes 仅支持单查，采纳时
    store.adopt 本地去重追加，故本页为同步内存渲染，无加载 / 错误请求分支）；
  - 列表行卡：菜名 + 摘要（N 样食材 · M 步，对齐源码 mine-meta；InnovationRecipe
    无创建时间字段，如实不展示）+ 已采纳徽标 + 行内「复用」；整卡点击 →
    ROUTES.INNOVATION_DETAIL + '?recipe_id='；
  - 行内复用：innovation.reuse(id) → trackEvent('innovation_reuse') → 成功跳
    result 页复用回看（无 job_id 分支直接呈现 store.current）；失败 toast；
  - 空态：「还没有创新菜，去创建第一道」→ ROUTES.INNOVATION_ENTRY；
  - 进入列表 trackEvent('innovation_index')。
-->
<script setup lang="ts">
import { onHide, onLoad } from '@dcloudio/uni-app'
import type { InnovationRecipe } from '@shared/types'
import { useInnovationStore } from '@/stores/innovation'
import { ROUTES, goRoute } from '@/utils/routes'
import { flushOnHide, trackEvent } from '@/utils/track'
import { toastError, toastSuccess } from '@/utils/toast'
import { useAppNetwork } from '@/platform/network'
import { useTheme } from '@/platform/theme'
import { useFontSize } from '@/platform/fontSize'
import OfflineBar from '@/components/OfflineBar.vue'
import EmptyState from '@/components/EmptyState.vue'

/** 深色模式标记（根节点 class） */
const { isDark } = useTheme()
/** 字号档位 class（根节点 class） */
const { fontSizeClass } = useFontSize()

/** 创新 store（myRecipes 内存列表 + reuse 动作） */
const innovation = useInnovationStore()
/** 全局网络态（离线提示条显隐） */
const network = useAppNetwork()

/** 行内复用进行中的菜谱 ID 集合（防重复点击；响应式 needs ref 但复用极快，用 Set 局部即可） */
const reusingIds = new Set<number>()

/**
 * 打开创新菜详情（整卡点击 → P-38，携带 recipe_id）。
 * @param r 创新菜条目
 * @returns 无
 */
function openDetail(r: InnovationRecipe): void {
  goRoute(`${ROUTES.INNOVATION_DETAIL}?recipe_id=${r.id}`)
}

/**
 * 行内复用：reuse 成功 → 埋点 + toast + 跳 result 页复用回看；失败 toast。
 * @param r 创新菜条目
 * @returns 无
 * @throws 不向外抛出（reuse 失败写 store.error，就地提示）
 */
async function onReuse(r: InnovationRecipe): Promise<void> {
  if (reusingIds.has(r.id)) return
  reusingIds.add(r.id)
  const ok = await innovation.reuse(r.id)
  reusingIds.delete(r.id)
  if (ok) {
    trackEvent('innovation_reuse')
    toastSuccess('已载入这道创新菜，可查看或直接采纳')
    goRoute(ROUTES.INNOVATION_RESULT)
  } else {
    toastError(innovation.error?.message || '复用失败，请重试')
  }
}

/**
 * 去创建第一道创新菜（空态行动按钮 → 入口页）。
 * @returns 无
 */
function goCreate(): void {
  goRoute(ROUTES.INNOVATION_ENTRY)
}

// onLoad：进入列表埋点 innovation_index（每次进入一次）
onLoad(() => {
  trackEvent('innovation_index')
})

// onHide：尽力上报缓冲埋点 + 暂停创新轮询（本页未轮询时为无操作，统一约定）
onHide(() => {
  flushOnHide()
  innovation.pausePolling()
})
</script>

<template>
  <view class="page" :class="[isDark ? 'dark' : '', fontSizeClass]">
    <!-- 离线提示条 -->
    <OfflineBar v-if="!network.isConnected" />

    <view class="mine">
      <!-- 空态：引导去创建（列表数据为会话内存态，离线时已采纳条目仍可查看） -->
      <EmptyState
        v-if="innovation.myRecipes.length === 0"
        icon="✨"
        title="还没有创新菜"
        desc="去创建属于你的第一道创新菜吧"
        action-text="去创建"
        @action="goCreate"
      />

      <!-- 列表 -->
      <view v-else class="mine__list">
        <view
          v-for="r in innovation.myRecipes"
          :key="r.id"
          class="mine__item"
          @click="openDetail(r)"
        >
          <view class="mine__main">
            <view class="mine__name-row">
              <text class="mine__name">{{ r.name }}</text>
              <view class="mine__adopted-badge">已采纳</view>
            </view>
            <text class="mine__meta">{{ r.ingredients.length }} 样食材 · {{ r.steps.length }} 步</text>
          </view>
          <view class="mine__reuse" @click.stop="onReuse(r)">复用</view>
        </view>
      </view>
    </view>
  </view>
</template>

<style scoped lang="scss">
.mine {
  box-sizing: border-box;
  min-height: 100%;
  padding: var(--space-md);
  padding-bottom: calc(var(--space-lg) + env(safe-area-inset-bottom));
}

.mine__list {
  display: flex;
  flex-direction: column;
  gap: var(--space-md);
}

/* 行卡：整卡可点 → 详情，热区 ≥88rpx（内容天然超出） */
.mine__item {
  display: flex;
  align-items: center;
  gap: var(--space-sm);
  padding: var(--space-md);
  border-radius: var(--radius-card);
  background: var(--bg-card);
  box-shadow: var(--shadow-card);
}

.mine__main {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: var(--space-xs);
}

.mine__name-row {
  display: flex;
  align-items: center;
  gap: var(--space-xs);
}

.mine__name {
  flex: 1;
  min-width: 0;
  font-size: var(--font-size-base);
  font-weight: 600;
  color: var(--text-primary);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

/* 已采纳徽标：primary 语义 */
.mine__adopted-badge {
  flex-shrink: 0;
  box-sizing: border-box;
  padding: 4rpx var(--space-sm);
  border-radius: var(--radius-ctrl);
  background: var(--color-primary-weak);
  color: var(--color-primary);
  font-size: var(--font-size-sm);
}

.mine__meta {
  font-size: var(--font-size-sm);
  color: var(--text-tertiary);
}

/* 行内复用按钮：primary 描边，热区 ≥88rpx */
.mine__reuse {
  flex-shrink: 0;
  box-sizing: border-box;
  min-height: var(--hit-min);
  display: flex;
  align-items: center;
  padding: 0 var(--space-md);
  border: 1rpx solid var(--color-primary);
  border-radius: var(--radius-ctrl);
  font-size: var(--font-size-sm);
  color: var(--color-primary);
}
</style>
