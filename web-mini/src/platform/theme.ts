/**
 * 文件职责：深色模式平台适配——读取系统主题 + 监听主题切换，供页面根节点绑定。
 * 页面用法：`<view class="page" :class="{ dark: isDark }">`（.dark 由 global.scss 定义变量翻转）。
 * 状态为模块级单例：多处调用 useTheme() 共享同一响应式引用与监听器，避免重复注册。
 */
import { ref, type Ref } from 'vue'

/** 主题模式（对齐 uni theme 取值） */
export type ThemeMode = 'light' | 'dark'

/** 单例响应式深色标记（null 表示尚未初始化） */
let isDarkRef: Ref<boolean> | null = null

/**
 * 读取系统当前主题（同步）。
 * @returns 'dark' | 'light'；uni.getSystemInfoSync 不可用或 theme 未定义时返回 'light'
 * @throws 不抛出（同步 API 异常一律按浅色兜底）
 */
export function getSystemTheme(): ThemeMode {
  try {
    const info = uni.getSystemInfoSync()
    return info.theme === 'dark' ? 'dark' : 'light'
  } catch {
    return 'light'
  }
}

/**
 * 深色模式组合式状态（单例）：初始取系统主题，uni.onThemeChange 监听系统切换实时更新。
 * 页面根节点用法：`<view class="page" :class="{ dark: isDark }">`。
 * @returns { isDark } 响应式深色标记（Ref<boolean>，多处调用共享同一实例）
 * @throws 不抛出（onThemeChange 注册失败时静默——仅失去运行时跟随能力，初始值仍正确）
 */
export function useTheme(): { isDark: Ref<boolean> } {
  if (!isDarkRef) {
    isDarkRef = ref(getSystemTheme() === 'dark')
    try {
      uni.onThemeChange((res) => {
        if (isDarkRef) isDarkRef.value = res.theme === 'dark'
      })
    } catch {
      // 平台不支持 / 类型缺失：静默降级为固定主题
    }
  }
  return { isDark: isDarkRef }
}
