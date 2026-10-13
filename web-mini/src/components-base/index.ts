/**
 * 文件级注释：components-base 目录统一出口（基础件，统一主题与热区）。
 * 页面可经此处统一引入（`import { BaseButton } from '@/components-base'`），
 * 也可直接路径引入（`import BaseButton from '@/components-base/BaseButton.vue'`），二者等价。
 */
export { default as BaseButton } from './BaseButton.vue'
export { default as BaseCell } from './BaseCell.vue'
export { default as BaseDialog } from './BaseDialog.vue'
export { default as BaseTag } from './BaseTag.vue'
export { default as BaseSwitch } from './BaseSwitch.vue'
export { default as BaseSlider } from './BaseSlider.vue'
export { default as BasePicker } from './BasePicker.vue'
export { default as BaseInput } from './BaseInput.vue'
export { default as BaseForm } from './BaseForm.vue'

/** 组件配套类型（页面适配数据时引用） */
export type { ButtonType, ButtonSize } from './BaseButton.vue'
export type { DialogPosition } from './BaseDialog.vue'
export type { TagKind } from './BaseTag.vue'
export type { PickerOption } from './BasePicker.vue'
export type { InputType } from './BaseInput.vue'
