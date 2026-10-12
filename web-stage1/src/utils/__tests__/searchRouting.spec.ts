/**
 * 文件职责：src/utils/searchRouting.ts 纯函数单测（DEF-02 修复配套）。
 * 覆盖：decideHomeSearchRoute 首页搜索四分支分流（短菜名带 q 不丢词 / 问句走 ask /
 *       qa 关闭降级 / 空输入提示）；classifyQueryResult 选择页 ?q= 三类分类
 *       （命中菜谱 / 回退食材定位（名称+别名，双向包含，忽略大小写）/ 双未命中空态）。
 * 运行方式：npm run test（vitest run，node 环境，不挂载组件）。
 */
import { describe, expect, it } from 'vitest'
import { classifyQueryResult, decideHomeSearchRoute } from '../searchRouting'

describe('decideHomeSearchRoute 首页搜索分流（DEF-02）', () => {
  it('短菜名「宫保鸡丁」→ selectShort（携带 q 跳转，不再丢词）', () => {
    expect(decideHomeSearchRoute('宫保鸡丁', true)).toBe('selectShort')
  })

  it('短食材名「土豆」→ selectShort', () => {
    expect(decideHomeSearchRoute('土豆', true)).toBe('selectShort')
  })

  it('问句「土豆和牛肉能一起做什么」→ ask（走 askStore.submitQuestion）', () => {
    expect(decideHomeSearchRoute('土豆和牛肉能一起做什么', true)).toBe('ask')
  })

  it('短但含疑问词（「吃啥吗」）→ ask（QUESTION_PATTERN 短路优先）', () => {
    expect(decideHomeSearchRoute('吃啥吗', true)).toBe('ask')
  })

  it('qa 开关关闭 → selectDegraded（降级为食材名精确搜索，同样带 q）', () => {
    expect(decideHomeSearchRoute('宫保鸡丁', false)).toBe('selectDegraded')
    expect(decideHomeSearchRoute('土豆和牛肉能一起做什么', false)).toBe('selectDegraded')
  })

  it('空输入/纯空白 → emptyHint（store 出单条提示）', () => {
    expect(decideHomeSearchRoute('', true)).toBe('emptyHint')
    expect(decideHomeSearchRoute('   ', true)).toBe('emptyHint')
  })

  it('前后空白会被 trim 后再判定', () => {
    expect(decideHomeSearchRoute(' 宫保鸡丁 ', true)).toBe('selectShort')
  })
})

describe('classifyQueryResult 选择页 ?q= 消费分类（DEF-02）', () => {
  const ingredients = [
    { name: '土豆', aliases: ['马铃薯', '洋芋'] },
    { name: '番茄', aliases: ['西红柿'] },
    { name: '牛肉', aliases: [] },
  ]

  it('菜谱命中 ≥1 条 → recipes（展示结果条）', () => {
    expect(classifyQueryResult([{ id: 392 }], '宫保鸡丁', ingredients)).toBe('recipes')
  })

  it('未命中菜谱但命中食材名 → ingredient（回退食材定位）', () => {
    expect(classifyQueryResult([], '土豆', ingredients)).toBe('ingredient')
  })

  it('命中食材别名（马铃薯）→ ingredient', () => {
    expect(classifyQueryResult([], '马铃薯', ingredients)).toBe('ingredient')
  })

  it('双向包含：输入含食材名（找一个土豆）→ ingredient', () => {
    expect(classifyQueryResult([], '找一个土豆', ingredients)).toBe('ingredient')
  })

  it('忽略大小写（Tomato 不区分大小写命中别名场景）', () => {
    expect(classifyQueryResult([], 'BEEF', [{ name: 'beef' }])).toBe('ingredient')
  })

  it('双未命中 → none（走既有「试试更宽泛的关键词」空态）', () => {
    expect(classifyQueryResult([], '宫保鸡丁', ingredients)).toBe('none')
    expect(classifyQueryResult([], '鱼香肉丝', ingredients)).toBe('none')
  })

  it('空关键词 → none（不触发食材定位）', () => {
    expect(classifyQueryResult([], '', ingredients)).toBe('none')
    expect(classifyQueryResult([], '   ', ingredients)).toBe('none')
  })
})
