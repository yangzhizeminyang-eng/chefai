/**
 * 文件职责：缺料标签「过滤脏项 + 折叠」纯函数单测（DEF-04 / DEF-12 配套测试）。
 * 覆盖：
 *       ① filterValidMissing：剔除无名/纯数字/纯符号脏项（「缺 1」脏标签防御）；
 *       ② filterValidMissing：容错 null/undefined/非字符串元素与 null 列表入参；
 *       ③ filterValidMissing：去重且保持原顺序；
 *       ④ filterValidMissing：保留含文字字符的混合名（中文/英文/字母数字混合）；
 *       ⑤ foldMissingTags：≤5 全量展示（overflow=0）；
 *       ⑥ foldMissingTags：>5 折叠为前 5 个 + overflow 计数（「等 N 样」数据源）；
 *       ⑦ 端到端口径：干煸仔鸡样例（脏项 + 7 样缺料）→ 过滤后折叠正确。
 * 运行方式：npm run test（vitest run，node 环境，纯函数不挂载组件）。
 */
import { describe, expect, it } from 'vitest'

import {
  MISSING_TAGS_VISIBLE_LIMIT,
  filterValidMissing,
  foldMissingTags,
} from '@/utils/recipe'

describe('filterValidMissing（DEF-04 缺料脏项过滤）', () => {
  it('剔除纯数字与纯符号脏项，保留正常中文名', () => {
    expect(filterValidMissing(['1', '32', '<', '', '   ', '鸡腿', '土豆'])).toEqual([
      '鸡腿',
      '土豆',
    ])
  })

  it('容错 null/undefined/非字符串元素，入参为 null 时返回空数组', () => {
    expect(filterValidMissing([null, undefined, 1, '鸡腿'])).toEqual(['鸡腿'])
    expect(filterValidMissing(null)).toEqual([])
    expect(filterValidMissing(undefined)).toEqual([])
  })

  it('同名项去重且保持首现顺序（避免 v-for :key 重复告警）', () => {
    expect(filterValidMissing(['鸡腿', '土豆', '鸡腿', ' 鸡腿 ', '青椒'])).toEqual([
      '鸡腿',
      '土豆',
      '青椒',
    ])
  })

  it('保留含文字字符的混合名（中文/英文/字母数字混合），名称 strip 后输出', () => {
    expect(filterValidMissing([' 郫县红油豆瓣酱 ', 'A4纸', 'Salt', '维生素B1'])).toEqual([
      '郫县红油豆瓣酱',
      'A4纸',
      'Salt',
      '维生素B1',
    ])
  })
})

describe('foldMissingTags（DEF-12 缺料标签折叠）', () => {
  it('阈值常量为 5', () => {
    expect(MISSING_TAGS_VISIBLE_LIMIT).toBe(5)
  })

  it('不超过阈值时全量展示且无折叠项', () => {
    const five = ['a', 'b', 'c', 'd', 'e']
    expect(foldMissingTags(five)).toEqual({ visible: five, overflow: 0 })
    expect(foldMissingTags([])).toEqual({ visible: [], overflow: 0 })
  })

  it('超过阈值时只展示前 5 个，余量计入 overflow', () => {
    const seven = ['a', 'b', 'c', 'd', 'e', 'f', 'g']
    expect(foldMissingTags(seven)).toEqual({ visible: ['a', 'b', 'c', 'd', 'e'], overflow: 2 })
    // 自定义阈值生效
    expect(foldMissingTags(seven, 2)).toEqual({ visible: ['a', 'b'], overflow: 5 })
  })

  it('端到端口径：干煸仔鸡样例（脏项剔除后 6 样 → 前 5 个 + 等 1 样）', () => {
    // 复刻缺陷现场：DB 脏行 name='1' 排在主料首位 + 6 个真实缺料
    const raw = ['1', '鸡腿', '土豆', '青椒', '大蒜', '郫县红油豆瓣酱', '花椒碎']
    const valid = filterValidMissing(raw)
    expect(valid).toEqual(['鸡腿', '土豆', '青椒', '大蒜', '郫县红油豆瓣酱', '花椒碎'])
    expect(foldMissingTags(valid)).toEqual({
      visible: ['鸡腿', '土豆', '青椒', '大蒜', '郫县红油豆瓣酱'],
      overflow: 1,
    })
  })
})
