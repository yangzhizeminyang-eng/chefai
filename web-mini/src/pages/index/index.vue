<!--
  文件级注释：P-01 首页（tabBar）。
  - 问候区 + 五入口宫格（对齐 web-stage1 HomeView 六入口语义：
    cooking→手选食材 / vision→拍照识别 / 搜索框入口化→搜索页 / goal→档案页 /
    innovation→AI 创新；fridge 已上 tabBar 不重复；seasonal 分包暂无落地页不设入口）；
  - 临期提醒条（home.data.expiring）：点击 trackEvent('inventory_expiring_click') 并
    switchTab 冰箱页；条内固定 INEDIBLE_JUDGE_NOTE 小字（RL-3 第一处，不作可食性判定）；
    支持当日关闭记忆（storage aicook_expiry_dismissed_{date}）；
  - 继续上次的菜卡（unfinished_session → COOK_GUIDE?session_id=）；
  - 无档案引导建档卡（hasProfile=false → PROFILE_LIST）；DisclaimerBar scene="home"；
  - onShow：home.load() + config.refreshOnShow()；onHide：flushOnHide()。
-->
<script setup lang="ts">
import { computed, ref } from 'vue'
import { onHide, onShow } from '@dcloudio/uni-app'
import { useHomeStore } from '@/stores/home'
import { useConfigStore } from '@/stores/config'
import { flushOnHide, trackEvent } from '@/utils/track'
import { get as storageGet, set as storageSet } from '@/utils/storage'
import { ROUTES } from '@/utils/routes'
import { INEDIBLE_JUDGE_NOTE } from '@shared/constants'
import { useAppNetwork } from '@/platform/network'
import { useTheme } from '@/platform/theme'
import { useFontSize } from '@/platform/fontSize'
import { toastInfo } from '@/utils/toast'
import OfflineBar from '@/components/OfflineBar.vue'
import SkeletonPage from '@/components/SkeletonPage.vue'
import ErrorState from '@/components/ErrorState.vue'
import DisclaimerBar from '@/components/DisclaimerBar.vue'

/** 深色模式标记（根节点 class） */
const { isDark } = useTheme()
/** 字号档位 class（根节点 class） */
const { fontSizeClass } = useFontSize()

/** 首页聚合 store（entries / expiring / unfinished_session / profile_hint） */
const home = useHomeStore()
/** 远程开关 store（AI 创新入口置灰） */
const config = useConfigStore()
/** 全局网络态（离线提示条显隐） */
const network = useAppNetwork()

/** 当日日期键（YYYY-MM-DD，本地时区；临期关闭记忆键组成部分） */
function todayKey(): string {
  const d = new Date()
  const m = String(d.getMonth() + 1).padStart(2, '0')
  const day = String(d.getDate()).padStart(2, '0')
  return `${d.getFullYear()}-${m}-${day}`
}

/** 临期提醒是否已被今日关闭（storage 当日记忆，读取失败按未关闭处理） */
const expiryDismissed = ref(
  storageGet<string>(`aicook_expiry_dismissed_${todayKey()}`, '') === '1',
)

/** 问候语（按时段切换，纯展示） */
const greeting = computed(() => {
  const h = new Date().getHours()
  if (h < 6) return '夜深了，想吃点清淡的？'
  if (h < 11) return '早上好，今天吃什么？'
  if (h < 14) return '中午好，今天吃什么？'
  if (h < 18) return '下午好，想吃点什么？'
  return '晚上好，今天吃什么？'
})

/** 临期提醒展示条件：有临期数据且今日未被关闭 */
const showExpiryAlert = computed(
  () => (home.data?.expiring?.length ?? 0) > 0 && !expiryDismissed.value,
)

/** 临期提醒文案（首条 + 其余计数，对齐阶段一口径） */
const expiryText = computed(() => {
  const list = home.data?.expiring ?? []
  const first = list[0]
  if (!first) return ''
  const head = `${first.ingredient_name} ${first.days_left < 0 ? '已过期' : `还剩 ${first.days_left} 天`}`
  return list.length > 1 ? `${head} 等 ${list.length} 样食材临近到期` : `${head}，注意及时食用`
})

/** 五入口宫格配置（enabled 动态判定；disabledTip 点击时提示） */
const entries = computed(() => [
  {
    key: 'cooking',
    icon: '🍚',
    title: '今天吃什么',
    desc: '随机推选 + 时令食材',
    to: ROUTES.RECOMMEND_TODAY,
    tab: false,
    enabled: home.data?.entries.cooking ?? true,
    disabledTip: '推荐功能维护中',
  },
  {
    key: 'vision',
    icon: '📸',
    title: '拍一下冰箱',
    desc: '拍照识别食材',
    to: ROUTES.RECOMMEND_PHOTO,
    tab: false,
    enabled: home.data?.entries.vision ?? true,
    disabledTip: '识别功能维护中',
  },
  {
    key: 'search',
    icon: '🔍',
    title: '搜索/提问',
    desc: '问厨娘或搜菜谱',
    to: ROUTES.RECOMMEND_SEARCH,
    tab: false,
    enabled: true,
    disabledTip: '',
  },
  {
    key: 'goal',
    icon: '🎯',
    title: '饮食目标',
    desc: '建档定制推荐',
    to: ROUTES.PROFILE_LIST,
    tab: false,
    enabled: home.data?.entries.goal ?? true,
    disabledTip: '档案功能维护中',
  },
  {
    key: 'innovation',
    icon: '✨',
    title: 'AI 创新一下',
    desc: '按手边食材出新菜',
    to: ROUTES.INNOVATION_ENTRY,
    tab: false,
    enabled:
      config.switches.innovation !== false && (home.data?.entries.innovation ?? true),
    disabledTip: 'AI 创新功能暂未开放',
  },
])

/**
 * 点击入口卡：禁用态 toast 提示；可用态按 tab 标记选择 switchTab / navigateTo。
 * @param entry 入口卡对象
 * @returns 无
 */
function goEntry(entry: { to: string; tab: boolean; enabled: boolean; disabledTip: string }): void {
  if (!entry.enabled) {
    toastInfo(entry.disabledTip)
    return
  }
  if (entry.tab) {
    uni.switchTab({ url: entry.to, fail: () => {} })
  } else {
    uni.navigateTo({ url: entry.to, fail: () => {} })
  }
}

/**
 * 关闭临期提醒：写当日记忆键，当日不再显示（持久化失败仅影响当日记忆）。
 * @returns 无
 */
function dismissExpiry(): void {
  expiryDismissed.value = true
  storageSet(`aicook_expiry_dismissed_${todayKey()}`, '1')
}

/**
 * 点击临期提醒条：埋点 inventory_expiring_click + switchTab 到冰箱页。
 * @returns 无
 */
function onExpiryClick(): void {
  trackEvent('inventory_expiring_click')
  uni.switchTab({ url: ROUTES.FRIDGE, fail: () => {} })
}

/**
 * 继续上次的菜：跳烹饪指导页携带未完成会话 ID（断点续做）。
 * @returns 无
 */
function onResumeCook(): void {
  const sid = home.data?.unfinished_session?.session_id
  if (!sid) return
  uni.navigateTo({ url: `${ROUTES.COOK_GUIDE}?session_id=${sid}`, fail: () => {} })
}

/**
 * 去建档：跳家庭档案列表页。
 * @returns 无
 */
function goProfile(): void {
  uni.navigateTo({ url: ROUTES.PROFILE_LIST, fail: () => {} })
}

/**
 * 重试首页聚合数据（ErrorState retry）。
 * @returns 无
 */
function retry(): void {
  void home.load()
}

// onShow：每次进入重拉聚合数据（保证临期/未完成会话新鲜）+ 开关 TTL 刷新
onShow(() => {
  void home.load()
  void config.refreshOnShow()
})

// onHide：尽力上报缓冲埋点
onHide(() => {
  flushOnHide()
})
</script>

<template>
  <view class="page" :class="[isDark ? 'dark' : '', fontSizeClass]">
    <!-- 离线提示条（App 全局网络态驱动） -->
    <OfflineBar v-if="!network.isConnected" />

    <view class="home">
      <!-- 问候区 -->
      <view class="home__head">
        <text class="home__title">{{ greeting }}</text>
        <text class="home__sub">食材在库、档案就绪，推荐更懂你</text>
      </view>

      <!-- 加载态：宫格骨架 -->
      <SkeletonPage v-if="home.loading" type="grid" :rows="3" />

      <template v-else>
        <!-- 异常态：聚合数据加载失败（入口卡不依赖聚合数据，仍可用） -->
        <ErrorState v-if="home.error" kind="server" @retry="retry" />

        <!-- 临期提醒条（可关闭 + 当日记忆；条内固定可食性边界说明，RL-3） -->
        <view v-if="showExpiryAlert" class="home__expiry" @click="onExpiryClick">
          <view class="home__expiry-main">
            <text class="home__expiry-text">{{ expiryText }}</text>
            <text class="home__expiry-note">{{ INEDIBLE_JUDGE_NOTE }}</text>
          </view>
          <view class="home__expiry-close" @click.stop="dismissExpiry">×</view>
        </view>

        <!-- 继续上次的菜卡（断点续做） -->
        <view
          v-if="home.hasUnfinished && home.data?.unfinished_session"
          class="home__resume"
          @click="onResumeCook"
        >
          <text class="home__resume-icon">🍳</text>
          <view class="home__resume-info">
            <text class="home__resume-title">继续上次的菜：{{ home.data.unfinished_session.recipe_name }}</text>
            <text class="home__resume-sub">
              进度：第 {{ home.data.unfinished_session.current_step }} 步 / 共 {{ home.data.unfinished_session.total_steps }} 步
            </text>
          </view>
          <view class="home__resume-btn">继续做</view>
        </view>

        <!-- 无档案引导建档卡（数据未返回时不误报） -->
        <view v-if="home.data && !home.hasProfile" class="home__profile-hint" @click="goProfile">
          <text class="home__profile-hint-text">
            还没有建立家庭档案，建好后推荐会更懂你（过敏原 / 口味 / 厨艺）
          </text>
          <view class="home__profile-hint-btn">去建档</view>
        </view>

        <!-- 五入口宫格 -->
        <view class="home__grid">
          <view
            v-for="entry in entries"
            :key="entry.key"
            class="home__entry"
            :class="{ 'is-disabled': !entry.enabled }"
            @click="goEntry(entry)"
          >
            <text class="home__entry-icon">{{ entry.icon }}</text>
            <text class="home__entry-title">{{ entry.title }}</text>
            <text class="home__entry-desc">{{ entry.enabled ? entry.desc : '暂不可用' }}</text>
          </view>
        </view>
      </template>

      <!-- 底部常驻免责小字 -->
      <DisclaimerBar scene="home" />
    </view>
  </view>
</template>

<style scoped lang="scss">
.home {
  box-sizing: border-box;
  padding: var(--space-md);
}

.home__head {
  display: flex;
  flex-direction: column;
  gap: 6rpx;
  margin-bottom: var(--space-lg);
}

.home__title {
  font-size: var(--font-size-lg);
  font-weight: 600;
  color: var(--text-primary);
}

.home__sub {
  font-size: var(--font-size-sm);
  color: var(--text-tertiary);
}

/* ── 临期提醒条（warning 语义 + 可食性边界小字，RL-3） ── */
.home__expiry {
  display: flex;
  align-items: flex-start;
  gap: var(--space-sm);
  padding: var(--space-sm) var(--space-md);
  margin-bottom: var(--space-md);
  border-radius: var(--radius-card);
  background: var(--color-warning-bg);
}

.home__expiry-main {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 6rpx;
}

.home__expiry-text {
  font-size: var(--font-size-base);
  color: var(--color-warning);
}

.home__expiry-note {
  font-size: var(--font-size-sm);
  line-height: 1.5;
  color: var(--text-tertiary);
}

.home__expiry-close {
  min-width: var(--hit-min);
  min-height: var(--hit-min);
  display: flex;
  align-items: center;
  justify-content: center;
  margin: calc(-1 * var(--space-xs));
  font-size: var(--font-size-lg);
  color: var(--text-tertiary);
}

/* ── 继续上次的菜卡 ── */
.home__resume {
  display: flex;
  align-items: center;
  gap: var(--space-md);
  padding: var(--space-md);
  margin-bottom: var(--space-md);
  border-radius: var(--radius-card);
  background: var(--color-primary-weak);
}

.home__resume-icon {
  font-size: 48rpx;
}

.home__resume-info {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 6rpx;
}

.home__resume-title {
  font-size: var(--font-size-base);
  font-weight: 600;
  color: var(--text-primary);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.home__resume-sub {
  font-size: var(--font-size-sm);
  color: var(--text-secondary);
}

.home__resume-btn {
  flex-shrink: 0;
  padding: 0 var(--space-md);
  min-height: var(--hit-min);
  display: flex;
  align-items: center;
  border-radius: var(--radius-ctrl);
  background: var(--color-primary);
  color: var(--text-inverse);
  font-size: var(--font-size-base);
}

/* ── 无档案引导建档卡 ── */
.home__profile-hint {
  display: flex;
  align-items: center;
  gap: var(--space-md);
  padding: var(--space-md);
  margin-bottom: var(--space-md);
  border-radius: var(--radius-card);
  background: var(--color-warning-bg);
}

.home__profile-hint-text {
  flex: 1;
  min-width: 0;
  font-size: var(--font-size-sm);
  line-height: 1.5;
  color: var(--text-secondary);
}

.home__profile-hint-btn {
  flex-shrink: 0;
  padding: 0 var(--space-md);
  min-height: var(--hit-min);
  display: flex;
  align-items: center;
  border-radius: var(--radius-ctrl);
  border: 2rpx solid var(--color-warning);
  color: var(--color-warning);
  font-size: var(--font-size-base);
}

/* ── 五入口宫格 ── */
.home__grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: var(--space-md);
  margin-bottom: var(--space-lg);
}

.home__entry {
  box-sizing: border-box;
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: 8rpx;
  padding: var(--space-md);
  min-height: 160rpx;
  border: 1rpx solid var(--border-color);
  border-radius: var(--radius-card);
  background: var(--bg-card);

  &.is-disabled {
    opacity: 0.55;
  }
}

.home__entry-icon {
  font-size: 44rpx;
}

.home__entry-title {
  font-size: var(--font-size-base);
  font-weight: 600;
  color: var(--text-primary);
}

.home__entry-desc {
  font-size: var(--font-size-sm);
  color: var(--text-tertiary);
}
</style>
