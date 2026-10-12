/**
 * 文件职责：src/utils/image.ts 单测（Task 9 + 长边下采样适配）。
 * 覆盖：computeScaledSize 等比缩放（含非法系数兜底）、compressImage 主流程 ——
 *       无需下采样且体积达标透传、长边超限下采样（4032×3024 → 1280×960、
 *       体积达标但长边超限仍重编码的透传语义变化）、小图不放大、非 File 入参抛错、
 *       无 document 环境抛错、mock canvas 下一次压缩达标 / 多轮降质收敛 /
 *       质量到底后缩尺寸收敛。
 * 运行方式：npm run test（vitest run，node 环境；mock 全局 document 与 createImageBitmap）。
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { compressImage, computeScaledSize } from '../image'

/** 保存原始全局对象（测试后恢复，避免污染其他用例） */
const originalDocument = globalThis.document
const originalCreateImageBitmap = (globalThis as Record<string, unknown>).createImageBitmap

/**
 * 设置 mock 位图尺寸（重设 globalThis.createImageBitmap，用例内按需覆盖；
 * beforeEach 默认 4000×3000 典型手机照片）。
 * @param width mock 位图宽度（px）
 * @param height mock 位图高度（px）
 * @returns 无
 */
function setBitmapSize(width: number, height: number): void {
  ;(globalThis as Record<string, unknown>).createImageBitmap = vi.fn(async () => ({
    width,
    height,
    close: vi.fn(),
  }))
}

/**
 * 生成 mock canvas 元素：toBlob 按 宽×高×质量/10000 生成对应大小的 Blob，
 * 用于模拟「尺寸/质量越大 → 编码结果越大」的真实行为。
 * @param sizeSpy 质量调用记录数组（可选，供断言尝试轮次）
 * @param dimsSpy 画布尺寸记录数组（可选，供断言长边下采样是否生效）
 * @returns 可塞进 document.createElement 的 canvas 桩
 */
function makeCanvasStub(
  sizeSpy?: Array<{ quality: number }>,
  dimsSpy?: Array<{ width: number; height: number }>,
) {
  const canvas = {
    width: 0,
    height: 0,
    getContext: () => ({ drawImage: vi.fn() }),
    toBlob: (cb: (b: Blob | null) => void, _type: string, quality: number) => {
      sizeSpy?.push({ quality })
      dimsSpy?.push({ width: canvas.width, height: canvas.height })
      const bytes = Math.max(1, Math.round((canvas.width * canvas.height * quality) / 10000))
      cb(new Blob([new Uint8Array(bytes)]))
    },
  }
  return canvas
}

beforeEach(() => {
  // 每个用例重建全局 mock：createImageBitmap 返回固定尺寸位图（4000×3000）
  setBitmapSize(4000, 3000)
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

describe('compressImage 长边下采样（视觉模型 token 优化）', () => {
  it('无需下采样且体积达标：直接透传原文件（同一引用，不重编码）', async () => {
    setBitmapSize(1000, 800)
    globalThis.document = {
      createElement: () => makeCanvasStub(),
    } as unknown as Document
    const file = makeFile(500)
    const out = await compressImage(file, 1024 * 1024)
    expect(out).toBe(file)
  })

  it('体积达标但长边超限：仍下采样重编码为 1280×960（透传语义变化）', async () => {
    // 2000×1500 的 300KB 图 ≤ 1MB，旧语义会透传；新语义按长边 1280 下采样
    setBitmapSize(2000, 1500)
    const dims: Array<{ width: number; height: number }> = []
    globalThis.document = {
      createElement: () => makeCanvasStub(undefined, dims),
    } as unknown as Document
    const file = makeFile(300 * 1024)
    const out = await compressImage(file, 1024 * 1024)
    expect(out).not.toBe(file)
    expect(dims[0]).toEqual({ width: 1280, height: 960 })
    expect(out.size).toBe(98) // 1280×960×0.8/10000
    expect(out.type).toBe('image/jpeg')
  })

  it('4032×3024 手机原图：首轮编码前降为 1280×960，结果 ≤1MB', async () => {
    setBitmapSize(4032, 3024)
    const dims: Array<{ width: number; height: number }> = []
    globalThis.document = {
      createElement: () => makeCanvasStub(undefined, dims),
    } as unknown as Document
    const file = makeFile(5 * 1024 * 1024)
    const out = await compressImage(file, 1024 * 1024)
    expect(dims[0]).toEqual({ width: 1280, height: 960 })
    expect(out.size).toBe(98)
    expect(out.size).toBeLessThanOrEqual(1024 * 1024)
  })

  it('小图（长边 ≤1280）不放大：体积超标时按原尺寸进入压缩循环', async () => {
    setBitmapSize(1000, 800)
    const dims: Array<{ width: number; height: number }> = []
    globalThis.document = {
      createElement: () => makeCanvasStub(undefined, dims),
    } as unknown as Document
    const file = makeFile(5 * 1024 * 1024)
    const out = await compressImage(file, 1024 * 1024)
    // 首轮画布 = 原尺寸 1000×800（不被放大到 1280），一次编码命中
    expect(dims[0]).toEqual({ width: 1000, height: 800 })
    expect(out.size).toBe(64) // 1000×800×0.8/10000
  })
})

describe('compressImage 图片压缩', () => {
  it('非 File 入参抛出中文错误', async () => {
    await expect(compressImage(undefined as unknown as File, 1000)).rejects.toThrow('请选择图片文件')
  })

  it('无 document 环境（node 裸跑）抛出环境不支持', async () => {
    // @ts-expect-error 测试模拟无 DOM 环境
    delete globalThis.document
    const file = makeFile(5 * 1024 * 1024)
    await expect(compressImage(file, 1024 * 1024)).rejects.toThrow('当前环境不支持图片压缩')
  })

  it('一次编码即达标：按起始质量 0.8 输出 JPEG File（长边 4000 已先降到 1280）', async () => {
    globalThis.document = {
      createElement: () => makeCanvasStub(),
    } as unknown as Document
    const file = makeFile(5 * 1024 * 1024)
    // 下采样后 1280×960×0.8/10000 = 98 字节 ≤ 1000 → 一发命中
    const out = await compressImage(file, 1000)
    expect(out.name).toBe('fridge_compressed.jpg')
    expect(out.type).toBe('image/jpeg')
    expect(out.size).toBe(98)
  })

  it('多轮降质量收敛：逐轮 -0.2 直到达标', async () => {
    const attempts: Array<{ quality: number }> = []
    globalThis.document = {
      createElement: () => makeCanvasStub(attempts),
    } as unknown as Document
    const file = makeFile(5 * 1024 * 1024)
    // 下采样后 1280×960：q0.8→98、q0.6→74、q0.4→49 命中（上限 50）
    const out = await compressImage(file, 50)
    expect(out.size).toBe(49)
    // 3 轮编码（quality 记录于 spy）
    expect(attempts.length).toBe(3)
  })

  it('质量到底后改缩尺寸收敛：scale 递减直至达标', async () => {
    globalThis.document = {
      createElement: () => makeCanvasStub(),
    } as unknown as Document
    const file = makeFile(5 * 1024 * 1024)
    // 下采样后 1280×960（初始 scale=0.32）：质量轮 0.8/0.6/0.4/0.2 → 98/74/49/25
    // 均超标（上限 20）→ 缩尺寸轮 scale 0.32×0.8=0.256 → 1024×768 ×0.2/10000 ≈ 16 命中
    const out = await compressImage(file, 20)
    expect(out.size).toBe(16)
  })
})
