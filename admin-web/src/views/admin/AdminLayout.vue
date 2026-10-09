<!-- 文件职责：后台整体布局（侧边栏分组菜单 + 顶栏用户区 + 主内容路由出口）。
     只读角色菜单项保持可见，写操作在各页面内由 ensureWritable 统一拦截提示。 -->
<script setup lang="ts">
/**
 * 布局逻辑：菜单分组渲染、角色标签展示、退出登录确认。
 */
import { computed } from 'vue'
import type { Component } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import { Apple, ChatDotRound, Dish, Document, Food, Lock, MagicStick, Memo, Odometer, Search, ShoppingCart, Switch as SwitchIcon, User, Warning } from '@element-plus/icons-vue'

import { ROLE_LABELS } from '@/api/admin'
import { useAuthStore } from '@/stores/auth'
import { confirmAction } from '@/utils/interaction'

/** 菜单项 */
interface MenuItem {
  path: string
  label: string
  icon: Component
}

/** 菜单分组 */
interface MenuGroup {
  title: string
  items: MenuItem[]
}

/** 侧边栏菜单分组配置（共 14 个入口） */
const menuGroups: MenuGroup[] = [
  {
    title: '概览',
    items: [{ path: '/dashboard', label: '看板', icon: Odometer }],
  },
  {
    title: '内容管理',
    items: [
      { path: '/recipes', label: '菜谱管理', icon: Dish },
      { path: '/ingredients', label: '食材库', icon: Apple },
      { path: '/nutrition', label: '营养数据', icon: Food },
    ],
  },
  {
    title: '风控安全',
    items: [
      { path: '/risk-rules', label: '风控规则', icon: Lock },
      { path: '/sensitive-words', label: '违禁词', icon: Warning },
      { path: '/trace-logs', label: 'Agent 日志', icon: Document },
    ],
  },
  {
    title: '运营支持',
    items: [
      { path: '/feedbacks', label: '反馈工单', icon: ChatDotRound },
      { path: '/orders', label: '订单管理', icon: ShoppingCart },
    ],
  },
  {
    title: '创新中心',
    items: [
      { path: '/innovation-rules', label: '创新规则库', icon: MagicStick },
      { path: '/innovation-inspect', label: '创新菜巡检', icon: Search },
    ],
  },
  {
    title: '系统管理',
    items: [
      { path: '/admin-users', label: '成员权限', icon: User },
      { path: '/operation-logs', label: '操作日志', icon: Memo },
      { path: '/switches', label: '远程开关', icon: SwitchIcon },
    ],
  },
]

const route = useRoute()
const router = useRouter()
const auth = useAuthStore()

/** 角色中文标签 */
const roleLabel = computed<string>(() => ROLE_LABELS[auth.role] ?? auth.role)

/**
 * 退出登录：确认后清理登录态并跳转登录页。
 */
async function handleLogout(): Promise<void> {
  if (!await confirmAction('确认退出登录？', '退出')) return
  auth.logout()
  router.push('/login')
}
</script>

<template>
  <el-container class="layout">
    <el-aside width="220px" class="aside">
      <div class="brand">AI 厨娘 · 管理后台</div>
      <el-menu router :default-active="route.path" class="menu">
        <el-menu-item-group v-for="group in menuGroups" :key="group.title" :title="group.title">
          <el-menu-item v-for="item in group.items" :key="item.path" :index="item.path">
            <el-icon><component :is="item.icon" /></el-icon>
            <span>{{ item.label }}</span>
          </el-menu-item>
        </el-menu-item-group>
      </el-menu>
    </el-aside>
    <el-container>
      <el-header class="header">
        <span class="page-title">{{ route.meta.title }}</span>
        <div class="header-right">
          <span class="username">{{ auth.username || '未登录' }}</span>
          <el-tag :type="auth.isReadonly ? 'info' : auth.isSuperAdmin ? 'danger' : 'primary'">{{ roleLabel }}</el-tag>
          <el-button link type="danger" @click="handleLogout">退出</el-button>
        </div>
      </el-header>
      <el-main class="main">
        <router-view />
      </el-main>
    </el-container>
  </el-container>
</template>

<style scoped>
.layout {
  height: 100vh;
}

.aside {
  border-right: 1px solid var(--el-border-color-light);
  background: var(--el-bg-color);
  overflow-y: auto;
}

.brand {
  height: 56px;
  display: flex;
  align-items: center;
  justify-content: center;
  font-weight: 600;
  border-bottom: 1px solid var(--el-border-color-light);
}

.menu {
  border-right: none;
}

.header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  border-bottom: 1px solid var(--el-border-color-light);
  background: var(--el-bg-color);
}

.page-title {
  font-size: 16px;
  font-weight: 600;
}

.header-right {
  display: flex;
  align-items: center;
  gap: 12px;
}

.main {
  background: var(--el-bg-color-page);
  overflow-y: auto;
}
</style>
