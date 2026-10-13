<!--
  文件级注释：P-26/27 收藏·历史页（tabBar，页内双 Tab 自制 segmented，非 tabBar 切换）。
  - 收藏 Tab（P-26）：me.loadFavorites(group?)，分组 chips（favoriteGroups，'' = 全部）；
    列表 RecipeCard（FavoriteItem 适配 RecipeCardLike）；点击 → RECIPE_DETAIL?recipe_id=；
    条目「取消收藏」按钮 → BaseDialog 确认 → me.removeFavorite（本地同步移除）；
  - 历史 Tab（P-27）：me.loadHistory()；列表：菜名 / 完成时间 / 评分·耗时摘要
    （对齐 web-stage1 MeView historyMetaText：DEF-08）；点击 → 详情；
    「再做一次」→ cook 链路起点 RECIPE_DETAIL（菜谱详情页起 Cook 开始链路）；
  - 两 Tab 独立 loading / empty / error 三态；onShow 拉当前 Tab 数据。
-->
<script setup lang="ts">
import { computed, ref } from 'vue'
import { onHide, onShow } from '@dcloudio/uni-app'
import type { ApiError, FavoriteItem, HistoryItem } from '@shared/types'
import { useMeStore } from '@/stores/me'
import { ROUTES } from '@/utils/routes'
import { flushOnHide } from '@/utils/track'
import { toastSuccess, toastError } from '@/utils/toast'
import { useAppNetwork } from '@/platform/network'
import { useTheme } from '@/platform/theme'
import { useFontSize } from '@/platform/fontSize'
import OfflineBar from '@/components/OfflineBar.vue'
import SkeletonPage from '@/components/SkeletonPage.vue'
import EmptyState from '@/components/EmptyState.vue'
import ErrorState from '@/components/ErrorState.vue'
import RecipeCard from '@/components/RecipeCard.vue'
import BaseDialog from '@/components-base/BaseDialog.vue'
import BaseButton from '@/components-base/BaseButton.vue'

/** 页内 Tab 键（favorites 收藏 / history 历史做菜） */
type TabKey = 'favorites' | 'history'

/** 深色模式标记（根节点 class） */
const { isDark } = useTheme()
/** 字号档位 class（根节点 class） */
const { fontSizeClass } = useFontSize()

/** 个人中心 store（favorites / favoriteGroups / history / loadFavorites / loadHistory / removeFavorite） */
const me = useMeStore()
/** 全局网络态（离线提示条显隐） */
const network = useAppNetwork()

/** 当前激活 Tab（缺省收藏） */
const activeTab = ref<TabKey>('favorites')

/** 当前收藏分组（'' = 全部） */
const favoriteGroup = ref('')

/** 待取消收藏条目（确认弹层目标；null = 弹层关闭） */
const pendingRemove = ref<FavoriteItem | null>(null)

/** 取消收藏确认弹层可见性 */
const removeDialogVisible = computed(() => pendingRemove.value !== null)

/** 页内 Tab 定义（segmented 渲染源） */
const TABS: Array<{ key: TabKey; label: string }> = [
  { key: 'favorites', label: '收藏' },
  { key: 'history', label: '历史做菜' },
]

/** 分组 chips：全部 + 后端返回分组列表 */
const groupChips = computed(() => ['', ...me.favoriteGroups])

/** 分组展示名（'' → 全部） */
function groupLabel(group: string): string {
  return group === '' ? '全部' : group
}

/**
 * 切换页内 Tab（数据各自懒拉：目标 Tab 空数据即拉取）。
 * @param key 目标 Tab
 * @returns 无
 */
function switchTab(key: TabKey): void {
  activeTab.value = key
  if (key === 'favorites' && me.favorites.length === 0 && !me.favoritesError) {
    void me.loadFavorites(favoriteGroup.value || undefined)
  }
  if (key === 'history' && me.history.length === 0 && !me.historyError) {
    void me.loadHistory()
  }
}

/**
 * 切换收藏分组（重拉该组，对齐源码 onGroupChange）。
 * @param group 分组名（'' = 全部）
 * @returns 无
 */
function onGroupChange(group: string): void {
  favoriteGroup.value = group
  void me.loadFavorites(group || undefined)
}

/**
 * 收藏条目 → 菜谱详情（携带 recipe_id）。
 * @param item 收藏条目
 * @returns 无
 */
function openFavorite(item: FavoriteItem): void {
  uni.navigateTo({ url: `${ROUTES.RECIPE_DETAIL}?recipe_id=${item.recipe_id}`, fail: () => {} })
}

/**
 * 请求取消收藏：打开确认弹层。
 * @param item 收藏条目
 * @returns 无
 */
function askRemoveFavorite(item: FavoriteItem): void {
  pendingRemove.value = item
}

/**
 * 取消取消收藏：关闭弹层。
 * @returns 无
 */
function cancelRemoveFavorite(): void {
  pendingRemove.value = null
}

/**
 * 确认取消收藏：me.removeFavorite（本地同步移除）；失败 toast。
 * @returns 无
 * @throws 不向外抛出（接口失败就地提示）
 */
async function confirmRemoveFavorite(): Promise<void> {
  const target = pendingRemove.value
  if (!target) return
  try {
    await me.removeFavorite(target.recipe_id)
    toastSuccess('已取消收藏')
  } catch (e) {
    toastError((e as ApiError).message || '取消收藏失败，请重试')
  } finally {
    pendingRemove.value = null
  }
}

/**
 * 历史条目 → 菜谱详情。
 * @param item 历史条目
 * @returns 无
 */
function openHistory(item: HistoryItem): void {
  uni.navigateTo({ url: `${ROUTES.RECIPE_DETAIL}?recipe_id=${item.recipe_id}`, fail: () => {} })
}

/**
 * 「再做一次」：跳菜谱详情（cook 链路起点，从详情页发起 Cook）。
 * @param item 历史条目
 * @returns 无
 */
function cookAgain(item: HistoryItem): void {
  uni.navigateTo({ url: `${ROUTES.RECIPE_DETAIL}?recipe_id=${item.recipe_id}`, fail: () => {} })
}

/**
 * 历史完成时间格式化（YYYY-MM-DD HH:mm，对齐源码 formatTime；非法原样返回）。
 * @param iso ISO 8601 时间
 * @returns 格式化文案
 */
function formatTime(iso: string): string {
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return iso
  const pad = (n: number): string => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}`
}

/**
 * 历史条目「评分 · 耗时」摘要文案（对齐源码 historyMetaText，DEF-08）。
 * @param item 历史条目（rating / duration_minutes 均可缺省）
 * @returns 摘要文案（如「★5 · 用时 25 分钟」「未评分」）
 */
function historyMetaText(item: HistoryItem): string {
  const ratingText = item.rating != null ? `★${item.rating}` : '未评分'
  return item.duration_minutes != null
    ? `${ratingText} · 用时 ${item.duration_minutes} 分钟`
    : ratingText
}

// onShow：拉当前 Tab 数据（从编辑/详情页返回后即时刷新）
onShow(() => {
  if (activeTab.value === 'favorites') {
    void me.loadFavorites(favoriteGroup.value || undefined)
  } else {
    void me.loadHistory()
  }
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

    <view class="fav-hist">
      <!-- 页内双 Tab（自制 segmented，非 tabBar） -->
      <view class="fav-hist__tabs">
        <view
          v-for="tab in TABS"
          :key="tab.key"
          class="fav-hist__tab"
          :class="{ 'is-active': activeTab === tab.key }"
          @click="switchTab(tab.key)"
        >
          {{ tab.label }}
        </view>
      </view>

      <!-- ═══ 收藏 Tab ═══ -->
      <template v-if="activeTab === 'favorites'">
        <!-- 分组 chips（有分组才渲染） -->
        <view v-if="me.favoriteGroups.length > 0" class="fav-hist__groups">
          <view
            v-for="group in groupChips"
            :key="group"
            class="fav-hist__group-chip"
            :class="{ 'is-active': favoriteGroup === group }"
            @click="onGroupChange(group)"
          >
            {{ groupLabel(group) }}
          </view>
        </view>

        <!-- 收藏加载态 -->
        <SkeletonPage v-if="me.favoritesLoading" type="list" :rows="4" />

        <!-- 收藏错误态 -->
        <ErrorState v-else-if="me.favoritesError" kind="server" @retry="me.loadFavorites(favoriteGroup || undefined)" />

        <!-- 收藏空态 -->
        <EmptyState
          v-else-if="me.favorites.length === 0"
          icon="⭐"
          title="还没有收藏的菜谱"
          desc="看到想做的菜，点详情里的收藏按钮即可保存到这里"
        />

        <!-- 收藏列表 -->
        <view v-else class="fav-hist__list">
          <view v-for="item in me.favorites" :key="item.recipe_id" class="fav-row">
            <RecipeCard
              class="fav-row__card"
              :item="{
                id: String(item.recipe_id),
                name: item.recipe_name,
                allergens: item.allergen_codes,
              }"
              @click="openFavorite(item)"
            />
            <view class="fav-row__remove" @click.stop="askRemoveFavorite(item)">取消收藏</view>
          </view>
        </view>
      </template>

      <!-- ═══ 历史 Tab ═══ -->
      <template v-else>
        <!-- 历史加载态 -->
        <SkeletonPage v-if="me.historyLoading" type="list" :rows="4" />

        <!-- 历史错误态 -->
        <ErrorState v-else-if="me.historyError" kind="server" @retry="me.loadHistory()" />

        <!-- 历史空态 -->
        <EmptyState
          v-else-if="me.history.length === 0"
          icon="🕘"
          title="还没有做过的菜"
          desc="跟着步骤做完一道菜，记录会出现在这里"
        />

        <!-- 历史列表 -->
        <view v-else class="fav-hist__list">
          <view
            v-for="item in me.history"
            :key="item.session_id"
            class="hist-card"
            @click="openHistory(item)"
          >
            <view class="hist-card__head">
              <text class="hist-card__name">{{ item.recipe_name }}</text>
              <view class="hist-card__again" @click.stop="cookAgain(item)">再做一次</view>
            </view>
            <text class="hist-card__meta">
              {{ formatTime(item.finished_at) }} · {{ historyMetaText(item) }}
            </text>
          </view>
        </view>
      </template>

      <!-- 取消收藏确认弹层 -->
      <BaseDialog
        :visible="removeDialogVisible"
        title="取消收藏"
        position="center"
        @close="cancelRemoveFavorite"
      >
        <view class="remove-dialog">
          <text class="remove-dialog__text">
            确定取消收藏「{{ pendingRemove?.recipe_name }}」吗？
          </text>
          <view class="remove-dialog__actions">
            <BaseButton type="default" block @click="cancelRemoveFavorite">取消</BaseButton>
            <BaseButton type="danger" block @click="confirmRemoveFavorite">确定</BaseButton>
          </view>
        </view>
      </BaseDialog>
    </view>
  </view>
</template>

<style scoped lang="scss">
.fav-hist {
  box-sizing: border-box;
  min-height: 100%;
  padding: var(--space-md);
}

/* ── 页内 segmented ── */
.fav-hist__tabs {
  display: flex;
  padding: 6rpx;
  margin-bottom: var(--space-md);
  border-radius: var(--radius-ctrl);
  background: var(--bg-card);
}

.fav-hist__tab {
  flex: 1;
  min-height: var(--hit-min);
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: var(--radius-ctrl);
  font-size: var(--font-size-base);
  color: var(--text-secondary);

  &.is-active {
    background: var(--color-primary);
    color: var(--text-inverse);
  }
}

/* ── 分组 chips ── */
.fav-hist__groups {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-sm);
  margin-bottom: var(--space-md);
}

.fav-hist__group-chip {
  box-sizing: border-box;
  padding: var(--space-xs) var(--space-md);
  min-height: 72rpx;
  display: flex;
  align-items: center;
  border: 1rpx solid var(--border-color);
  border-radius: var(--radius-pill);
  font-size: var(--font-size-sm);
  color: var(--text-secondary);
  background: var(--bg-card);

  &.is-active {
    border-color: var(--color-primary);
    color: var(--color-primary);
    background: var(--color-primary-weak);
  }
}

.fav-hist__list {
  display: flex;
  flex-direction: column;
  gap: var(--space-md);
}

/* ── 收藏行：卡片 + 取消收藏按钮 ── */
.fav-row {
  display: flex;
  flex-direction: column;
  gap: var(--space-xs);
}

.fav-row__remove {
  align-self: flex-end;
  min-height: 72rpx;
  display: flex;
  align-items: center;
  padding: 0 var(--space-md);
  font-size: var(--font-size-sm);
  color: var(--color-danger);
}

/* ── 历史卡 ── */
.hist-card {
  display: flex;
  flex-direction: column;
  gap: var(--space-xs);
  padding: var(--space-md);
  border-radius: var(--radius-card);
  background: var(--bg-card);
}

.hist-card__head {
  display: flex;
  align-items: center;
  gap: var(--space-sm);
}

.hist-card__name {
  flex: 1;
  min-width: 0;
  font-size: var(--font-size-base);
  font-weight: 600;
  color: var(--text-primary);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.hist-card__again {
  flex-shrink: 0;
  min-height: 72rpx;
  display: flex;
  align-items: center;
  padding: 0 var(--space-md);
  border: 1rpx solid var(--color-primary);
  border-radius: var(--radius-ctrl);
  font-size: var(--font-size-sm);
  color: var(--color-primary);
}

.hist-card__meta {
  font-size: var(--font-size-sm);
  color: var(--text-tertiary);
}

/* ── 取消收藏确认弹层 ── */
.remove-dialog {
  display: flex;
  flex-direction: column;
  gap: var(--space-lg);
  padding: var(--space-sm) 0 var(--space-md);
}

.remove-dialog__text {
  font-size: var(--font-size-base);
  line-height: 1.6;
  color: var(--text-primary);
}

.remove-dialog__actions {
  display: flex;
  gap: var(--space-sm);
}
</style>
