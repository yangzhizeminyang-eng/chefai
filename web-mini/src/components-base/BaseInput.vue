<script setup lang="ts">
/**
 * 文件级注释：基础输入框（基础件，v-model 封装 uni 内置 input/textarea）。
 * - type：text/number/digit 走 <input>；textarea 走 <textarea>（自适应高度）；
 * - 统一边框/圆角/内边距，聚焦态主色描边（focus/blur 事件驱动 class，
 *   小程序样式层无法依赖 :focus 伪类）；disabled 半透明禁用；
 * - maxlength 透传（缺省 140；-1 表示不限）。
 * 使用约束：由页面根 .page/.dark 提供主题变量上下文。
 */
import { computed, ref } from 'vue'

/** 输入框类型（textarea 走多行分支，其余透传 input 的 type） */
export type InputType = 'text' | 'textarea' | 'number' | 'digit'

/** 组件入参 */
const props = withDefaults(
  defineProps<{
    /** 输入值（v-model） */
    modelValue: string
    /** 占位文案 */
    placeholder?: string
    /** 输入类型：text/textarea/number/digit */
    type?: InputType
    /** 禁用态 */
    disabled?: boolean
    /** 最大输入长度（缺省 140；-1 不限） */
    maxlength?: number
  }>(),
  { placeholder: '', type: 'text', disabled: false, maxlength: 140 },
)

/** 值更新事件（v-model 绑定）+ 键盘确认事件（单行 input confirm，软键盘"完成/搜索"触发） */
const emit = defineEmits<{
  (e: 'update:modelValue', value: string): void
  (e: 'confirm'): void
}>()

/** 是否聚焦（驱动容器主色描边） */
const focused = ref(false)

/** 是否多行（textarea 分支） */
const isTextarea = computed(() => props.type === 'textarea')

/** input 的 type 属性值（textarea 时不使用） */
const inputType = computed(() => (props.type === 'textarea' ? 'text' : props.type))

/**
 * input 事件：回传新值。
 * 参数用 Event 宽类型 + 内部收窄（detail.value）：模板中小写 input/textarea 由编译器
 * 匹配为原生 HTML 元素事件（payload 无 detail.value 结构），而小程序运行时事件
 * 携带 detail.value——宽类型保证类型检查通过，收窄保证运行时取值正确。
 * @param e input 事件（detail.value 为新值）
 * @returns 无
 */
function onInput(e: Event): void {
  const detail = (e as { detail?: { value?: string } }).detail
  emit('update:modelValue', detail?.value ?? '')
}

/**
 * confirm 事件：软键盘确认键触发（透传给调用方，供"发送/搜索"等键盘动作绑定）。
 * @returns 无
 */
function onConfirm(): void {
  emit('confirm')
}

/** 聚焦：置 focused（主色描边） */
function onFocus(): void {
  focused.value = true
}

/** 失焦：清 focused */
function onBlur(): void {
  focused.value = false
}
</script>

<template>
  <view
    class="base-input"
    :class="{ 'is-focus': focused, 'is-disabled': disabled }"
  >
    <!-- 多行分支：textarea 自适应高度 -->
    <textarea
      v-if="isTextarea"
      class="base-input__field base-input__field--area"
      :value="modelValue"
      :placeholder="placeholder"
      :disabled="disabled"
      :maxlength="maxlength"
      auto-height
      @input="onInput"
      @focus="onFocus"
      @blur="onBlur"
    />
    <!-- 单行分支：input（type 透传 number/digit；confirm 透传软键盘确认动作） -->
    <input
      v-else
      class="base-input__field"
      :type="inputType"
      :value="modelValue"
      :placeholder="placeholder"
      :disabled="disabled"
      :maxlength="maxlength"
      :confirm-type="'search'"
      @input="onInput"
      @focus="onFocus"
      @blur="onBlur"
      @confirm="onConfirm"
    />
  </view>
</template>

<style scoped lang="scss">
/* 统一容器：边框/圆角/焦点态主色描边 */
.base-input {
  box-sizing: border-box;
  display: flex;
  align-items: center;
  min-height: var(--hit-min);
  padding: 0 var(--space-sm);
  border: 1rpx solid var(--border-color);
  border-radius: var(--radius-ctrl);
  background: var(--bg-card);
  transition: border-color 0.2s ease;

  &.is-focus {
    border-color: var(--color-primary);
  }

  &.is-disabled {
    opacity: 0.5;
  }
}

.base-input__field {
  flex: 1;
  min-height: var(--hit-min);
  width: 100%;
  font-size: var(--font-size-base);
  color: var(--text-primary);

  /* 多行：上内边距 + 行高 */
  &--area {
    padding: var(--space-xs) 0;
    line-height: 1.6;
    min-height: 160rpx;
  }
}
</style>
