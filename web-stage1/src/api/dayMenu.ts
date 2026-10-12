/**
 * 文件职责：「今天吃什么」零输入直出推荐端点封装（POST /v1/recommend/day-menu）。
 * - 请求体无必填字段：零输入即出候选；exclude_ids 用于「换一换」排除上一批 recipe_id；
 * - 匿名身份沿用全局 http 惯例（api/index.ts 请求拦截器）：POST 请求自动携带
 *   X-Anonymous-Id 头（localStorage aicook_anonymous_id，存在才携带），
 *   后端从请求头解析 anonymous_id 并加载家庭档案执行过敏原/忌口/难度/设备硬过滤；
 * - request_id 由拦截器自动注入请求体（本端点无幂等缓存，每次请求必须出新批，
 *   批次由 exclude_ids 区分，前端无需显式传幂等键）；
 * - 响应结构复用 RecommendResponse 契约：results ≤6 道且 match_level 恒为
 *   can_cook_now（零输入无覆盖语义，页面按耗时口径分组展示，不按 match_level 分组）。
 */
import apiClient from './index'
import type { RecommendResponse } from './types'

/** 「今天吃什么」零输入推荐响应体（结构同 RecommendResponse，别名复用既有契约类型） */
export type DayMenuResponse = RecommendResponse

/**
 * 零输入直出推荐（POST /v1/recommend/day-menu）。
 * @param excludeIds 上一批结果的 recipe_id 列表（「换一换」排除语义；空数组 = 首次请求）
 * @returns 推荐响应体（≤6 道候选，含 cover_image_url 可空字段；results 为空时后端附 notice 引导文案）
 */
export function fetchDayMenu(excludeIds: number[] = []): Promise<DayMenuResponse> {
  return apiClient.post('/v1/recommend/day-menu', { exclude_ids: excludeIds })
}
