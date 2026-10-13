<script setup lang="ts">
/**
 * 文件级注释：G-03 过敏原警示条（安全组件，主包内置）。
 * 自 web-stage1/src/components/AllergenAlertBar.vue 迁移（conflict/subject 双句式收敛为
 * 小程序统一句式「含过敏原：{list}」+ 固定收口句 ALLERGEN_ALERT_SUFFIX）：
 * - warning 色背景（--color-warning-bg）+ 警示图标 + 主文案 + 收口句，图标 + 文字
 *   双通道表达，不依赖颜色传达信息（灰度稿兼容）；
 * - large 模式（烹饪页用）字号 40rpx：适老可读且整条完整可见（不用 64rpx 烹饪档
 *   --font-size-cooking，避免长句在窄屏折行溢出）；
 * - 无过敏原（allergens 为空）时整体不渲染。
 * 使用约束：由页面根 .page/.dark 提供主题变量上下文。
 */
import { computed } from 'vue'
import { ALLERGEN_ALERT_SUFFIX } from '@shared/constants'

/** 组件入参 */
const props = withDefaults(
  defineProps<{
    /** 菜谱（或结果集合）含有的致敏原列表（空数组 → 组件不渲染） */
    allergens: string[]
    /** 大字模式（烹饪引导页用）：字号 40rpx，保证烹饪中远距可读 */
    large?: boolean
  }>(),
  { large: false },
)

/** 是否有致敏原需要展示（空数组隐藏组件） */
const hasAllergens = computed(() => props.allergens.length > 0)

/** 主文案：统一句式「含过敏原：X、Y」 */
const mainText = computed(() => `含过敏原：${props.allergens.join('、')}`)
</script>

<template>
  <!-- 警示条：图标 + 文字双通道，不依赖颜色 -->
  <view v-if="hasAllergens" class="allergen-bar" :class="{ 'is-large': large }">
    <!-- 警示图标：圆底叹号，即使无色彩也传达警示语义 -->
    <view class="allergen-bar__icon">!</view>
    <view class="allergen-bar__body">
      <text class="allergen-bar__text">{{ mainText }}</text>
      <!-- 固定收口句：ALLERGEN_ALERT_SUFFIX 常量收口，逐字使用不改写 -->
      <text class="allergen-bar__strong">，{{ ALLERGEN_ALERT_SUFFIX }}</text>
    </view>
  </view>
</template>

<style scoped lang="scss">
.allergen-bar {
  box-sizing: border-box;
  display: flex;
  align-items: flex-start;
  gap: var(--space-sm);
  padding: var(--space-sm) var(--space-md);
  border-radius: var(--radius-ctrl);
  background: var(--color-warning-bg);
}

.allergen-bar__icon {
  box-sizing: border-box;
  flex-shrink: 0;
  width: 44rpx;
  height: 44rpx;
  margin-top: 2rpx;
  border-radius: var(--radius-pill);
  border: 2rpx solid var(--color-warning);
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: var(--font-size-sm);
  font-weight: 700;
  color: var(--color-warning);
  line-height: 1;
}

.allergen-bar__body {
  flex: 1;
  min-width: 0;
}

.allergen-bar__text {
  font-size: var(--font-size-sm);
  line-height: 1.6;
  color: var(--color-warning);
  word-break: break-all;
}

/* 固定收口句：加粗强调 */
.allergen-bar__strong {
  font-size: var(--font-size-sm);
  line-height: 1.6;
  font-weight: 700;
  color: var(--color-warning);
  word-break: break-all;
}

/* 大字模式（烹饪页）：40rpx 适老可读且整条完整可见 */
.allergen-bar.is-large .allergen-bar__text,
.allergen-bar.is-large .allergen-bar__strong {
  font-size: 40rpx;
}

.allergen-bar.is-large .allergen-bar__icon {
  width: 56rpx;
  height: 56rpx;
  font-size: var(--font-size-base);
}
</style>
