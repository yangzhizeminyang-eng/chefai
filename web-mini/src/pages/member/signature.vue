<!--
  文件级注释：P-28 拿手菜页（pages/member 分包）。
  - 数据源：me.loadSignature()（GET /v1/signature-dishes，后端按 cook_count 倒序）；
  - 条目渲染按 SignatureDish 契约字段：菜名 / 累计烹饪次数 / 平均评分
    （契约无「最近做过的时间」字段，故不渲染该列，见 shared/types SignatureDish）；
  - 空态：「做完的菜会出现在这里」（引导去首页挑菜 / 推荐开做）；
  - 条目点击 → 菜谱详情（ROUTES.RECIPE_DETAIL + '?recipe_id='）；
  - 三态：SkeletonPage / ErrorState（重试）/ EmptyState；onShow 拉取，onHide flush 埋点。
-->
<script setup lang="ts">
import { onHide, onShow } from '@dcloudio/uni-app'
import type { SignatureDish } from '@shared/types'
import { useMeStore } from '@/stores/me'
import { ROUTES } from '@/utils/routes'
import { flushOnHide } from '@/utils/track'
import { useAppNetwork } from '@/platform/network'
import { useTheme } from '@/platform/theme'
import { useFontSize } from '@/platform/fontSize'
import OfflineBar from '@/components/OfflineBar.vue'
import SkeletonPage from '@/components/SkeletonPage.vue'
import EmptyState from '@/components/EmptyState.vue'
import ErrorState from '@/components/ErrorState.vue'

/** 深色模式标记（根节点 class） */
const { isDark } = useTheme()
/** 字号档位 class（根节点 class） */
const { fontSizeClass } = useFontSize()

/** 个人中心 store（signature / signatureLoading / signatureError / loadSignature） */
const me = useMeStore()
/** 全局网络态（离线提示条显隐） */
const network = useAppNetwork()

/**
 * 评分列文案（avg_rating 可能为 null = 无评分记录）。
 * @param rating 平均评分（1~5 或 null）
 * @returns 形如「★4.5」的文案；无评分返回「未评分」
 */
function ratingText(rating: SignatureDish['avg_rating']): string {
  return rating == null ? '未评分' : `★${rating}`
}

/**
 * 点击拿手菜条目 → 菜谱详情页（携带 recipe_id）。
 * @param item 拿手菜条目
 * @returns 无
 * @throws 不抛出（navigateTo fail 静默）
 */
function openRecipe(item: SignatureDish): void {
  uni.navigateTo({ url: `${ROUTES.RECIPE_DETAIL}?recipe_id=${item.recipe_id}`, fail: () => {} })
}

// onShow：拉取拿手菜（从详情页返回后即时刷新次数/评分）
onShow(() => {
  void me.loadSignature()
})

// onHide：尽力上报缓冲埋点
onHide(() => {
  flushOnHide()
})
</script>

<template>
  <view class="page" :class="[isDark ? 'dark' : '', fontSizeClass]">
    <!-- 离线提示条 -->
    <OfflineBar v-if="!network.isConnected" />

    <view class="signature">
      <!-- 加载态 -->
      <SkeletonPage v-if="me.signatureLoading" type="list" :rows="4" />

      <!-- 错误态（重试） -->
      <ErrorState v-else-if="me.signatureError" kind="server" @retry="me.loadSignature()" />

      <!-- 空态：还没做过的菜 -->
      <EmptyState
        v-else-if="me.signature.length === 0"
        icon="🏆"
        title="做完的菜会出现在这里"
        desc="多做饭，常做的菜会成为你的拿手菜"
      />

      <!-- 拿手菜列表（按烹饪次数倒序，后端排序） -->
      <view v-else class="signature__list">
        <view
          v-for="item in me.signature"
          :key="item.recipe_id"
          class="sig-card"
          @click="openRecipe(item)"
        >
          <view class="sig-card__head">
            <text class="sig-card__name">{{ item.recipe_name }}</text>
            <view class="sig-card__arrow" />
          </view>
          <text class="sig-card__meta">做过 {{ item.cook_count }} 次 · {{ ratingText(item.avg_rating) }}</text>
        </view>
      </view>
    </view>
  </view>
</template>

<style scoped lang="scss">
.signature {
  box-sizing: border-box;
  min-height: 100%;
  padding: var(--space-md) var(--space-md) var(--space-xl);
}

.signature__list {
  display: flex;
  flex-direction: column;
  gap: var(--space-md);
}

.sig-card {
  display: flex;
  flex-direction: column;
  gap: var(--space-xs);
  padding: var(--space-md) var(--space-lg);
  border-radius: var(--radius-card);
  background: var(--bg-card);
}

.sig-card__head {
  display: flex;
  align-items: center;
  gap: var(--space-sm);
}

.sig-card__name {
  flex: 1;
  min-width: 0;
  font-size: var(--font-size-base);
  font-weight: 600;
  color: var(--text-primary);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.sig-card__arrow {
  flex-shrink: 0;
  width: 16rpx;
  height: 16rpx;
  border-right: 3rpx solid var(--text-tertiary);
  border-bottom: 3rpx solid var(--text-tertiary);
  transform: rotate(45deg);
}

.sig-card__meta {
  font-size: var(--font-size-sm);
  color: var(--text-tertiary);
}
</style>
