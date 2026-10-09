/**
 * 文件职责：远程开关状态（GET /v1/config/switches，4 模块）。
 * App 挂载时拉取一次；推荐入口根据 switches.recommend 决定是否置灰。
 * 后端不可用时回退为全开（不阻塞演示主流程）。
 */
import { defineStore } from 'pinia'
import { getSwitches } from '@/api/endpoints'
import type { Switches } from '@/api/types'

/** 默认开关（全开：后端不可用时的前端兜底） */
const DEFAULT_SWITCHES: Switches = {
  recommend: true,
  vision: true,
  qa: true,
  payment: true,
}

export const useConfigStore = defineStore('config', {
  state: () => ({
    /** 4 模块远程开关 */
    switches: { ...DEFAULT_SWITCHES } as Switches,
    /** 开关是否已成功拉取过 */
    loaded: false,
  }),
  actions: {
    /**
     * 拉取远程开关（App 挂载时调用一次；失败静默保持默认全开）。
     */
    async load(): Promise<void> {
      try {
        const res = await getSwitches()
        this.switches = { ...DEFAULT_SWITCHES, ...res }
        this.loaded = true
      } catch {
        // 后端不可用：保持默认全开，不阻塞页面
        this.loaded = false
      }
    },
  },
})
