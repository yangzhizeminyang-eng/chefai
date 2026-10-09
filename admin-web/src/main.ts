/**
 * 文件职责：后台管理端应用入口。
 * - 创建 Vue 应用并装配 Pinia / vue-router；
 * - 完整引入 Element Plus（中文 locale）并全局注册图标组件；
 * - 引入 Element Plus 基础样式与全局自定义样式（后台标准亮色主题）。
 */
import { createApp } from 'vue'
import { createPinia } from 'pinia'
import ElementPlus from 'element-plus'
import zhCn from 'element-plus/es/locale/lang/zh-cn'
import * as ElementPlusIconsVue from '@element-plus/icons-vue'

// Element Plus 基础样式
import 'element-plus/dist/index.css'
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

// 全局注册所有 Element Plus 图标（组件名：ElIconXxx 形式，如 <ElIconSearch />）
for (const [key, component] of Object.entries(ElementPlusIconsVue)) {
  app.component(`ElIcon${key}`, component)
}

app.mount('#app')
