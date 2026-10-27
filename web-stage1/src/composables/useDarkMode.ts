/**
 * 文件职责：深色模式组合式函数。
 * - 状态持久化到 localStorage（key: aicook_dark_mode，值 'light' | 'dark' | 'auto'）；
 * - 通过切换 document.documentElement.classList 的 'dark' 类生效（配合 Element Plus dark css-vars）；
 * - 默认使用浅色主题；仅用户显式选择 auto 时跟随系统 prefers-color-scheme。
 */
import { ref, watchEffect, type Ref } from 'vue'

/** 深色模式可选值 */
type DarkModeValue = 'light' | 'dark' | 'auto'

/** localStorage 持久化键 */
const STORAGE_KEY = 'aicook_dark_mode'

/** 全局单例响应式状态（跨组件共享） */
const mode: Ref<DarkModeValue> = ref(readStoredMode())

/** 系统是否偏好深色（媒体查询实时值） */
const prefersDark =
  typeof window !== 'undefined' && typeof window.matchMedia === 'function'
    ? window.matchMedia('(prefers-color-scheme: dark)')
    : null

/**
 * 从 localStorage 读取持久化的模式值。
 * @returns 持久化的模式；无值或非法值时返回 'light'（匹配产品的浅色厨房视觉）
 */
function readStoredMode(): DarkModeValue {
  try {
    const v = localStorage.getItem(STORAGE_KEY)
    if (v === 'light' || v === 'dark' || v === 'auto') return v
  } catch {
    // localStorage 不可用（隐私模式等），静默降级为 auto
  }
  return 'light'
}

/**
 * 将模式值持久化到 localStorage（失败静默，不影响功能）。
 * @param v 待持久化的模式值
 */
function writeStoredMode(v: DarkModeValue): void {
  try {
    localStorage.setItem(STORAGE_KEY, v)
  } catch {
    // 忽略持久化失败
  }
}

/**
 * 计算当前是否应处于深色模式：
 * 显式 light/dark 直接生效；auto 跟随系统 prefers-color-scheme。
 */
watchEffect(() => {
  const isDark = mode.value === 'dark' || (mode.value === 'auto' && !!prefersDark?.matches)
  document.documentElement.classList.toggle('dark', isDark)
})

// auto 模式下监听系统深浅色变化，实时同步（仅绑定一次）
if (prefersDark) {
  prefersDark.addEventListener('change', () => {
    if (mode.value === 'auto') {
      document.documentElement.classList.toggle('dark', prefersDark.matches)
    }
  })
}

/**
 * 深色模式组合式函数（单例状态）。
 * @returns mode 当前模式（响应式）、isDark 是否深色（响应式）、toggle 切换深浅、setMode 显式设定
 */
export function useDarkMode() {
  /** 是否处于深色模式（派生自 mode 与系统偏好） */
  const isDark = ref(false)
  watchEffect(() => {
    isDark.value = mode.value === 'dark' || (mode.value === 'auto' && !!prefersDark?.matches)
  })

  /**
   * 在浅色 / 深色之间切换（以当前实际生效状态为准），并持久化为显式值。
   */
  function toggle(): void {
    const next: DarkModeValue = isDark.value ? 'light' : 'dark'
    setMode(next)
  }

  /**
   * 显式设定模式并持久化。
   * @param v 目标模式（'light' | 'dark' | 'auto'）
   */
  function setMode(v: DarkModeValue): void {
    mode.value = v
    writeStoredMode(v)
  }

  return { mode, isDark, toggle, setMode }
}
