/**
 * 测试职责：HomeView 首页食材区 TransitionGroup 直接子元素 key 约束回归。
 *
 * 背景：
 *     HomeView.vue 「手边的食材」区块的 <TransitionGroup> 有两个直接子元素：
 *     v-for 的 <span class="ingredient-chip">（:key="item.id"）与「添加更多」
 *     <button class="ingredient-add">。若 button 缺 key，开发模式下 Vue 抛出
 *     「<TransitionGroup> children must be keyed」警告，且移动/插入动画无法正确
 *     复用节点。本测试锁定该约束，防止回退。
 *
 * 实现方式说明（为何采用源码静态断言而非组件级挂载）：
 *     1. 本项目 vitest 为 node 环境（vite.config.ts test.environment='node'，
 *        无 jsdom/happy-dom），无法挂载组件；
 *     2. SSR 输出（renderToString）不含 key 属性（key 是虚拟 DOM 概念），
 *        且 TransitionGroup 的 key 校验警告仅在客户端 dev patch 阶段触发，
 *        node SSR 无法可靠捕获。
 *     因此以静态解析模板的方式校验：TransitionGroup 块内每个直接子元素标签
 *     必须携带 key（:key="..." 或 key="..."）。
 *
 * 运行环境：vitest node（纯 fs 正则解析，不挂载组件）。
 */
import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { describe, expect, it } from 'vitest'

/** 被测视图源文件路径（__tests__ 同级目录下的 HomeView.vue） */
const HOME_VIEW_SOURCE_PATH = fileURLToPath(new URL('../HomeView.vue', import.meta.url))

/** HTML 空元素（void elements）：无闭合标签，解析深度不变 */
const VOID_ELEMENTS = new Set([
  'area', 'base', 'br', 'col', 'embed', 'hr', 'img', 'input',
  'link', 'meta', 'param', 'source', 'track', 'wbr',
])

/** 解析出的直接子元素信息 */
interface DirectChild {
  /** 标签名（小写） */
  tag: string
  /** 开标签内的原始属性串（含引号内的值） */
  attrs: string
}

/**
 * 从源码中提取 TransitionGroup 块的内层内容（内部函数）。
 *
 * 参数：
 *     source：HomeView.vue 完整源码。
 *
 * 返回值：
 *     TransitionGroup 开标签之后、闭标签之前的模板内容；未找到时返回 null。
 *
 * 异常：
 *     无（未找到 TransitionGroup 返回 null，由断言显式失败）。
 */
function extractTransitionGroupInner(source: string): string | null {
  const openMatch = /<TransitionGroup\b[^>]*>/.exec(source)
  if (!openMatch) return null
  const closeIndex = source.indexOf('</TransitionGroup>', openMatch.index + openMatch[0].length)
  if (closeIndex < 0) return null
  return source.slice(openMatch.index + openMatch[0].length, closeIndex)
}

/**
 * 逐字符扫描模板内容，收集指定深度（直接子级）的开标签元素（内部函数）。
 *
 * 处理规则：
 *     - 跳过 HTML 注释（<!-- -->）；
 *     - 开标签属性串中引号内的 ">" 不视为标签结束；
 *     - 闭标签使深度 -1，空元素/自闭合标签不改变深度；
 *     - 深度从 0 进入 1 的开标签（以及深度 0 处的空/自闭合标签）记为直接子元素。
 *
 * 参数：
 *     template：TransitionGroup 内层模板内容。
 *
 * 返回值：
 *     DirectChild[]：按出现顺序排列的直接子元素列表。
 *
 * 异常：
 *     无（畸形模板仅导致收集结果为空，由断言显式失败）。
 */
function collectDirectChildren(template: string): DirectChild[] {
  const children: DirectChild[] = []
  let depth = 0
  let i = 0
  while (i < template.length) {
    if (template.startsWith('<!--', i)) {
      const end = template.indexOf('-->', i + 4)
      i = end < 0 ? template.length : end + 3
      continue
    }
    if (template[i] !== '<') {
      i += 1
      continue
    }
    const isClosing = template[i + 1] === '/'
    let j = i + (isClosing ? 2 : 1)
    let tag = ''
    while (j < template.length && /[A-Za-z0-9-]/.test(template[j] as string)) {
      tag += template[j]
      j += 1
    }
    // 逐字符读取属性串：引号内的 ">" 不结束标签
    let attrs = ''
    let quote: string | null = null
    while (j < template.length) {
      const ch = template[j] as string
      if (quote) {
        if (ch === quote) quote = null
      } else if (ch === '"' || ch === "'") {
        quote = ch
      } else if (ch === '>') {
        break
      }
      attrs += ch
      j += 1
    }
    const selfClosing = attrs.trimEnd().endsWith('/')
    if (isClosing) {
      depth -= 1
    } else if (VOID_ELEMENTS.has(tag.toLowerCase()) || selfClosing) {
      if (depth === 0) children.push({ tag: tag.toLowerCase(), attrs })
    } else {
      depth += 1
      if (depth === 1) children.push({ tag: tag.toLowerCase(), attrs })
    }
    i = j + 1
  }
  return children
}

describe('HomeView TransitionGroup 直接子元素 key 约束', () => {
  it('食材列表 TransitionGroup 内每个直接子元素都携带 key', () => {
    const source = readFileSync(HOME_VIEW_SOURCE_PATH, 'utf-8')
    const inner = extractTransitionGroupInner(source)
    expect(inner, 'HomeView.vue 中应存在 <TransitionGroup> 块').not.toBeNull()

    const children = collectDirectChildren(inner as string)
    expect(
      children.length,
      'TransitionGroup 应至少包含食材 chip 与「添加更多」按钮两个直接子元素',
    ).toBeGreaterThanOrEqual(2)

    for (const child of children) {
      expect(
        child.attrs,
        `TransitionGroup 直接子元素 <${child.tag}> 缺少 key 属性（属性串：${child.attrs.trim()}）`,
      ).toMatch(/\bkey\s*=/)
    }

    // 语义锚点：确认解析到的是目标块（食材 chip 与添加按钮），防止解析到无关 TransitionGroup
    const tags = children.map((c) => `${c.tag}.${/class="([^"]*)"/.exec(c.attrs)?.[1] ?? ''}`)
    expect(tags.join(',')).toContain('span.ingredient-chip')
    expect(tags.join(',')).toContain('button.ingredient-add')
  })
})
