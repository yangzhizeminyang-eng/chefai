/**
 * 文件职责：Vite 环境变量类型声明——为 import.meta.env 补充最小类型面
 * （tsconfig types 仅含 @dcloudio/types / @uni-helper/uni-app-types，未引入 vite/client，
 * 本声明使 import.meta.env.MODE / VITE_API_BASE_URL 在 strict 模式下可用）。
 */

/** Vite 注入的环境变量集合（仅声明工程实际消费的字段） */
interface ImportMetaEnv {
  /** 运行模式：development / production 等（vite build-mode 决定） */
  readonly MODE: string
  /** API 基础地址（生产构建经 .env 注入；缺省由请求层回落占位域名） */
  readonly VITE_API_BASE_URL?: string
}

/** ImportMeta 扩展：挂载 env */
interface ImportMeta {
  /** Vite 环境变量（编译期静态替换） */
  readonly env: ImportMetaEnv
}
