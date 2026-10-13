/**
 * 文件职责：src/utils/apiError.ts 纯函数单测（P0 修复 1.3 配套测试）。
 * 覆盖：format422Detail 对后端 422 detail 的两类结构解析 ——
 *       ① 当前真实口径：str(exc.errors()) 的 Python repr 串（含 tuple loc / 双引号 msg / input / ctx）；
 *       ② 防御分支：原生 FastAPI 校验错误数组 [{loc, msg, input}]；
 *       以及非 422 短路、无 detail、无法解析、未知字段、未知消息等边界。
 * repr 样例严格对齐 backend/app/main.py validation_exception_handler 的真实输出。
 * 运行方式：npm run test（vitest run，node 环境，不挂载组件）。
 * 从 web-stage1/src/utils/__tests__/apiError.spec.ts 零改造迁移（仅本文件级注释追加迁移说明、
 * 导入路径改为 ../src/types/api 与 ../src/utils/apiError），原用例保持原样；
 * 文件末尾追加阶段二增强用例（fromUniFailure uni.request fail 归一化）。
 */
import { describe, expect, it } from 'vitest'
import type { ApiError } from '../src/types/api'
import { format422Detail, fromUniFailure } from '../src/utils/apiError'

/** 构造 ApiError 的最小工厂（detail 默认不传） */
function makeError(overrides: Partial<ApiError>): ApiError {
  return { code: 400, message: '请求失败', ...overrides }
}

describe('format422Detail 短路边界', () => {
  it('非 422 错误（HTTP 400 / TIMEOUT 等）返回空串', () => {
    expect(format422Detail(makeError({ code: 400 }))).toBe('')
    expect(format422Detail(makeError({ code: 'TIMEOUT' }))).toBe('')
  })

  it('422 但无 detail / detail 为空时返回空串', () => {
    expect(format422Detail(makeError({ code: 422 }))).toBe('')
    expect(format422Detail(makeError({ code: 422, detail: null }))).toBe('')
    expect(format422Detail(makeError({ code: 422, detail: '' }))).toBe('')
  })

  it('code 为业务码 VALIDATION_ERROR（字符串）同样可解析', () => {
    expect(format422Detail(makeError({ code: 'VALIDATION_ERROR', detail: 'oops' }))).toBe('')
    // 能通过短路，进入解析（此处 detail 无条目，返回空串）
  })
})

describe('format422Detail 解析 str(exc.errors()) repr 串（后端当前口径）', () => {
  it('location 枚举错误 → 「存放位置：值必须是 … 之一（当前值：冷藏）」', () => {
    const detail = `[{'type': 'enum', 'loc': ('body', 'location'), 'msg': "Input should be 'fridge', 'freezer', 'room' or 'dry'", 'input': '冷藏', 'ctx': {'expected': "'fridge' | 'freezer' | 'room' | 'dry'"}}]`
    expect(format422Detail(makeError({ code: 422, detail }))).toBe(
      '存放位置：值必须是 fridge/freezer/room/dry 之一（当前值：冷藏）',
    )
  })

  it('多条错误以「；」连接；无 input 的条目不错位（Field required）', () => {
    const detail = `[{'type': 'missing', 'loc': ('body', 'ingredient_id'), 'msg': 'Field required'}, {'type': 'enum', 'loc': ('body', 'location'), 'msg': "Input should be 'fridge', 'freezer', 'room' or 'dry'", 'input': '冷藏'}]`
    expect(format422Detail(makeError({ code: 422, detail }))).toBe(
      '食材：缺少必填字段；存放位置：值必须是 fridge/freezer/room/dry 之一（当前值：冷藏）',
    )
  })

  it('数字层级 loc 取最后一级字段名；数字 input 展示当前值', () => {
    const detail = `[{'type': 'enum', 'loc': ('body', 'items', 0, 'quantity_level'), 'msg': "Input should be 'low', 'mid' or 'plenty'", 'input': 5}]`
    expect(format422Detail(makeError({ code: 422, detail }))).toBe(
      '数量档位：值必须是 low/mid/plenty 之一（当前值：5）',
    )
  })

  it('未收录字段名原样透出；非枚举消息原样透传', () => {
    const detail = `[{'type': 'string_too_long', 'loc': ('body', 'nickname'), 'msg': 'String should have at most 20 characters', 'input': '太长的昵称'}]`
    expect(format422Detail(makeError({ code: 422, detail }))).toBe(
      'nickname：String should have at most 20 characters',
    )
  })

  it('无 loc 的条目仅输出原因，不产生悬空冒号', () => {
    const detail = `[{'type': 'value_error', 'msg': 'Value error, 匿名会话 ID 过长'}]`
    expect(format422Detail(makeError({ code: 422, detail }))).toBe('匿名会话 ID 过长')
  })

  it('普通字符串（无 loc/msg 结构）解析不出条目 → 返回空串由调用方回退', () => {
    expect(format422Detail(makeError({ code: 422, detail: 'some plain error' }))).toBe('')
  })
})

describe('format422Detail 解析原生数组 detail（防御分支）', () => {
  it('数组条目逐条转「字段：原因」，多条以「；」连接', () => {
    const detail = [
      { type: 'missing', loc: ['body', 'ingredient_id'], msg: 'Field required' },
      {
        type: 'enum',
        loc: ['body', 'location'],
        msg: "Input should be 'fridge', 'freezer', 'room' or 'dry'",
        input: '冷藏',
      },
    ]
    expect(format422Detail(makeError({ code: 422, detail }))).toBe(
      '食材：缺少必填字段；存放位置：值必须是 fridge/freezer/room/dry 之一（当前值：冷藏）',
    )
  })

  it('数组条目缺 loc / msg 时各自仅输出可用部分，不产生悬空冒号', () => {
    const detail = [{ msg: 'Field required' }, { loc: ['body', 'location'] }]
    expect(format422Detail(makeError({ code: 422, detail }))).toBe('缺少必填字段；存放位置')
  })
})

describe('fromUniFailure uni.request fail 归一化（阶段二小程序增强）', () => {
  it('request:fail timeout → TIMEOUT / 加载超时文案（复用 normalizeError 既有口径）', () => {
    expect(fromUniFailure('request:fail timeout')).toEqual({
      code: 'TIMEOUT',
      message: '加载超时，请重试',
    })
  })

  it('request:fail 其他失败 → NETWORK / 网络连接不可用文案', () => {
    expect(fromUniFailure('request:fail abort')).toEqual({
      code: 'NETWORK',
      message: '网络连接不可用，请检查网络后重试',
    })
    expect(fromUniFailure('request:fail ')).toEqual({
      code: 'NETWORK',
      message: '网络连接不可用，请检查网络后重试',
    })
  })

  it('errMsg 为空串按 NETWORK 兜底（不抛出）', () => {
    expect(fromUniFailure('')).toEqual({
      code: 'NETWORK',
      message: '网络连接不可用，请检查网络后重试',
    })
  })
})
