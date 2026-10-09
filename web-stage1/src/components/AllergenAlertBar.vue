<script setup lang="ts">
/**
 * 组件职责：过敏原警示条（全局组件 G-03）。
 * - 红色警示条（危险语义）+ Warning 图标 + 文字；
 * - 无冲突（allergens 为空）时不渲染；
 * - 文案：有登记冲突 →「{主体}含 X、Y，与您登记的过敏原冲突」；
 *   无登记（预检提示）→「{主体}含 X、Y，请留意以下致敏原」；
 *   主体名词由 subject 控制（缺省「本菜谱」；搜索结果列表等聚合场景传「搜索结果」）；
 * - 固定句式加粗「请以实际食材包装标签为准」；
 * - 图标 + 文字齐备，不依赖颜色传达信息（灰度稿兼容）。
 */
import { computed } from 'vue'
import { Warning } from '@element-plus/icons-vue'

/** 组件入参 */
const props = withDefaults(
  defineProps<{
    /** 菜谱（或结果集合）含有的致敏原列表（空数组 → 不渲染警示条） */
    allergens: string[]
    /** 是否与用户登记过敏原冲突（true → 冲突句式；false → 留意句式） */
    conflict?: boolean
    /** 警示主体名词（缺省「本菜谱」；聚合结果场景可传「搜索结果」等，§10.2 ②） */
    subject?: string
  }>(),
  { conflict: false, subject: '本菜谱' },
)

/** 是否有致敏原需要展示（空数组隐藏组件） */
const hasAllergens = computed(() => props.allergens.length > 0)

/** 主文案：按 conflict 布尔切换固定句式（主体名词可替换） */
const mainText = computed(() => {
  const joined = props.allergens.join('、')
  return props.conflict
    ? `${props.subject}含 ${joined}，与您登记的过敏原冲突`
    : `${props.subject}含 ${joined}，请留意以下致敏原`
})
</script>

<template>
  <!-- 危险语义警示条：图标 + 文字双通道，不依赖颜色 -->
  <div v-if="hasAllergens" class="allergen-bar" role="alert">
    <!-- Warning 图标：即使无色彩也能传达警示语义 -->
    <el-icon class="allergen-bar__icon" :size="20" aria-hidden="true">
      <Warning />
    </el-icon>
    <span class="allergen-bar__text">
      {{ mainText }}
      <!-- 固定句式加粗：以实际包装标签为准 -->
      <strong class="allergen-bar__strong">，请以实际食材包装标签为准</strong>
    </span>
  </div>
</template>

<style scoped>
.allergen-bar {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 10px 14px;
  border-radius: 8px;
  background: var(--color-danger-bg);
  border: 1px solid var(--color-danger-border);
  color: var(--color-danger);
}

.allergen-bar__icon {
  flex-shrink: 0;
}

.allergen-bar__text {
  font-size: var(--font-md);
  line-height: 1.6;
}

.allergen-bar__strong {
  font-weight: 700;
}
</style>
