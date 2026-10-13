/**
 * 文件职责：时令吃什么（GET /v1/seasonal）端点封装与契约类型。
 * 自 web-stage1/src/api/seasonal.ts 原样迁移，底层由 axios 换为本工程 request 封装。
 * - 响应含服务端当月 month（1~12）、当季食材 ingredients（按名称白名单匹配食材库）、
 *   当季菜谱 recipes（主料命中当季食材 + 同款硬过滤，≤8 道，结构同推荐结果条目）；
 * - 后端降级约定：异常/无月份映射时 ingredients/recipes 为空数组且 HTTP 恒 200，
 *   前端以「数据缺失」空态兜底，不按错误处理。
 */
import { get } from './request'
import type { RecommendResultItem } from '@shared/types'

/** 当季食材条目（后端按当月名称白名单匹配 ingredient 表返回） */
export interface SeasonalIngredient {
  /** 食材 ID（对齐食材库 ingredient.id，预置已选集合时直接复用） */
  id: number
  /** 食材名称 */
  name: string
  /** 所属分类编码（如 veg / meat / seafood ...） */
  category: string
}

/** 时令响应体（GET /v1/seasonal） */
export interface SeasonalResponse {
  /** 服务端当月月份数（1~12；供副标题展示，异常/缺失时前端不显示月份数字） */
  month: number
  /** 当季食材列表（降级时为空数组 → 页面展示「当月时令数据待补充」空态） */
  ingredients: SeasonalIngredient[]
  /** 当季菜谱列表（≤8 道，契约复用推荐结果条目 RecommendResultItem；降级时为空数组） */
  recipes: RecommendResultItem[]
}

/**
 * 拉取当月时令数据（GET /v1/seasonal，无请求参数）。
 * 沿用请求层惯例：X-Anonymous-Id 匿名身份头自动携带（storage 存在才附加），
 * GET 天然幂等无需 request_id，与 getHome() 同款写法。
 * @returns 当月时令响应体（month + ingredients + recipes；后端降级时数组为空）
 * @throws 归一化 ApiError（网络失败/超时，页面按 error 态重试兜底）
 */
export function fetchSeasonal(): Promise<SeasonalResponse> {
  return get<SeasonalResponse>('/v1/seasonal')
}
