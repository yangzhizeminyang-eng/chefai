<script setup lang="ts">
/**
 * 组件职责：菜谱封面（推荐卡片 / 详情页共用的 16:9 图片区）。
 * - 有 src（cover_image_url，/v1/media 相对路径）→ 懒加载真实图（object-fit: cover 不变形），
 *   加载中显示骨架灰块占满容器（高度稳定不跳动，防 CLS）；
 *   @error 置 loadError 回落占位封面，绝不出现裂图；@load 隐藏骨架；
 * - 无 src 或加载失败 → 程序化占位封面：按 recipeId 稳定映射 8 色暖色板（utils/cover），
 *   中央 🍳 图标 + 菜名文字（最多 2 行，溢出省略），右下角固定「示意图」角标（不可关闭）；
 * - 可访问性：img alt = 菜名；占位态容器 role="img" 且 aria-label 含「菜名 示意图」，
 *   占位语义由文字与角标承载，不依赖颜色单独传达信息。
 */
import { computed, ref, watch } from 'vue'
import { coverPalette } from '@/utils/cover'

/** 组件入参 */
const props = defineProps<{
  /** 封面图 URL（/v1/media 相对路径；null/undefined 表示无真实图，直接走占位封面） */
  src?: string | null
  /** 菜名（img 的 alt 与占位封面文字） */
  title: string
  /** 菜谱 ID（占位封面色板稳定映射键，同 id 恒定同色） */
  recipeId: number
}>()

/** 图片是否加载失败（true → 回落占位封面，绝不裂图） */
const loadError = ref(false)
/** 图片是否已加载完成（控制骨架显隐） */
const loaded = ref(false)

// src 变化（组件复用 / 详情切换菜谱）时重置加载状态，避免残留旧图状态
watch(
  () => props.src,
  () => {
    loadError.value = false
    loaded.value = false
  },
)

/** 是否展示占位封面（无 src 或加载出错） */
const showPlaceholder = computed(() => !props.src || loadError.value)

/** 占位封面色板（bg 背景 / fg 深色文字，成对保证对比度可读） */
const palette = computed(() => coverPalette(props.recipeId))

/** 占位态容器无障碍标签（role="img" 的 aria-label：「菜名 示意图」） */
const placeholderLabel = computed(() => `${props.title} 示意图`)
</script>

<template>
  <div class="recipe-cover">
    <!-- 占位封面：色板背景 + 🍳 + 菜名（最多 2 行省略）+ 右下角固定「示意图」角标 -->
    <div
      v-if="showPlaceholder"
      class="cover-placeholder"
      role="img"
      :aria-label="placeholderLabel"
      :style="{ background: palette.bg, color: palette.fg }"
    >
      <span class="placeholder-icon" aria-hidden="true">🍳</span>
      <span class="placeholder-title">{{ title }}</span>
      <span class="placeholder-badge">示意图</span>
    </div>
    <!-- 真实图分支：加载中骨架占满容器（图片渐入期间不留白、高度不跳动） -->
    <template v-else>
      <div v-if="!loaded" class="cover-skeleton" aria-hidden="true"></div>
      <!-- @error 置 loadError 回落占位封面，绝不出现裂图 -->
      <img
        class="cover-img"
        :src="src ?? undefined"
        :alt="title"
        loading="lazy"
        @load="loaded = true"
        @error="loadError = true"
      />
    </template>
  </div>
</template>

<style scoped>
/* 容器固定 16:9，高度由宽度决定，布局稳定不跳动（防 CLS） */
.recipe-cover {
  position: relative;
  width: 100%;
  aspect-ratio: 16 / 9;
  overflow: hidden;
  border-radius: 8px;
  background: var(--color-info-bg);
}

/* 真实图：裁切填充不变形 */
.cover-img {
  display: block;
  width: 100%;
  height: 100%;
  object-fit: cover;
}

/* 加载中骨架：占满容器的灰块扫动动画（Element Plus 同款视觉语言） */
.cover-skeleton {
  position: absolute;
  inset: 0;
  background: linear-gradient(90deg, #efefef 25%, #f7f7f7 37%, #efefef 63%);
  background-size: 400% 100%;
  animation: cover-skeleton-loading 1.4s ease infinite;
}

@keyframes cover-skeleton-loading {
  0% {
    background-position: 100% 50%;
  }

  100% {
    background-position: 0 50%;
  }
}

/* 占位封面：色板底色 + 居中图标与菜名 */
.cover-placeholder {
  position: absolute;
  inset: 0;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 6px;
  padding: 12px;
  text-align: center;
}

.placeholder-icon {
  font-size: 28px;
  line-height: 1;
}

/* 菜名最多 2 行，溢出省略 */
.placeholder-title {
  display: -webkit-box;
  overflow: hidden;
  -webkit-box-orient: vertical;
  -webkit-line-clamp: 2;
  font-size: var(--font-md);
  font-weight: 600;
  line-height: 1.4;
  word-break: break-all;
}

/* 右下角固定「示意图」角标：半透明黑底白字，不可关闭 */
.placeholder-badge {
  position: absolute;
  right: 8px;
  bottom: 8px;
  padding: 2px 8px;
  border-radius: 4px;
  background: rgba(0, 0, 0, 0.45);
  color: #fff;
  font-size: 12px;
  line-height: 1.5;
}
</style>
