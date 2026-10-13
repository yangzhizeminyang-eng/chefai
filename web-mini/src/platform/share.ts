/**
 * 文件职责：分享平台适配——转发 payload 组装与简易海报绘制。
 * 隐私红线（RL）：分享 / 海报内容仅含菜名、封面等公开信息，
 * 不携带任何健康画像 / 过敏原 / 库存等个人数据。
 * drawSharePoster 为 uni.createCanvasContext 最小实现（底色 + 菜名大字 +
 * 「内容由 AI 生成，仅供参考」固定免责行 + 可选封面），绘制异常静默返回 false。
 */

/** 可分享的菜谱最小信息（调用方从 RecipeDetail 摘取，避免整对象误带隐私字段） */
export interface RecipeShareInfo {
  /** 菜谱 ID（详情页路由参数） */
  id: number | string
  /** 菜名（分享标题） */
  name: string
  /** 封面图 URL（可选；分享卡片与海报复用） */
  cover_url?: string
}

/** 小程序转发 payload（onShareAppMessage 返回值结构） */
export interface SharePayload {
  /** 转发卡片标题（菜名） */
  title: string
  /** 点击卡片进入的页面路径（菜谱详情页 + recipe_id 参数） */
  path: string
  /** 转发卡片封面（可选，缺省用页面截图） */
  imageUrl?: string
}

/**
 * 组装菜谱转发 payload。
 * 隐私红线（RL）：payload 仅含菜名 / 路径 / 封面，不含健康与过敏原信息。
 * @param recipe 菜谱最小信息（id + name + cover_url?）
 * @returns onShareAppMessage 可直接返回的 payload
 * @throws 不抛出
 */
export function buildRecipeSharePayload(recipe: RecipeShareInfo): SharePayload {
  return {
    title: recipe.name,
    path: `/pages/recommend/detail?recipe_id=${recipe.id}`,
    imageUrl: recipe.cover_url,
  }
}

/**
 * 绘制菜谱分享海报（canvas 旧版接口最小实现）。
 * 版面：底色 → 菜名大字（顶部）→ 固定免责行（底部）→ 可选封面图（中部）。
 * 注意：网络封面图在部分平台需先 downloadFile 拿本地路径才可 drawImage；
 * 本实现直接绘制，封面绘制失败随整体异常被吞掉返回 false（调用方降级纯转发）。
 * @param canvasId 画布节点 id（页面 <canvas canvas-id="xxx" /> 需存在且已渲染）
 * @param recipe 菜谱最小信息（name / cover_url?）
 * @param disclaimer 底部免责文案（调用方传 DISCLAIMER_SHARE 等共享常量）
 * @returns 绘制流程完成（draw 回调触发）返回 true；任何异常返回 false（不抛出）
 * @throws 不抛出（画布不存在 / drawImage 失败等一律 resolve(false)）
 */
export function drawSharePoster(canvasId: string, recipe: RecipeShareInfo, disclaimer: string): Promise<boolean> {
  return new Promise<boolean>((resolve) => {
    try {
      const ctx = uni.createCanvasContext(canvasId)
      // 底色（与页面浅色主题一致）
      ctx.setFillStyle('#fffdf9')
      ctx.fillRect(0, 0, 320, 420)
      // 菜名大字
      ctx.setFillStyle('#262626')
      ctx.setFontSize(28)
      ctx.fillText(recipe.name, 24, 96)
      // 可选封面图（中部 272x200）
      if (recipe.cover_url) {
        ctx.drawImage(recipe.cover_url, 24, 130, 272, 200)
      }
      // 固定免责行（AI 生成声明，合规硬要求）
      ctx.setFillStyle('#8c8c8c')
      ctx.setFontSize(12)
      ctx.fillText(disclaimer, 24, 396)
      // draw 回调封装：完成 resolve(true)
      ctx.draw(false, () => resolve(true))
    } catch {
      resolve(false)
    }
  })
}
