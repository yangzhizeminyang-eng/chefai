/**
 * 文件级注释：分包体积审计脚本——统计 web-mini/dist/build/mp-weixin 的
 * 主包与 5 个分包体积，对照微信小程序体积预算（主包 ≤1.6MB / 单分包 ≤1.5MB）。
 * 用法：先执行 npm run build:mp-weixin，再执行 npm run audit:size。
 * 退出码：超限或 dist 不存在 exit(1)；全部达标打印各包体积 PASS exit(0)。
 */
import { readdirSync, readFileSync, statSync } from 'node:fs'
import { join, relative, resolve, dirname } from 'node:path'
import { fileURLToPath } from 'node:url'

/** 本脚本所在目录（用于定位 web-mini/dist） */
const SCRIPT_DIR = dirname(fileURLToPath(import.meta.url))

/** 微信构建产物根目录 */
const DIST_ROOT = resolve(SCRIPT_DIR, '../dist/build/mp-weixin')

/** 分包目录名清单（相对 dist 根的 pages/ 子目录） */
const SUBPKGS = ['recommend', 'cooking', 'nutrition', 'member', 'innovation']

/** 主包体积上限：1.6MB */
const MAIN_LIMIT = 1.6 * 1024 * 1024

/** 单分包体积上限：1.5MB */
const SUB_LIMIT = 1.5 * 1024 * 1024

/**
 * 递归收集目录下全部文件
 * @param {string} dir 待遍历目录绝对路径
 * @param {string[]} acc 收集结果（绝对路径数组，调用方传入空数组）
 * @returns {string[]} 文件绝对路径列表
 */
function collectFiles(dir, acc) {
  for (const name of readdirSync(dir)) {
    const full = join(dir, name)
    const st = statSync(full)
    if (st.isDirectory()) collectFiles(full, acc)
    else acc.push(full)
  }
  return acc
}

/**
 * 计算文件列表总体积
 * @param {string[]} files 文件绝对路径列表
 * @returns {number} 总字节数（读取失败按 0 计，极小概率竞态不影响审计结论）
 */
function totalSize(files) {
  return files.reduce((sum, f) => {
    try {
      return sum + statSync(f).size
    } catch {
      return sum
    }
  }, 0)
}

/**
 * 格式化字节数为可读文本
 * @param {number} bytes 字节数
 * @returns {string} 形如 "1.23MB"/"456KB" 的格式化结果
 */
function fmt(bytes) {
  return bytes >= 1024 * 1024
    ? `${(bytes / 1024 / 1024).toFixed(2)}MB`
    : `${(bytes / 1024).toFixed(0)}KB`
}

/**
 * 主流程：主包 = dist 根下不属于任何分包目录的文件；各分包 = 对应目录。
 * 超限时列出明细（最大前 20 个文件）并 exit(1)，否则打印各包体积 PASS。
 * @returns {void} 无返回值；通过 process.exit 控制退出码
 */
function main() {
  let all
  try {
    all = collectFiles(DIST_ROOT, [])
  } catch {
    console.error(`[size-audit] 未找到构建产物 ${DIST_ROOT}，请先执行 npm run build:mp-weixin`)
    process.exit(1)
  }

  const subPrefixes = SUBPKGS.map((s) => join(DIST_ROOT, 'pages', s))
  const isSubFile = (f) => subPrefixes.some((p) => f.startsWith(p))

  const mainFiles = all.filter((f) => !isSubFile(f))
  const mainSize = totalSize(mainFiles)
  const results = [{ name: '主包', size: mainSize, limit: MAIN_LIMIT, files: mainFiles }]

  for (const sub of SUBPKGS) {
    const files = all.filter((f) => f.startsWith(join(DIST_ROOT, 'pages', sub)))
    results.push({ name: `分包 pages/${sub}`, size: totalSize(files), limit: SUB_LIMIT, files })
  }

  let failed = false
  console.log('[size-audit] 各包体积：')
  for (const r of results) {
    const status = r.size > r.limit ? '❌ 超限' : '✅'
    console.log(`  ${r.name.padEnd(22)} ${fmt(r.size).padStart(8)} / 上限 ${fmt(r.limit)}  ${status}`)
    if (r.size > r.limit) {
      failed = true
      console.log(`  超限明细（最大前 20 个文件）：`)
      const top = [...r.files]
        .sort((a, b) => statSync(b).size - statSync(a).size)
        .slice(0, 20)
      for (const f of top) {
        console.log(`    ${fmt(statSync(f).size).padStart(8)}  ${relative(DIST_ROOT, f).replace(/\\/g, '/')}`)
      }
    }
  }

  if (failed) process.exit(1)
  console.log('PASS（主包与全部分包均在体积预算内）')
}

main()
