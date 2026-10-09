/**
 * 文件职责：全局字号档位组合式函数（对齐深色模式 useDarkMode 的单例模式，M-6/L3-4 修复）。
 * - 档位：normal（标准 16px 主字号）/ large（大 18px）/ xlarge（特大 20px）；
 * - 生效链路：watchEffect 将档位映射写入 document.documentElement 根级 CSS 变量——
 *   ① 项目字号阶 --font-sm / --font-md / --font-lg（global.css :root 的运行时覆盖，
 *      body font-size 与全部 var(--font-*) 文案随之缩放）；
 *   ② Element Plus 组件字号 --el-font-size-extra-small ~ extra-large（覆盖 el-var.css
 *      默认值，按钮 / 输入框 / 弹窗 / checkbox 等 EP 组件同步缩放）；
 * - 持久化：localStorage（key: aicook_font_size）保证刷新后任意页面立即恢复；
 *   服务器设置（PUT /v1/settings → meStore.settings.font_size）由 App.vue 在
 *   加载 / 保存后调 syncFromSettings 覆盖本地档位，实现「设置一次，全局生效」。
 */
import { ref, watchEffect } from 'vue'
import type { SettingsData } from '@/api/types'

/** 字号档位可选值（与 SettingsData.font_size 契约一致） */
export type FontSizeMode = 'normal' | 'large' | 'xlarge'

/** localStorage 持久化键 */
const STORAGE_KEY = 'aicook_font_size'

/** 档位 → 变量值映射表：font 为项目字号阶，el 为 Element Plus 组件字号阶 */
const FONT_SCALE_MAP: Record<
  FontSizeMode,
  {
    /** 项目字号阶（global.css :root 的 --font-sm/md/lg） */
    font: { sm: string; md: string; lg: string }
    /** Element Plus 字号阶（el-var.css 的 --el-font-size-*） */
    el: {
      extraSmall: string
      small: string
      base: string
      medium: string
      large: string
      extraLarge: string
    }
  }
> = {
  /** 标准：与 global.css / el-var.css 默认值一致（基准档） */
  normal: {
    font: { sm: '14px', md: '16px', lg: '18px' },
    el: { extraSmall: '12px', small: '13px', base: '14px', medium: '16px', large: '18px', extraLarge: '20px' },
  },
  /** 大：主字号 18px，各阶整体 +2px */
  large: {
    font: { sm: '16px', md: '18px', lg: '20px' },
    el: { extraSmall: '14px', small: '15px', base: '16px', medium: '18px', large: '20px', extraLarge: '22px' },
  },
  /** 特大：主字号 20px，各阶整体 +4px */
  xlarge: {
    font: { sm: '18px', md: '20px', lg: '22px' },
    el: { extraSmall: '16px', small: '17px', base: '18px', medium: '20px', large: '22px', extraLarge: '24px' },
  },
}

/**
 * 从 localStorage 读取持久化的档位值。
 * @returns 持久化的档位；无值或非法值时返回 'normal'
 * @throws 不抛出（localStorage 不可用如隐私模式时静默降级）
 */
function readStoredMode(): FontSizeMode {
  try {
    const v = localStorage.getItem(STORAGE_KEY)
    if (v === 'normal' || v === 'large' || v === 'xlarge') return v
  } catch {
    // localStorage 不可用，静默降级为标准档
  }
  return 'normal'
}

/**
 * 将档位值持久化到 localStorage（失败静默，不影响功能）。
 * @param v 待持久化的档位值
 * @returns 无
 * @throws 不抛出（持久化失败仅影响刷新恢复）
 */
function writeStoredMode(v: FontSizeMode): void {
  try {
    localStorage.setItem(STORAGE_KEY, v)
  } catch {
    // 忽略持久化失败
  }
}

/**
 * 将档位应用到 documentElement 根级 CSS 变量（项目字号阶 + Element Plus 组件字号阶）。
 * @param mode 字号档位
 * @returns 无
 */
function applyFontScale(mode: FontSizeMode): void {
  const scale = FONT_SCALE_MAP[mode]
  const rootStyle = document.documentElement.style
  // 项目字号阶（覆盖 :root 定义，body font-size 与 var(--font-*) 文案随之缩放）
  rootStyle.setProperty('--font-sm', scale.font.sm)
  rootStyle.setProperty('--font-md', scale.font.md)
  rootStyle.setProperty('--font-lg', scale.font.lg)
  // Element Plus 组件字号阶（覆盖 el-var.css 默认，EP 组件同步缩放）
  rootStyle.setProperty('--el-font-size-extra-small', scale.el.extraSmall)
  rootStyle.setProperty('--el-font-size-small', scale.el.small)
  rootStyle.setProperty('--el-font-size-base', scale.el.base)
  rootStyle.setProperty('--el-font-size-medium', scale.el.medium)
  rootStyle.setProperty('--el-font-size-large', scale.el.large)
  rootStyle.setProperty('--el-font-size-extra-large', scale.el.extraLarge)
}

/** 全局单例响应式档位（跨组件共享；初始值取 localStorage，刷新即恢复） */
const mode = ref<FontSizeMode>(readStoredMode())

// 模块级生效：档位变化（或首次调用）即写根级 CSS 变量，全站即时生效
watchEffect(() => {
  applyFontScale(mode.value)
})

/**
 * 全局字号档位组合式函数（单例状态）。
 * @returns mode 当前档位（响应式）、setFontSize 本地设定并持久化、
 *          syncFromSettings 从服务器设置同步档位（App.vue 调用）
 */
export function useFontSize() {
  /**
   * 本地设定档位并持久化（页面内直接切换场景预留；当前主链路经服务器设置同步）。
   * @param v 目标档位
   * @returns 无
   */
  function setFontSize(v: FontSizeMode): void {
    mode.value = v
    writeStoredMode(v)
  }

  /**
   * 从服务器设置同步档位（仅接受合法值；非法值忽略，保持当前档位）。
   * @param v 服务器 SettingsData.font_size（可能为 undefined/null）
   * @returns 无
   */
  function syncFromSettings(v: SettingsData['font_size'] | undefined | null): void {
    if (v === 'normal' || v === 'large' || v === 'xlarge') {
      mode.value = v
      writeStoredMode(v)
    }
  }

  return { mode, setFontSize, syncFromSettings }
}
