/**
 * 文件职责：src/utils/nutritionQuery.ts 纯函数单测（DEF-07「查看营养丢份数」）。
 * 覆盖：buildNutritionQuery（合法份数字符串化、非法份数仅带展开标记）与
 *       parseNutritionQuery（展开标记判别、1~20 整数份数校验、数组/数值/非法值兜底）。
 * 运行方式：npm run test（vitest run，node 环境，不挂载组件）。
 */
import { describe, expect, it } from 'vitest'
import { buildNutritionQuery, parseNutritionQuery } from '../nutritionQuery'

describe('buildNutritionQuery 完成页跳转 query 构造', () => {
  it('合法会话快照 → expand_nutrition=1 + 字符串化份数', () => {
    expect(buildNutritionQuery({ recipe_id: 7, servings: 3 })).toEqual({
      expand_nutrition: '1',
      servings: '3',
    })
  })

  it('份数为 1 / 20 边界仍合法', () => {
    expect(buildNutritionQuery({ recipe_id: 1, servings: 1 })).toEqual({
      expand_nutrition: '1',
      servings: '1',
    })
    expect(buildNutritionQuery({ recipe_id: 1, servings: 20 })).toEqual({
      expand_nutrition: '1',
      servings: '20',
    })
  })

  it('份数非法（0 / 21 / 非整数 / NaN）→ 仅带展开标记，不传错误份数', () => {
    expect(buildNutritionQuery({ recipe_id: 1, servings: 0 })).toEqual({ expand_nutrition: '1' })
    expect(buildNutritionQuery({ recipe_id: 1, servings: 21 })).toEqual({ expand_nutrition: '1' })
    expect(buildNutritionQuery({ recipe_id: 1, servings: 2.5 })).toEqual({ expand_nutrition: '1' })
    expect(buildNutritionQuery({ recipe_id: 1, servings: Number.NaN })).toEqual({
      expand_nutrition: '1',
    })
  })
})

describe('parseNutritionQuery 详情页入口 query 解析', () => {
  it('expand_nutrition=1 + 合法份数 → 展开 + 份数数值', () => {
    expect(parseNutritionQuery({ expand_nutrition: '1', servings: '3' })).toEqual({
      expand: true,
      servings: 3,
    })
  })

  it('未携带 query（普通进入详情页）→ 不展开、份数 null', () => {
    expect(parseNutritionQuery({})).toEqual({ expand: false, servings: null })
  })

  it('expand_nutrition 非 1 → 不展开（份数仍解析）', () => {
    expect(parseNutritionQuery({ expand_nutrition: '0', servings: '2' })).toEqual({
      expand: false,
      servings: 2,
    })
    expect(parseNutritionQuery({ expand_nutrition: 'true', servings: '2' })).toEqual({
      expand: false,
      servings: 2,
    })
  })

  it('份数越界（0 / 21）与非整数（2.5）→ null', () => {
    expect(parseNutritionQuery({ expand_nutrition: '1', servings: '0' }).servings).toBeNull()
    expect(parseNutritionQuery({ expand_nutrition: '1', servings: '21' }).servings).toBeNull()
    expect(parseNutritionQuery({ expand_nutrition: '1', servings: '2.5' }).servings).toBeNull()
  })

  it('份数非数字（abc / 空串 / null）→ null', () => {
    expect(parseNutritionQuery({ expand_nutrition: '1', servings: 'abc' }).servings).toBeNull()
    expect(parseNutritionQuery({ expand_nutrition: '1', servings: '' }).servings).toBeNull()
    expect(parseNutritionQuery({ expand_nutrition: '1', servings: null }).servings).toBeNull()
  })

  it('份数缺省 → null（仅展开营养区）', () => {
    expect(parseNutritionQuery({ expand_nutrition: '1' })).toEqual({ expand: true, servings: null })
  })

  it('数组型 query 值取首值（vue-router 同名参数）', () => {
    expect(
      parseNutritionQuery({ expand_nutrition: ['1'], servings: ['4', '9'] as unknown }),
    ).toEqual({ expand: true, servings: 4 })
  })

  it('数值型 servings（1~20 整数）直接通过', () => {
    expect(parseNutritionQuery({ expand_nutrition: 1, servings: 6 })).toEqual({
      expand: true,
      servings: 6,
    })
  })
})
