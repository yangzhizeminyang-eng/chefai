/**
 * 文件职责：库存模块纯工具函数（存放位置枚举 ↔ 中文标签映射）。
 * 修复 P0-H1 / L4-2：后端 /v1/inventory 仅接受位置枚举 fridge/freezer/room/dry
 * （DB 列 storage 受 chk_storage 约束，见 backend/app/models/cooking.py:47；
 * API 契约见 backend/app/schemas/inventory.py 的 StorageLocation）。
 * 前端此前用中文标签「冷藏」等直接充当表单值提交，导致新增条目必现 422。
 * 本模块提供唯一事实源：选项用 {label, value} 双值结构，展示统一走 locationLabel()。
 * 无 Vue / DOM / 网络 / store 依赖，纯函数可被 vitest 在 node 环境直接单测。
 * 从 web-stage1/src/utils/inventory.ts 零改造迁移（仅文件级注释追加迁移说明、类型导入路径
 * 由 @/api/types 改为本包相对路径 ../types/api，实现与导出签名不变），
 * 供小程序端（web-mini，经 vite alias @shared 引用）与 Web 端共用。
 */
import type { StorageLocation } from '../types/api'

/** 位置枚举 → 中文标签映射（与后端 StorageLocation 四值一一对应，未知值由 locationLabel 原样返回） */
export const LOCATION_LABELS: Record<StorageLocation, string> = {
  fridge: '冷藏',
  freezer: '冷冻',
  room: '常温',
  dry: '阴凉干燥',
}

/** 位置选项列表（label = 中文展示文案，value = 提交给后端的枚举值），供单选组/下拉遍历 */
export const LOCATION_OPTIONS: ReadonlyArray<{ label: string; value: StorageLocation }> = (
  Object.keys(LOCATION_LABELS) as StorageLocation[]
).map((value) => ({ label: LOCATION_LABELS[value], value }))

/**
 * 位置值转中文展示文案（库存列表位置列、详情等统一入口）。
 * @param location 位置枚举值（fridge/freezer/room/dry）；兼容历史脏数据（任意字符串）与空值
 * @returns 已知枚举返回对应中文标签；空值返回「位置未记录」；未知值原样返回（不吞异常数据）
 */
export function locationLabel(location?: string | null): string {
  if (!location) return '位置未记录'
  return LOCATION_LABELS[location as StorageLocation] ?? location
}
