/**
 * 文件职责：远程开关状态（GET /v1/config/switches，5 模块）。
 * App 挂载时拉取一次；推荐/识别/问答/支付/创新各入口根据 switches 对应键决定是否置灰。
 * 后端不可用时回退为全开（不阻塞演示主流程）。
 * 阶段二新增（小程序页面 onShow 高频触发）：TTL 缓存窗口——成功拉取后 60s 内重复
 * load() 直接跳过，超窗才重拉；refreshOnShow() 供页面 onShow 调用（同走 TTL 守卫）。
 * 键名对齐后端实测（backend/app/api/v1/config.py _SWITCH_KEYS 五键：
 * recommend / vision / qa / payment / innovation；shared 类型 Switches 已含可选第 5 键）。
 */
import { defineStore } from 'pinia'
import { getSwitches } from '@/api/endpoints'
import type { Switches } from '@shared/types'

/** 开关缓存 TTL（毫秒）：成功拉取后 60s 内视为新鲜，不重复请求 */
const SWITCHES_TTL_MS = 60000

/** 默认开关（5 键全开：后端不可用时的前端兜底） */
const DEFAULT_SWITCHES: Switches = {
  recommend: true,
  vision: true,
  qa: true,
  payment: true,
  innovation: true,
}

export const useConfigStore = defineStore('config', {
  state: () => ({
    /** 5 模块远程开关（innovation 为后端可选键，缺省视为全开） */
    switches: { ...DEFAULT_SWITCHES } as Switches,
    /** 开关是否已成功拉取过 */
    loaded: false,
    /** 最近一次成功拉取的时刻（毫秒时间戳；TTL 判断依据，0 = 从未成功拉取） */
    lastLoadedAt: 0,
  }),
  actions: {
    /**
     * 拉取远程开关（失败静默保持默认全开）。
     * TTL 守卫：已成功拉取且距上次成功不足 60s 时直接跳过（不重复请求）。
     * @returns 无
     * @throws 不抛出（拉取失败静默，保持当前开关状态）
     */
    async load(): Promise<void> {
      // TTL 内跳过：lastLoadedAt 仅在成功拉取后更新，失败后可立即重试
      if (this.loaded && Date.now() - this.lastLoadedAt < SWITCHES_TTL_MS) return
      try {
        const res = await getSwitches()
        this.switches = { ...DEFAULT_SWITCHES, ...res }
        this.loaded = true
        this.lastLoadedAt = Date.now()
      } catch {
        // 后端不可用：保持默认全开，不阻塞页面
        this.loaded = false
      }
    },

    /**
     * 页面 onShow 场景的开关刷新（阶段二新增）：超 TTL 才重拉，TTL 内为无操作。
     * 语义与 load() 一致（load 内置 TTL 守卫），独立命名以表达调用意图。
     * @returns 无
     * @throws 不抛出（同 load）
     */
    async refreshOnShow(): Promise<void> {
      await this.load()
    },
  },
})
