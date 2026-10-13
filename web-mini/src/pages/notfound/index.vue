<!--
  文件级注释：404 异常页（深链分包下载失败 / 页面不存在的兜底）。
  - onLoad options：redirect（来源路径，可选）——有值时说明文案补「页面不存在或加载失败」；
  - EmptyState + 「回到首页」按钮（reLaunch 首页，清栈重开）；
  - 兜底提示语义对齐 OFFLINE_UNCACHED_TEXT（分包未下载完成时内容需联网加载）。
-->
<script setup lang="ts">
import { computed, ref } from 'vue'
import { onLoad } from '@dcloudio/uni-app'
import { OFFLINE_UNCACHED_TEXT } from '@shared/constants'
import { ROUTES } from '@/utils/routes'
import { useTheme } from '@/platform/theme'
import { useFontSize } from '@/platform/fontSize'
import EmptyState from '@/components/EmptyState.vue'

/** 深色模式标记（根节点 class） */
const { isDark } = useTheme()
/** 字号档位 class（根节点 class） */
const { fontSizeClass } = useFontSize()

/** 是否携带 redirect 参数（深链进入失败：文案补「或加载失败」） */
const fromRedirect = ref(false)

/** 空态标题（按 redirect 有无微调措辞，响应式跟随 onLoad 结果） */
const titleText = computed(() => (fromRedirect.value ? '页面不存在或加载失败' : '页面不存在'))

/**
 * onLoad：解析 redirect 参数（有值即视为深链下载失败场景）。
 * @param options 页面参数（redirect 可选）
 * @returns 无
 */
onLoad((options) => {
  fromRedirect.value = !!options?.redirect
})

/**
 * 回到首页（reLaunch 清栈重开，规避来源页已失效的页面栈）。
 * @returns 无
 */
function goHome(): void {
  uni.reLaunch({ url: ROUTES.HOME, fail: () => {} })
}
</script>

<template>
  <view class="page" :class="[isDark ? 'dark' : '', fontSizeClass]">
    <view class="notfound">
      <EmptyState
        icon="🧭"
        :title="titleText"
        :desc="OFFLINE_UNCACHED_TEXT + '，可回到首页重新进入'"
        action-text="回到首页"
        @action="goHome"
      />
    </view>
  </view>
</template>

<style scoped lang="scss">
.notfound {
  box-sizing: border-box;
  min-height: 100%;
  padding-top: var(--space-xl);
}
</style>
