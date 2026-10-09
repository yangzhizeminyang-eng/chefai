/**
 * 文件职责：应用入口。
 * - 创建 Vue 应用并装配 Pinia / vue-router；
 * - 完整引入 Element Plus（中文 locale）并全局注册图标组件；
 * - 引入 Element Plus 基础样式与深色模式 CSS 变量（配合 html.dark 生效）；
 * - 引入全局样式（CSS 变量、安全色语义、通用卡片）。
 */
import { createApp } from 'vue'
import { createPinia } from 'pinia'
import ElementPlus from 'element-plus'
import zhCn from 'element-plus/es/locale/lang/zh-cn'
import * as ElementPlusIconsVue from '@element-plus/icons-vue'

// Element Plus 样式：基础 + 深色变量
import 'element-plus/dist/index.css'
import 'element-plus/theme-chalk/dark/css-vars.css'
// 全局自定义样式（置于 Element 之后，允许覆盖）
import '@/styles/global.css'

import App from './App.vue'
import router from './router'

const app = createApp(App)

// Pinia 状态管理
app.use(createPinia())
// 路由
app.use(router)
// Element Plus 完整引入，中文语言包
app.use(ElementPlus, { locale: zhCn })

// 全局注册所有 Element Plus 图标（组件名：ElIconXxx 形式，如 <ElIconWarning />）
for (const [key, component] of Object.entries(ElementPlusIconsVue)) {
  app.component(`ElIcon${key}`, component)
}

app.mount('#app')
