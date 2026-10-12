/**
 * 文件职责：图像压缩工具（Task 9 / 识别页上传前的前端压缩）。
 * - compressImage(file, maxBytes, maxEdge)：先按长边 ≤ maxEdge（默认 1280px）做等比
 *   下采样（真实视觉模型按像素计 token，长边 1280 可显著降低识别成本与延迟），
 *   再按「位图缩放 + JPEG 质量递减」逐步压缩至 maxBytes 以内（输出统一 JPEG；
 *   无需下采样且体积已达标时原样透传不重编码）；
 * - computeScaledSize：等比缩放尺寸计算（纯函数，可单测）；
 * - 依赖浏览器能力（createImageBitmap / canvas / Blob），node 单测通过 mock 全局
 *   document / createImageBitmap 覆盖主流程（见 __tests__/image.spec.ts）。
 */

/** 压缩循环的尝试次数上限（质量递减 + 尺寸递减交替，6 次足够收敛） */
const MAX_ATTEMPTS = 6

/** JPEG 质量起始值（后续每轮 -0.2，下限 0.2） */
const START_QUALITY = 0.8

/** 质量下限（到达下限后改为继续缩尺寸） */
const QUALITY_FLOOR = 0.3

/** 内部已加载图像的统一视图（createImageBitmap 与 Image 兜底两种来源） */
interface LoadedImage {
  /** 可绘入 canvas 的图像源 */
  source: CanvasImageSource
  /** 原始宽度（px） */
  width: number
  /** 原始高度（px） */
  height: number
  /** 资源释放（bitmap.close / revokeObjectURL） */
  close: () => void
}

/**
 * 等比缩放尺寸计算（纯函数）。
 * @param width 原始宽度（px）
 * @param height 原始高度（px）
 * @param scale 缩放系数（0~1；<=0 或非法按 1 处理）
 * @returns 缩放后尺寸（至少 1px，四舍五入）
 */
export function computeScaledSize(
  width: number,
  height: number,
  scale: number,
): { width: number; height: number } {
  const s = Number.isFinite(scale) && scale > 0 ? scale : 1
  return {
    width: Math.max(1, Math.round(width * s)),
    height: Math.max(1, Math.round(height * s)),
  }
}

/**
 * 加载图像为可绘制源：优先 createImageBitmap（现代浏览器），
 * 兜底 Image + objectURL（老浏览器/兼容场景）。
 * @param file 图像文件
 * @returns 统一图像视图（含释放函数）
 */
async function loadImage(file: File): Promise<LoadedImage> {
  if (typeof createImageBitmap === 'function') {
    const bitmap = await createImageBitmap(file)
    return {
      source: bitmap,
      width: bitmap.width,
      height: bitmap.height,
      close: () => bitmap.close(),
    }
  }
  // 兜底：Image 元素 + object URL
  const url = URL.createObjectURL(file)
  const img = new Image()
  await new Promise<void>((resolve, reject) => {
    img.onload = () => resolve()
    img.onerror = () => reject(new Error('图片读取失败，请重试'))
    img.src = url
  })
  return {
    source: img,
    width: img.naturalWidth,
    height: img.naturalHeight,
    close: () => URL.revokeObjectURL(url),
  }
}

/**
 * canvas 导出 Blob 的 Promise 封装。
 * @param canvas 画布
 * @param type 输出 MIME
 * @param quality JPEG 质量（0~1）
 * @returns 编码后的 Blob
 */
function canvasToBlob(canvas: HTMLCanvasElement, type: string, quality: number): Promise<Blob> {
  return new Promise((resolve, reject) => {
    canvas.toBlob((blob) => {
      if (blob) resolve(blob)
      else reject(new Error('图片编码失败，请重试'))
    }, type, quality)
  })
}

/**
 * Blob → File（保留原文件主名，统一 .jpg 后缀）。
 * @param blob 编码后的图像数据
 * @param originalName 原文件名（用于保留主名）
 * @returns 可上传的 File 对象
 */
function blobToFile(blob: Blob, originalName: string): File {
  const base = originalName.replace(/\.[^.]+$/, '') || 'photo'
  return new File([blob], `${base}_compressed.jpg`, { type: 'image/jpeg' })
}

/**
 * 图片压缩主流程（识别页上传前处理）：
 * ① 加载位图后先做长边下采样判定：longEdge > maxEdge 时初始缩放系数 = maxEdge / longEdge
 *    （等比、只缩不放大）——视觉模型按像素计 token，长边压到 1280px 可显著降低
 *    识别成本与延迟（4032×3024 手机原图 → 1280×960）；
 * ② 无需下采样（initialScale === 1）且原图 ≤ maxBytes → 直接透传（不重编码，避免无谓画质损失）；
 * ③ 否则进入「降 JPEG 质量 / 缩尺寸」交替重编码循环，直至 ≤ maxBytes 或尝试耗尽；
 * ④ 尝试耗尽仍超标时返回达到的最小结果（尽力压缩，交由后端二次校验兜底）。
 * 注意透传语义变化：体积达标但长边超限的图片现在也会下采样重编码（不再透传原图）。
 * @param file 用户选择的图像文件
 * @param maxBytes 目标字节上限（如 1MB = 1024*1024）
 * @param maxEdge 长边像素上限（默认 1280；等比下采样只缩不放大）
 * @returns 压缩后的 File（JPEG；无需下采样且已达标的原图原样返回）
 * @throws Error 非图片文件 / 当前环境不支持 canvas / 图片读取失败时抛出
 */
export async function compressImage(file: File, maxBytes: number, maxEdge: number = 1280): Promise<File> {
  // 参数与类型守卫（下采样判定需先加载位图，故环境检查前置到位图加载之前）
  if (!(file instanceof File)) throw new Error('请选择图片文件')
  if (typeof document === 'undefined') throw new Error('当前环境不支持图片压缩')

  const image = await loadImage(file)
  try {
    // 长边下采样判定：longEdge 超限则按比例等比缩小（只缩不放大）
    const longEdge = Math.max(image.width, image.height)
    const initialScale = longEdge > maxEdge ? maxEdge / longEdge : 1
    // 无需下采样且体积达标 → 原样透传（同一引用返回，不重编码）
    if (initialScale === 1 && file.size <= maxBytes) return file

    let scale = initialScale
    let quality = START_QUALITY
    let smallest: File | null = null
    let smallestSize = Number.POSITIVE_INFINITY

    for (let attempt = 0; attempt < MAX_ATTEMPTS; attempt++) {
      const { width, height } = computeScaledSize(image.width, image.height, scale)
      const canvas = document.createElement('canvas')
      canvas.width = width
      canvas.height = height
      const ctx = canvas.getContext('2d')
      if (!ctx) throw new Error('当前环境不支持图片压缩')
      ctx.drawImage(image.source, 0, 0, width, height)

      const blob = await canvasToBlob(canvas, 'image/jpeg', quality)
      const outFile = blobToFile(blob, file.name)
      // 记录历史最小结果（尝试耗尽时兜底返回）
      if (blob.size < smallestSize) {
        smallestSize = blob.size
        smallest = outFile
      }
      // 达标即返回
      if (blob.size <= maxBytes) return outFile

      // 未达标：先降质量（>0.3），到底后改为缩尺寸（×0.8）
      if (quality > QUALITY_FLOOR) {
        quality = Math.max(0.2, quality - 0.2)
      } else {
        scale *= 0.8
      }
    }

    // 尝试耗尽：返回历史最小结果（尽力压缩，后端仍会校验）
    if (smallest) return smallest
    throw new Error('图片压缩失败，请重试或改用手选食材')
  } finally {
    image.close()
  }
}
