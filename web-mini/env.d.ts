/**
 * 文件级注释：全局类型引用与模块声明——引入 uni-app 平台类型、
 * uni 内置组件模板类型（@uni-helper/uni-app-types），并声明 .vue 单文件组件模块。
 */
/// <reference types="@dcloudio/types" />
/// <reference types="@uni-helper/uni-app-types" />

declare module '*.vue' {
  import { DefineComponent } from 'vue'
  /** 任意 Vue 单文件组件的宽松类型（模板类型由 vue-tsc 按文件推导） */
  const component: DefineComponent<Record<string, never>, Record<string, never>, unknown>
  export default component
}
