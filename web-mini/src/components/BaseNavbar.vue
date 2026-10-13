<script setup lang="ts">
/**
 * 文件级注释：基础导航栏（业务组件，custom navigationStyle 页面专用，如烹饪引导页 P-15）。
 * 小程序自定义导航栏结构：
 * - 状态栏高度占位：uni.getSystemInfoSync().statusBarHeight（px，取不到回落 20px）；
 * - 内容行：返回箭头（CSS 双线箭头，热区 ≥88rpx）+ 居中标题；
 * - backConfirmText 有值：点返回先 uni.showModal 二次确认，确认后 uni.navigateBack
 *   （P-15 沉浸式烹饪页返回二次确认，防误触中断烹饪）；无值直接返回；
 * - fixed 定位 + 自带占位块（placeholder 高度 = 状态栏 px + 内容行 88rpx），
 *   页面无需再留白。
 * 使用约束：页面 navigationStyle 必须为 custom；由页面根 .page/.dark 提供主题变量。
 */
import { computed } from 'vue'

/** 组件入参 */
const props = withDefaults(
  defineProps<{
    /** 导航栏标题 */
    title: string
    /** 返回二次确认文案（可选；有值则弹 uni.showModal 确认后再返回） */
    backConfirmText?: string
    /** 是否展示返回箭头（首页/tabBar 页等无返回场景传 false） */
    showBack?: boolean
  }>(),
  { backConfirmText: '', showBack: true },
)

/**
 * 读取系统状态栏高度（px）。
 * @returns statusBarHeight（取不到回落 20）
 * @throws 不抛出（同步 API 异常一律回落默认值）
 */
function readStatusBarHeight(): number {
  try {
    const info = uni.getSystemInfoSync()
    return typeof info.statusBarHeight === 'number' ? info.statusBarHeight : 20
  } catch {
    return 20
  }
}

/** 状态栏高度（px，组件创建时读取一次；小程序运行期状态栏高度不变） */
const statusBarHeight = readStatusBarHeight()

/** 内容行是否展示返回箭头 */
const showBack = computed(() => props.showBack)

/**
 * 点击返回：backConfirmText 有值先二次确认（uni.showModal），确认后 uni.navigateBack；
 * 无值直接返回。
 * @returns 无
 * @throws 不向外抛出（showModal/navigateBack 失败静默：无栈可弹时系统自忽略）
 */
function onBack(): void {
  if (props.backConfirmText) {
    uni.showModal({
      title: '提示',
      content: props.backConfirmText,
      /** 用户确认 → 返回上一页 */
      success: (res) => {
        if (res.confirm) uni.navigateBack({})
      },
      /** 取消/失败静默：停留当前页 */
      fail: () => {},
    })
    return
  }
  uni.navigateBack({})
}
</script>

<template>
  <view class="base-navbar">
    <!-- fixed 导航栏：状态栏占位（px）+ 内容行（88rpx） -->
    <view class="base-navbar__fixed">
      <view class="base-navbar__status" :style="{ height: `${statusBarHeight}px` }" />
      <view class="base-navbar__content">
        <view v-if="showBack" class="base-navbar__back" @click="onBack">
          <view class="base-navbar__back-icon" />
        </view>
        <text class="base-navbar__title">{{ title }}</text>
      </view>
    </view>
    <!-- 文档流占位块：防止页面内容被 fixed 导航遮挡 -->
    <view class="base-navbar__placeholder">
      <view :style="{ height: `${statusBarHeight}px` }" />
      <view class="base-navbar__content-height" />
    </view>
  </view>
</template>

<style scoped lang="scss">
.base-navbar {
  display: block;
  width: 100%;
}

.base-navbar__fixed {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  z-index: 100;
  background: var(--bg-card);
  border-bottom: 1rpx solid var(--divider);
}

.base-navbar__status {
  width: 100%;
}

.base-navbar__content {
  position: relative;
  box-sizing: border-box;
  display: flex;
  align-items: center;
  justify-content: center;
  height: var(--hit-min);
  padding: 0 var(--space-md);
}

/* 返回箭头热区：≥88rpx，左缘对齐 */
.base-navbar__back {
  position: absolute;
  left: 0;
  top: 0;
  box-sizing: border-box;
  width: var(--hit-min);
  height: var(--hit-min);
  display: flex;
  align-items: center;
  justify-content: center;
}

/* CSS 双线箭头（L 形旋转 45°），不依赖图标库 */
.base-navbar__back-icon {
  width: 20rpx;
  height: 20rpx;
  border-left: 4rpx solid var(--text-primary);
  border-bottom: 4rpx solid var(--text-primary);
  transform: rotate(45deg);
  margin-left: 8rpx;
}

.base-navbar__title {
  max-width: 60%;
  font-size: var(--font-size-lg);
  font-weight: 600;
  color: var(--text-primary);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

/* 文档流占位：状态栏 + 内容行高度 */
.base-navbar__placeholder {
  display: block;
  width: 100%;
}

.base-navbar__content-height {
  height: var(--hit-min);
}
</style>
