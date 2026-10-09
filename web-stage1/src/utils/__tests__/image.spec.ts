/**
 * 文件职责：src/utils/image.ts 单测（Task 9）。
 * 覆盖：computeScaledSize 等比缩放（含非法系数兜底）、compressImage 主流程 ——
 *       原图达标透传、非 File 入参抛错、无 document 环境抛错、
 *       mock canvas 下一次压缩达标 / 多轮降质收敛 / 质量到底后缩尺寸收敛。
 * 运行方式：npm run test（vitest run，node 环境；mock 全局 document 与 createImageBitmap）。
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { compressImage, computeScaledSize } from '../image'

/** mock 位图尺寸（4000×3000 的典型手机照片） */
const MOCK_WIDTH = 4000
const MOCK_HEIGHT = 3000

/** 保存原始全局对象（测试后恢复，避免污染其他用例） */
const originalDocument = globalThis.document
const originalCreateImageBitmap = (globalThis as Record<string, unknown>).createImageBitmap

/**
 * 生成 mock canvas 元素：toBlob 按 宽×高×质量/10000 生成对应大小的 Blob，
 * 用于模拟「尺寸/质量越大 → 编码结果越大」的真实行为。
 * @param sizeSpy 质量调用记录数组（可选，供断言尝试轮次）
 * @returns 可塞进 document.createElement 的 canvas 桩
 */
function makeCanvasStub(sizeSpy?: Array<{ quality: number }>) {
  const canvas = {
    width: 0,
    height: 0,
    getContext: () => ({ drawImage: vi.fn() }),
    toBlob: (cb: (b: Blob | null) => void, _type: string, quality: number) => {
      sizeSpy?.push({ quality })
      const bytes = Math.max(1, Math.round((canvas.width * canvas.height * quality) / 10000))
      cb(new Blob([new Uint8Array(bytes)]))
    },
  }
  return canvas
}

beforeEach(() => {
  // 每个用例重建全局 mock：createImageBitmap 返回固定尺寸位图
  ;(globalThis as Record<string, unknown>).createImageBitmap = vi.fn(async () => ({
    width: MOCK_WIDTH,
    height: MOCK_HEIGHT,
    close: vi.fn(),
  }))
})

afterEach(() => {
  globalThis.document = originalDocument
  ;(globalThis as Record<string, unknown>).createImageBitmap = originalCreateImageBitmap
  vi.restoreAllMocks()
})

/** 构造指定大小的测试文件 */
function makeFile(sizeBytes: number): File {
  return new File([new Uint8Array(sizeBytes)], 'fridge.png', { type: 'image/png' })
}

describe('computeScaledSize 等比缩放计算', () => {
  it('scale=1 时保持原尺寸', () => {
    expect(computeScaledSize(4000, 3000, 1)).toEqual({ width: 4000, height: 3000 })
  })

  it('按系数等比缩小并四舍五入', () => {
    expect(computeScaledSize(1000, 600, 0.8)).toEqual({ width: 800, height: 480 })
  })

  it('结果至少 1px（极端小系数不产生 0 尺寸）', () => {
    expect(computeScaledSize(10, 10, 0.0001)).toEqual({ width: 1, height: 1 })
  })

  it('非法系数（0/负数/NaN）按 1 处理', () => {
    expect(computeScaledSize(100, 50, 0)).toEqual({ width: 100, height: 50 })
    expect(computeScaledSize(100, 50, -2)).toEqual({ width: 100, height: 50 })
    expect(computeScaledSize(100, 50, Number.NaN)).toEqual({ width: 100, height: 50 })
  })
})

describe('compressImage 图片压缩', () => {
  it('原图已达标：直接透传原文件（同一引用，不重编码）', async () => {
    const file = makeFile(500)
    const out = await compressImage(file, 1024 * 1024)
    expect(out).toBe(file)
  })

  it('非 File 入参抛出中文错误', async () => {
    await expect(compressImage(undefined as unknown as File, 1000)).rejects.toThrow('请选择图片文件')
  })

  it('无 document 环境（node 裸跑）抛出环境不支持', async () => {
    // @ts-expect-error 测试模拟无 DOM 环境
    delete globalThis.document
    const file = makeFile(5 * 1024 * 1024)
    await expect(compressImage(file, 1024 * 1024)).rejects.toThrow('当前环境不支持图片压缩')
  })

  it('一次编码即达标：按起始质量 0.8 输出 JPEG File', async () => {
    // 4000×3000×0.8/10000 = 960 字节 ≤ 1000 → 一发命中
    globalThis.document = {
      createElement: () => makeCanvasStub(),
    } as unknown as Document
    const file = makeFile(5 * 1024 * 1024)
    const out = await compressImage(file, 1000)
    expect(out.name).toBe('fridge_compressed.jpg')
    expect(out.type).toBe('image/jpeg')
    expect(out.size).toBe(960)
  })

  it('多轮降质量收敛：逐轮 -0.2 直到达标', async () => {
    const attempts: Array<{ quality: number }> = []
    globalThis.document = {
      createElement: () => makeCanvasStub(attempts),
    } as unknown as Document
    const file = makeFile(5 * 1024 * 1024)
    // 上限 500：q0.8→960、q0.6→720、q0.4→480 命中
    const out = await compressImage(file, 500)
    expect(out.size).toBe(480)
    // 3 轮编码（quality 记录于 spy）
    expect(attempts.length).toBe(3)
  })

  it('质量到底后改缩尺寸收敛：scale 递减直至达标', async () => {
    globalThis.document = {
      createElement: () => makeCanvasStub(),
    } as unknown as Document
    const file = makeFile(5 * 1024 * 1024)
    // 上限 100：质量轮 0.8/0.6/0.4/0.2 均超标（960/720/480/240）→ 缩尺寸轮 0.8（154）→ 0.64（98）命中
    const out = await compressImage(file, 100)
    expect(out.size).toBe(98)
  })
})
