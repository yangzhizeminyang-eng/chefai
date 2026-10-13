/**
 * 文件职责：全局字号三档适配（适老化/大字需求）——'sm' | 'base' | 'lg' 三档，
 * 持久化到 storage（aicook_font_size），并通过 global.scss 末尾的
 * .font-sm / .font-base / .font-lg 三个 CSS 变量覆盖类生效。
 * 页面用法：根节点 `:class="fontSizeClass"`，元素字号使用 var(--font-size-base) 等语义变量。
 * 状态为模块级单例：多处调用 useFontSize() 共享同一响应式引用。
 */
import { computed, ref, type ComputedRef, type Ref } from 'vue'
import { get as storageGet, set as storageSet } from '@/utils/storage'

/** 字号档位联合类型 */
export type FontSizeKey = 'sm' | 'base' | 'lg'

/** 字号持久化键 */
const FONT_SIZE_KEY = 'aicook_font_size'

/** 合法档位集合（读取校验用，防历史脏值） */
const VALID_KEYS: readonly FontSizeKey[] = ['sm', 'base', 'lg']

/** 单例响应式档位（null 表示尚未初始化） */
let sizeRef: Ref<FontSizeKey> | null = null

/**
 * 从 storage 读取持久化档位（非法值回落 'base'）。
 * @returns 校验通过的档位
 * @throws 不抛出（storage 异常按默认档处理）
 */
function loadSize(): FontSizeKey {
  const stored = storageGet<FontSizeKey>(FONT_SIZE_KEY)
  return stored && VALID_KEYS.includes(stored) ? stored : 'base'
}

/**
 * 字号组合式状态（单例）。
 * @returns { size } 当前档位响应式引用；{ setSize } 切换并持久化；
 *          { fontSizeClass } 形如 'font-base' 的 class 计算属性（绑定页面根节点）
 * @throws 不抛出
 */
export function useFontSize(): {
  size: Ref<FontSizeKey>
  setSize: (key: FontSizeKey) => void
  fontSizeClass: ComputedRef<string>
} {
  if (!sizeRef) {
    sizeRef = ref<FontSizeKey>(loadSize())
  }
  /**
   * 切换字号档位并持久化（storage 写失败静默，仅本次会话生效）。
   * @param key 目标档位
   * @returns 无
   * @throws 不抛出
   */
  const setSize = (key: FontSizeKey): void => {
    if (!VALID_KEYS.includes(key)) return
    if (sizeRef) sizeRef.value = key
    storageSet(FONT_SIZE_KEY, key)
  }
  /** 根节点 class（如 'font-lg'），与 global.scss 末尾三个变量覆盖类对应 */
  const fontSizeClass = computed(() => `font-${sizeRef?.value ?? 'base'}`)
  return { size: sizeRef, setSize, fontSizeClass }
}
