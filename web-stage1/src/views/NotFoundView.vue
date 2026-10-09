<script setup lang="ts">
/**
 * 文件职责：404 未找到页面（N2/L2 修复，catchAll 路由 /:pathMatch(.*)* 的兜底视图）。
 * - 未知路由不再主体空白，本页给出明确 404 文案与「返回首页」行动入口；
 * - 风格对齐项目既有视图（BlockedView 的 page-card 布局 + 大标识区），
 *   底部复用 DisclaimerBar 常驻免责条（G-02）；
 * - 深色模式兼容：全部使用项目 CSS 变量（--color-info-* / --text-main 等），
 *   不硬编码色值，随 html.dark 自适应。
 */
import { useRouter } from 'vue-router'

/** 路由实例：「返回首页」按钮跳转 */
const router = useRouter()

/**
 * 返回首页（catchAll 兜底页唯一的行动入口）。
 * @returns 无
 */
function goHome(): void {
  void router.push('/')
}
</script>

<template>
  <section class="page-card notfound-page">
    <!-- 顶部大标识：图标 + 标题 + 副标题（视觉结构对齐 BlockedView 的 block-banner） -->
    <div class="notfound-banner">
      <span class="banner-icon" aria-hidden="true">🥄</span>
      <div class="banner-text">
        <h1 class="banner-title">404 · 页面不存在</h1>
        <p class="banner-subtitle">你访问的页面不存在或已被移除，请检查地址是否正确。</p>
      </div>
    </div>

    <!-- 行动入口：返回首页 -->
    <div class="footer-row">
      <el-button type="primary" @click="goHome">返回首页</el-button>
    </div>

    <!-- 常驻免责条（G-02，与既有视图一致） -->
    <DisclaimerBar variant="default" />
  </section>
</template>

<style scoped>
/* ── 顶部大标识（信息语义蓝色系，非危险/警示场景） ── */
.notfound-banner {
  display: flex;
  align-items: flex-start;
  gap: 14px;
  padding: 26px 20px;
  border: 1px solid var(--color-info-border);
  border-radius: 10px;
  background: var(--color-info-bg);
}

.banner-icon {
  font-size: 40px;
  line-height: 1.2;
}

.banner-title {
  margin: 0 0 6px;
  font-size: 22px;
  font-weight: 700;
  color: var(--color-info);
}

.banner-subtitle {
  margin: 0;
  font-size: var(--font-md);
  color: var(--text-main);
}

/* ── 底部行动区 ── */
.footer-row {
  display: flex;
  justify-content: flex-start;
  margin: 20px 0 12px;
}
</style>
