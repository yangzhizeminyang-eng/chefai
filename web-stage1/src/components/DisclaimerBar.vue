<script setup lang="ts">
/**
 * 组件职责：免责声明条（全局组件 G-02）。
 * - 固定附着于首页底部 / 菜谱详情 / 营养区 / 风控拦截页；
 * - variant = 'default'：通用免责文案；
 * - variant = 'nutrition'：追加「估算值」标注句；
 * - 视觉：小字灰蓝（信息语义，不使用危险/警示色）。
 */
/** 组件入参：variant 决定文案档位 */
withDefaults(
  defineProps<{
    /** 文案档位：default 通用 / nutrition 营养区（追加估算值标注） */
    variant?: 'default' | 'nutrition'
  }>(),
  { variant: 'default' },
)

/** 通用免责文案（G-02 固定句式） */
const DEFAULT_TEXT =
  '本产品仅提供烹饪与饮食参考，不构成医疗或营养治疗建议；食品安全提示请以实物标签与官方指南为准。'

/** 营养区追加文案（估算值标注） */
const NUTRITION_APPENDIX = '以上数据为估算值，非实测值，误差约 ±15%，仅供饮食参考。'
</script>

<template>
  <!-- 信息语义小字条：灰蓝色，不依赖颜色（纯文字承载语义） -->
  <div class="disclaimer-bar disclaimer-text" role="note">
    <span>{{ DEFAULT_TEXT }}</span>
    <!-- nutrition 档位追加估算值标注 -->
    <span v-if="variant === 'nutrition'">{{ NUTRITION_APPENDIX }}</span>
  </div>
</template>

<style scoped>
.disclaimer-bar {
  display: block;
  padding: 8px 12px;
  border-top: 1px solid var(--color-info-border);
}

.disclaimer-bar span {
  display: inline;
}

.disclaimer-bar span + span {
  margin-left: 4px;
}
</style>
