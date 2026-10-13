/**
 * 文件级注释：浏览器 API 静态检查脚本——扫描 web-mini/src 下 .ts/.vue 文件，
 * 禁止直调 localStorage/sessionStorage/window./document./navigator.，
 * 白名单：src/utils/storage.ts（受控封装）与 src/platform/（平台适配层）。
 * 用法：node scripts/check-browser-api.mjs（在 web-mini 目录执行，或 npm run check:api）。
 * 退出码：命中违规 exit(1)；否则打印 PASS exit(0)。
 */
import { readdirSync, readFileSync, statSync } from 'node:fs'
import { join, relative, resolve, dirname } from 'node:path'
import { fileURLToPath } from 'node:url'

/** 本脚本所在目录（用于定位 web-mini/src） */
const SCRIPT_DIR = dirname(fileURLToPath(import.meta.url))

/** 扫描目标源码目录：web-mini/src */
const SRC_DIR = resolve(SCRIPT_DIR, '../src')

/**
 * 浏览器 API 违规正则：匹配 localStorage / sessionStorage 直调，
 * 以及 window. / document. / navigator. 属性访问。
 */
const BROWSER_API_RE = /(localStorage|sessionStorage|window\.|document\.|navigator\.)/

/**
 * 白名单判定：受控存储封装与平台适配层允许出现浏览器 API
 * @param {string} normPath 以 '/' 分隔的相对路径（相对 web-mini 根）
 * @returns {boolean} 是否在白名单内
 */
function isAllowed(normPath) {
  return normPath.includes('src/utils/storage.ts') || normPath.includes('src/platform/')
}

/**
 * 递归收集目录下的 .ts/.vue 文件
 * @param {string} dir 待遍历目录绝对路径
 * @param {string[]} acc 收集结果（绝对路径数组，调用方传入空数组）
 * @returns {string[]} 收集到的文件绝对路径列表（目录不存在时抛出 Node 文件系统异常）
 */
function collectFiles(dir, acc) {
  for (const name of readdirSync(dir)) {
    const full = join(dir, name)
    const st = statSync(full)
    if (st.isDirectory()) {
      collectFiles(full, acc)
    } else if (name.endsWith('.ts') || name.endsWith('.vue')) {
      acc.push(full)
    }
  }
  return acc
}

/**
 * 主流程：扫描全部文件逐行匹配违规正则，命中则输出 文件:行号:内容 并 exit(1)，
 * 全部通过则打印 PASS。
 * @returns {void} 无返回值；通过 process.exitCode / process.exit 控制退出码
 */
function main() {
  let files
  try {
    files = collectFiles(SRC_DIR, [])
  } catch (err) {
    console.error(`[check-browser-api] 无法读取源码目录 ${SRC_DIR}：${err.message}`)
    process.exit(1)
  }

  const violations = []
  for (const file of files) {
    const rel = relative(resolve(SCRIPT_DIR, '..'), file).replace(/\\/g, '/')
    if (isAllowed(rel)) continue
    const lines = readFileSync(file, 'utf8').split(/\r?\n/)
    lines.forEach((line, i) => {
      if (BROWSER_API_RE.test(line)) {
        violations.push(`${rel}:${i + 1}:${line.trim()}`)
      }
    })
  }

  if (violations.length > 0) {
    console.error(`[check-browser-api] 发现 ${violations.length} 处浏览器 API 直调（小程序禁止）：`)
    for (const v of violations) console.error('  ' + v)
    process.exit(1)
  }
  console.log(`PASS（扫描 ${files.length} 个 .ts/.vue 文件，无浏览器 API 直调）`)
}

main()
