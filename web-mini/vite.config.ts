/**
 * 文件级注释：uni-app Vite 构建配置——挂载 uni 插件并注册跨端共享包别名。
 * 说明：本工程无 "type": "module"，Vite 以 CJS 上下文加载本文件，可直接使用 __dirname。
 */
import { defineConfig } from 'vite'
import uni from '@dcloudio/vite-plugin-uni'
import path from 'node:path'

/**
 * 导出 Vite 配置
 * @returns 配好 uni 插件与路径别名的 Vite 配置对象（无异常路径，构建期由 Vite 自行抛错）
 */
export default defineConfig({
  plugins: [uni()],
  resolve: {
    alias: {
      // '@' 指向小程序源码目录
      '@': path.resolve(__dirname, 'src'),
      // '@shared' 指向跨端共享包（packages/shared，由后续任务创建）
      '@shared': path.resolve(__dirname, '../packages/shared/src')
    }
  }
})
