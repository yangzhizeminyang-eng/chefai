<script setup lang="ts">
/**
 * 文件级注释：G-02 免责声明条（安全组件，主包内置）。
 * 自 web-stage1/src/components/DisclaimerBar.vue 迁移（variant 档位语义 → scene 场景枚举）：
 * - scene 缺省 text 缺省时按场景从 @shared/constants 取对应 DISCLAIMER_* 常量；
 * - allergen 场景固定句式收口 = ALLERGEN_ALERT_SUFFIX（「请以实际食材包装标签为准」）；
 * - text 传入时优先使用页面定制文案（仍要求引用常量，不允许散落硬编码）；
 * - 视觉：小字 --text-tertiary、上边框分隔、内边距紧凑，信息语义不使用警示色。
 * 使用约束：由页面根 .page/.dark 提供主题变量上下文。
 */
import { computed } from 'vue'
import {
  DISCLAIMER_HOME,
  DISCLAIMER_DETAIL,
  DISCLAIMER_NUTRITION,
  DISCLAIMER_RISK,
  DISCLAIMER_SHARE,
  ALLERGEN_ALERT_SUFFIX,
} from '@shared/constants'

/** 免责场景枚举（决定缺省文案档位） */
export type DisclaimerScene = 'home' | 'detail' | 'nutrition' | 'risk' | 'share' | 'allergen'

/** 组件入参 */
const props = withDefaults(
  defineProps<{
    /** 页面定制文案（可选；传入则优先于场景常量，要求引用 @shared/constants 常量） */
    text?: string
    /** 免责场景：缺省文案按场景取 @shared/constants 对应常量 */
    scene?: DisclaimerScene
  }>(),
  { text: '', scene: undefined },
)

/** 场景 → 缺省文案映射（allergen 场景固定收口句 ALLERGEN_ALERT_SUFFIX） */
const SCENE_TEXT: Record<DisclaimerScene, string> = {
  home: DISCLAIMER_HOME,
  detail: DISCLAIMER_DETAIL,
  nutrition: DISCLAIMER_NUTRITION,
  risk: DISCLAIMER_RISK,
  share: DISCLAIMER_SHARE,
  allergen: ALLERGEN_ALERT_SUFFIX,
}

/** 实际展示文案：text 优先，其次按 scene 取常量，均缺省回通用 DISCLAIMER_TEXT 档（home 同源） */
const displayText = computed(() => {
  if (props.text) return props.text
  if (props.scene) return SCENE_TEXT[props.scene]
  return DISCLAIMER_HOME
})
</script>

<template>
  <!-- 信息语义小字条：纯文字承载语义，不依赖颜色 -->
  <view class="disclaimer-bar">
    <text class="disclaimer-bar__text">{{ displayText }}</text>
  </view>
</template>

<style scoped lang="scss">
.disclaimer-bar {
  display: block;
  box-sizing: border-box;
  width: 100%;
  padding: var(--space-xs) var(--space-sm);
  border-top: 1rpx solid var(--divider);
}

.disclaimer-bar__text {
  font-size: var(--font-size-sm);
  line-height: 1.6;
  color: var(--text-tertiary);
  word-break: break-all;
}
</style>
