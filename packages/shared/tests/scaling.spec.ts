/**
 * 文件职责：src/utils/scaling.ts 步骤用量缩放管线单测（缺陷 M3/R3 回归）。
 * 覆盖：单值缩放（g/个/勺/ml/kg/L/只/根/片/块/瓣/颗）、范围格式（1~2g/1-2g）、
 *       时间单位不缩放（分钟/秒/小时）、无单位数字不缩放、混合文本、
 *       系数 1 / 非法系数透传、空文本边界。
 * 运行方式：npm run test（vitest run，node 环境，不挂载组件）。
 * 从 web-stage1/src/utils/__tests__/scaling.spec.ts 零改造迁移（仅本文件级注释追加迁移说明、
 * 被测模块导入路径改为 ../src/utils/scaling），用例与断言保持原样。
 */
import { describe, expect, it } from 'vitest'
import { scaleAmountHintText, scaleStepHint } from '../src/utils/scaling'

describe('scaleAmountHintText 单值用量缩放', () => {
  it('克（g）缩放：番茄 300g → 600g（factor=2）', () => {
    expect(scaleAmountHintText('番茄 300g', 2)).toBe('番茄 600g')
  })

  it('计数单位（个）缩放：鸡蛋 3 个 → 6 个（factor=2）', () => {
    expect(scaleAmountHintText('鸡蛋 3 个', 2)).toBe('鸡蛋 6 个')
  })

  it('勺单位缩放且保留空格：生抽 2 勺 → 4 勺（factor=2）', () => {
    expect(scaleAmountHintText('生抽 2 勺', 2)).toBe('生抽 4 勺')
  })

  it('毫升（ml）无空格写法缩放：料酒 15ml → 30ml（factor=2）', () => {
    expect(scaleAmountHintText('料酒 15ml', 2)).toBe('料酒 30ml')
  })

  it('缩系数（factor=0.5）减半：鸡蛋 3 个 → 1.5 个（保留 1 位小数）', () => {
    expect(scaleAmountHintText('鸡蛋 3 个', 0.5)).toBe('鸡蛋 1.5 个')
  })

  it('kg/千克/升/只/根/片/块/瓣/颗 单位均参与缩放', () => {
    expect(scaleAmountHintText('面粉 1kg', 3)).toBe('面粉 3kg')
    expect(scaleAmountHintText('土豆 1千克', 2)).toBe('土豆 2千克')
    expect(scaleAmountHintText('水 0.5升', 2)).toBe('水 1升')
    expect(scaleAmountHintText('鸡翅 5只', 2)).toBe('鸡翅 10只')
    expect(scaleAmountHintText('香葱 2根', 2)).toBe('香葱 4根')
    expect(scaleAmountHintText('姜片 3片', 2)).toBe('姜片 6片')
    expect(scaleAmountHintText('豆腐 1块', 2)).toBe('豆腐 2块')
    expect(scaleAmountHintText('大蒜 2瓣', 3)).toBe('大蒜 6瓣')
    expect(scaleAmountHintText('红枣 5颗', 2)).toBe('红枣 10颗')
  })

  it('一份文本中的多段用量同时缩放', () => {
    expect(scaleAmountHintText('番茄 300g；鸡蛋 3 个', 2)).toBe('番茄 600g；鸡蛋 6 个')
  })
})

describe('scaleAmountHintText 范围格式缩放', () => {
  it('波浪号范围：盐 1~2g → 2~4g（factor=2）', () => {
    expect(scaleAmountHintText('盐 1~2g', 2)).toBe('盐 2~4g')
  })

  it('全角波浪号范围：盐 1～2g → 2～4g（factor=2，保留原分隔符）', () => {
    expect(scaleAmountHintText('盐 1～2g', 2)).toBe('盐 2～4g')
  })

  it('连字符范围：干辣椒 5-8g → 10-16g（factor=2，保留原分隔符）', () => {
    expect(scaleAmountHintText('干辣椒 5-8g', 2)).toBe('干辣椒 10-16g')
  })

  it('范围与小数缩放：盐 1.5~2g → 3~4g（factor=2）', () => {
    expect(scaleAmountHintText('盐 1.5~2g', 2)).toBe('盐 3~4g')
  })

  it('范围段与单值段共存：盐 1~2g；糖 3g → 2~4g；6g（factor=2）', () => {
    expect(scaleAmountHintText('盐 1~2g；糖 3g', 2)).toBe('盐 2~4g；糖 6g')
  })
})

describe('scaleAmountHintText 时间单位不缩放', () => {
  it('分钟数不缩放：腌制 10 分钟保持原样', () => {
    expect(scaleAmountHintText('腌制 10 分钟', 2)).toBe('腌制 10 分钟')
  })

  it('秒数不缩放：焯水 30 秒保持原样', () => {
    expect(scaleAmountHintText('焯水 30 秒', 2)).toBe('焯水 30 秒')
  })

  it('小时数不缩放：小火炖 1 小时保持原样', () => {
    expect(scaleAmountHintText('小火炖 1 小时', 2)).toBe('小火炖 1 小时')
  })

  it('混合场景：时间保持、用量缩放', () => {
    expect(scaleAmountHintText('炖 50 分钟后加生抽 10ml', 2)).toBe('炖 50 分钟后加生抽 20ml')
  })
})

describe('scaleAmountHintText 无单位数字不缩放', () => {
  it('次数/序数不缩放：冲洗 2 遍保持原样', () => {
    expect(scaleAmountHintText('冲洗 2 遍', 2)).toBe('冲洗 2 遍')
  })

  it('纯数字无单位不缩放：编号 1 保持原样', () => {
    expect(scaleAmountHintText('第 1 步', 2)).toBe('第 1 步')
  })

  it('油温描述不误伤：六成热/70% 均保持原样', () => {
    expect(scaleAmountHintText('油温六成热（约 70%）', 2)).toBe('油温六成热（约 70%）')
  })
})

describe('scaleAmountHintText 边界与防御', () => {
  it('factor=1 时原样返回（不重排任何字符）', () => {
    expect(scaleAmountHintText('番茄 300g；鸡蛋 3 个', 1)).toBe('番茄 300g；鸡蛋 3 个')
  })

  it('非法系数（0/负数/NaN）原样返回', () => {
    expect(scaleAmountHintText('番茄 300g', 0)).toBe('番茄 300g')
    expect(scaleAmountHintText('番茄 300g', -2)).toBe('番茄 300g')
    expect(scaleAmountHintText('番茄 300g', Number.NaN)).toBe('番茄 300g')
  })

  it('空文本返回空串', () => {
    expect(scaleAmountHintText('', 2)).toBe('')
  })

  it('不含任何用量片段的文本原样返回', () => {
    expect(scaleAmountHintText('翻炒均匀即可出锅', 2)).toBe('翻炒均匀即可出锅')
  })
})

describe('scaleStepHint 步骤提示辅助', () => {
  it('null/undefined 提示返回空串', () => {
    expect(scaleStepHint(null, 2)).toBe('')
    expect(scaleStepHint(undefined, 2)).toBe('')
  })

  it('有效提示按系数缩放', () => {
    expect(scaleStepHint('盐 2g（约半勺）', 2)).toBe('盐 4g（约半勺）')
  })
})
