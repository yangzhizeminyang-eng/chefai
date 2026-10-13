/**
 * 文件级注释：小程序入口——创建应用、挂载 Pinia（样式与全局错误捕获见 App.vue）。
 * uni-app 规范：入口通过 export createApp() 供编译器在各端调用，不直接 new Vue 实例。
 * 🔴 红线：createApp() 必须返回 { app } 对象（uni-app 编译器生成的启动代码为
 * `createApp().app.mount("#app")`，若直接返回 Vue 实例则 `.app` 为 undefined，
 * 运行时抛 "Cannot read property 'mount' of undefined" 导致 app.js 崩溃、
 * getApp() 为空、全 App 白屏——历史缺陷，勿回退）。
 */
import { createSSRApp } from 'vue'
import { createPinia } from 'pinia'
import App from './App.vue'

/**
 * 创建应用实例（uni-app 规范入口，每端调用一次）
 * @returns 包含 app 属性（Vue 应用实例，已挂载 Pinia）的对象——uni-app 编译器契约
 */
export function createApp() {
  const app = createSSRApp(App)
  app.use(createPinia())
  return { app }
}
