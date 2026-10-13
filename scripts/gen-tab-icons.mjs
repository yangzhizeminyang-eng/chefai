/**
 * 文件级注释：tabBar 图标生成脚本——零依赖，用 node 内置 zlib 手写 PNG 编码
 * （PNG 签名 + IHDR + IDAT + IEND，含纯 JS crc32 实现），
 * 生成 4 组 81×81 单色几何图标（home / fridge / fav / me）到 web-mini/src/static/tab/。
 * 规范：默认态 #8c8c8c、选中态 #ff7a45；背景透明；描边/线条 ≥6px 保证可辨识；
 * 心形用隐式方程 (x²+y²-1)³ − x²y³ < 0 判定；3×3 超采样抗锯齿。
 * 用法：node scripts/gen-tab-icons.mjs（在仓库根目录执行）。
 */
import { deflateSync } from 'node:zlib'
import { writeFileSync, mkdirSync, statSync, existsSync } from 'node:fs'
import { join, resolve, dirname } from 'node:path'
import { fileURLToPath } from 'node:url'

/** 本脚本所在目录（仓库根的 scripts/） */
const SCRIPT_DIR = dirname(fileURLToPath(import.meta.url))

/** 输出目录：web-mini/src/static/tab */
const OUT_DIR = resolve(SCRIPT_DIR, '../web-mini/src/static/tab')

/** 画布尺寸（微信 tabBar 图标推荐 81×81） */
const SIZE = 81

/** 默认态颜色 #8c8c8c */
const COLOR_IDLE = [140, 140, 140]

/** 选中态颜色 #ff7a45 */
const COLOR_ACTIVE = [255, 122, 69]

/** 3×3 超采样子像素偏移（0~1 开区间内） */
const SUB_SAMPLES = [0, 1, 2].flatMap((i) => [0, 1, 2].map((j) => [(i + 0.5) / 3, (j + 0.5) / 3]))

/** crc32 查找表（IEEE 802.3 多项式 0xEDB88320，懒初始化） */
const CRC_TABLE = (() => {
  const table = new Uint32Array(256)
  for (let n = 0; n < 256; n++) {
    let c = n
    for (let k = 0; k < 8; k++) c = c & 1 ? 0xedb88320 ^ (c >>> 1) : c >>> 1
    table[n] = c >>> 0
  }
  return table
})()

/**
 * 计算 CRC32 校验值
 * @param {Buffer|Uint8Array} buf 参与校验的字节序列（chunk type + data）
 * @returns {number} 32 位无符号 CRC 值
 */
function crc32(buf) {
  let c = 0xffffffff
  for (let i = 0; i < buf.length; i++) c = CRC_TABLE[(c ^ buf[i]) & 0xff] ^ (c >>> 8)
  return (c ^ 0xffffffff) >>> 0
}

/**
 * 组装单个 PNG chunk（length + type + data + crc）
 * @param {string} type 4 字节 chunk 类型，如 'IHDR' / 'IDAT' / 'IEND'
 * @param {Buffer} data chunk 数据体
 * @returns {Buffer} 完整 chunk 字节流
 */
function pngChunk(type, data) {
  const typeBuf = Buffer.from(type, 'ascii')
  const len = Buffer.alloc(4)
  len.writeUInt32BE(data.length, 0)
  const crc = Buffer.alloc(4)
  crc.writeUInt32BE(crc32(Buffer.concat([typeBuf, data])), 0)
  return Buffer.concat([len, typeBuf, data, crc])
}

/**
 * 将 RGBA 像素数组编码为 PNG 文件字节流
 * @param {Uint8Array} pixels 长度为 SIZE*SIZE*4 的 RGBA 像素数组
 * @returns {Buffer} 完整 PNG 文件字节流（无异常路径，输入长度不符会产生损坏文件，由内部固定遍历保证）
 */
function encodePng(pixels) {
  const signature = Buffer.from([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a])
  const ihdr = Buffer.alloc(13)
  ihdr.writeUInt32BE(SIZE, 0)
  ihdr.writeUInt32BE(SIZE, 4)
  ihdr[8] = 8 // bitDepth
  ihdr[9] = 6 // colorType: RGBA
  ihdr[10] = 0 // compression: deflate
  ihdr[11] = 0 // filter: adaptive（此处逐行用 0）
  ihdr[12] = 0 // interlace: none
  // 原始扫描线：每行前置 1 字节 filter type（0 = None）
  const raw = Buffer.alloc(SIZE * (1 + SIZE * 4))
  for (let y = 0; y < SIZE; y++) {
    const rowStart = y * (1 + SIZE * 4)
    raw[rowStart] = 0
    pixels.subarray(y * SIZE * 4, (y + 1) * SIZE * 4).forEach((v, i) => {
      raw[rowStart + 1 + i] = v
    })
  }
  const idat = deflateSync(raw, { level: 9 })
  return Buffer.concat([signature, pngChunk('IHDR', ihdr), pngChunk('IDAT', idat), pngChunk('IEND', Buffer.alloc(0))])
}

/**
 * 计算点到线段的最短距离
 * @param {number} px 点 x 坐标
 * @param {number} py 点 y 坐标
 * @param {number} x1 线段端点 1 x
 * @param {number} y1 线段端点 1 y
 * @param {number} x2 线段端点 2 x
 * @param {number} y2 线段端点 2 y
 * @returns {number} 点到线段的最短距离
 */
function segDist(px, py, x1, y1, x2, y2) {
  const dx = x2 - x1
  const dy = y2 - y1
  const lenSq = dx * dx + dy * dy
  let t = lenSq === 0 ? 0 : ((px - x1) * dx + (py - y1) * dy) / lenSq
  t = Math.max(0, Math.min(1, t))
  const cx = x1 + t * dx
  const cy = y1 + t * dy
  return Math.hypot(px - cx, py - cy)
}

/**
 * 计算点到圆角矩形（轴对齐）边界的符号距离（外部为正、内部为负）
 * @param {number} px 点 x 坐标
 * @param {number} py 点 y 坐标
 * @param {number} cx 矩形中心 x
 * @param {number} cy 矩形中心 y
 * @param {number} hw 半宽
 * @param {number} hh 半高
 * @param {number} r 圆角半径
 * @returns {number} 符号距离值
 */
function roundedRectSdf(px, py, cx, cy, hw, hh, r) {
  const qx = Math.abs(px - cx) - (hw - r)
  const qy = Math.abs(py - cy) - (hh - r)
  const outside = Math.hypot(Math.max(qx, 0), Math.max(qy, 0))
  const inside = Math.min(Math.max(qx, qy), 0)
  return outside + inside - r
}

/**
 * 绘制一个图标并编码为 PNG
 * @param {(x: number, y: number) => boolean} inside 像素中心坐标（x/y ∈ [0,81)）是否在形状内的判定函数
 * @param {number[]} color 形状填充色 [r, g, b]
 * @returns {Buffer} PNG 文件字节流
 */
function renderIcon(inside, color) {
  const pixels = new Uint8Array(SIZE * SIZE * 4)
  for (let y = 0; y < SIZE; y++) {
    for (let x = 0; x < SIZE; x++) {
      // 3×3 超采样：按覆盖率计算 alpha，实现边缘抗锯齿
      let hit = 0
      for (const [ox, oy] of SUB_SAMPLES) {
        if (inside(x + ox, y + oy)) hit++
      }
      if (hit > 0) {
        const idx = (y * SIZE + x) * 4
        pixels[idx] = color[0]
        pixels[idx + 1] = color[1]
        pixels[idx + 2] = color[2]
        pixels[idx + 3] = Math.round((255 * hit) / SUB_SAMPLES.length)
      }
    }
  }
  return encodePng(pixels)
}

/**
 * 构造"任一子形状命中即算命中"的判定函数
 * @param {Array<(x: number, y: number) => boolean>} tests 子形状判定函数列表
 * @returns {(x: number, y: number) => boolean} 组合后的判定函数
 */
const anyOf = (tests) => (x, y) => tests.some((t) => t(x, y))

/**
 * 生成一条指定宽度的线段判定函数
 * @param {number[]} a 端点 A [x, y]
 * @param {number[]} b 端点 B [x, y]
 * @param {number} halfWidth 线宽的一半（保证线宽 ≥6px）
 * @returns {(x: number, y: number) => boolean} 像素是否落在线段带宽内
 */
const seg = (a, b, halfWidth) => (x, y) => segDist(x, y, a[0], a[1], b[0], b[1]) <= halfWidth

/**
 * 图标形状定义：名称 + 81×81 坐标系下的判定函数（线条统一 ≥6px 宽）
 */
const ICONS = [
  {
    // home 房子：三角屋顶（两条 8px 宽斜线）+ 方形屋身（7px 宽描边）
    name: 'home',
    inside: anyOf([
      seg([10, 44], [40.5, 15], 4),
      seg([40.5, 15], [71, 44], 4),
      seg([23, 42], [58, 42], 3.5),
      seg([58, 42], [58, 70], 3.5),
      seg([58, 70], [23, 70], 3.5),
      seg([23, 70], [23, 42], 3.5)
    ])
  },
  {
    // fridge 冰箱：6px 宽圆角矩形描边 + 中横隔线
    name: 'fridge',
    inside: anyOf([
      (x, y) => Math.abs(roundedRectSdf(x, y, 40.5, 40, 17, 31, 8)) <= 3,
      seg([24, 30], [57, 30], 3)
    ])
  },
  {
    // fav 心形：隐式方程 (u²+v²-1)³ − u²·v³ < 0，实心填充（v 轴向上，已翻转）
    name: 'fav',
    inside: (x, y) => {
      const u = (x - 40.5) / 26
      const v = (39 - y) / 26
      const a = u * u + v * v - 1
      return a * a * a - u * u * v * v * v < 0
    }
  },
  {
    // me 人形：圆头（半径 11）+ 下半身半圆（半径 18，上缘平切）
    name: 'me',
    inside: anyOf([
      (x, y) => Math.hypot(x - 40.5, y - 27) <= 11,
      (x, y) => y <= 59 && Math.hypot(x - 40.5, y - 59) <= 18
    ])
  }
]

/**
 * 主流程：输出目录不存在则创建；逐图标生成默认态/选中态 PNG 并校验文件大小 >0。
 * @returns {void} 无返回值；文件系统异常直接抛出由 node 打印堆栈
 */
function main() {
  if (!existsSync(OUT_DIR)) mkdirSync(OUT_DIR, { recursive: true })
  let ok = 0
  for (const icon of ICONS) {
    for (const [suffix, color] of [['', COLOR_IDLE], ['-active', COLOR_ACTIVE]]) {
      const file = join(OUT_DIR, `${icon.name}${suffix}.png`)
      const png = renderIcon(icon.inside, color)
      writeFileSync(file, png)
      const size = statSync(file).size
      if (size <= 0) {
        console.error(`[gen-tab-icons] 生成失败（空文件）：${file}`)
        process.exit(1)
      }
      ok++
      console.log(`  ✔ ${file}（${size} bytes）`)
    }
  }
  console.log(`DONE：共生成 ${ok} 个 tabBar 图标 → ${OUT_DIR}`)
}

main()
