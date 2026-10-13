/**
 * 文件职责：「今天吃什么」（/today）纯函数工具集合——零输入直出推荐的耗时口径分组。
 * 零输入态无食材匹配语义，覆盖率三档（✅现在就能做 / 🛒差1–2样 / 💡需要多买几样）
 * 不成立，故改用耗时口径分组（≤15 分钟 / 15–30 分钟 / 需备料），
 * 对齐《12-首页双入口重构设计方案-V0.1》§6.3 规则 3。
 * 无 Vue / DOM / 网络 / store 依赖，全部为纯函数（相同输入恒定输出、无副作用），
 * 可被 vitest 在 node 环境直接单测（见 src/utils/__tests__/today.spec.ts）。
 * 从 web-stage1/src/utils/today.ts 零改造迁移（仅文件级注释追加迁移说明、类型导入路径
 * 由 @/api/types 改为本包相对路径 ../types/api，实现与导出签名不变），
 * 供小程序端（web-mini，经 vite alias @shared 引用）与 Web 端共用。
 */
import type { RecommendResultItem } from '../types/api'

/** 耗时口径分组 key：fast = ≤15 分钟 / medium = 15–30 分钟 / prep = >30 分钟或未标注 */
export type DayMenuGroupKey = 'fast' | 'medium' | 'prep'

/** 单个耗时口径分组（key + 固定标题 + 组内条目；空档不返回） */
export interface DayMenuGroup {
  /** 分组键（fast / medium / prep，即耗时档位标识） */
  key: DayMenuGroupKey
  /** 分组标题（与 W-02 三档分组标题风格一致，带图标前缀） */
  title: string
  /** 组内推荐条目（保持原数组顺序） */
  items: RecommendResultItem[]
}

/** 各耗时档固定标题（键与分组 key 一一对应） */
const GROUP_TITLES: Record<DayMenuGroupKey, string> = {
  fast: '⏱ ≤15 分钟',
  medium: '⏱ 15–30 分钟',
  prep: '🛒 需备料',
}

/** 分组展示顺序（固定 fast → medium → prep，与耗时升序口径一致） */
const GROUP_ORDER: readonly DayMenuGroupKey[] = ['fast', 'medium', 'prep']

/**
 * 零输入推荐结果按耗时口径三档分组。
 * 口径：time_minutes ≤ 15 → fast；16~30 → medium；>30 或为 null（未标注耗时）→ prep。
 * 各档内部保持原数组顺序；空档不返回（调用方直接 v-for 渲染，无需再判空）；
 * 顺序固定 fast → medium → prep。
 * @param items 零输入推荐结果条目数组（可容错 null/undefined）
 * @returns 非空分组列表（输入为空或全为空档口径时返回空数组）
 */
export function groupDayMenuByTime(items: RecommendResultItem[]): DayMenuGroup[] {
  const buckets: Record<DayMenuGroupKey, RecommendResultItem[]> = {
    fast: [],
    medium: [],
    prep: [],
  }
  for (const item of items ?? []) {
    const minutes = item.time_minutes
    if (minutes != null && minutes <= 15) {
      buckets.fast.push(item)
    } else if (minutes != null && minutes <= 30) {
      buckets.medium.push(item)
    } else {
      buckets.prep.push(item)
    }
  }
  return GROUP_ORDER.filter((key) => buckets[key].length > 0).map((key) => ({
    key,
    title: GROUP_TITLES[key],
    items: buckets[key],
  }))
}
