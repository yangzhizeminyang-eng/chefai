<script setup lang="ts">
/**
 * 文件级注释：菜谱封面（业务组件）。
 * 自 web-stage1/src/components/RecipeCover.vue 迁移（语义保持，DOM img → uni image）：
 * - 有 coverUrl → 真实图（mode aspectFill 裁切不变形 + lazy-load 懒加载 + 占位背景色），
 *   加载中显示骨架灰块占满容器（高度稳定防跳动），加载失败回落程序化占位封面，绝不裂图；
 * - 无图或失败 → 占位回落块：按 paletteSeed（缺省用菜名）稳定映射 coverPalette 8 色
 *   暖色板，中央渲染菜名首字大字，右下角固定「示意图」角标（沿用阶段一不可关闭语义）；
 * - size 三档：sm 列表缩略方图 / md 卡片 16:9 / lg 详情大图。
 * 使用约束：由页面根 .page/.dark 提供主题变量上下文；色板色来自 @shared/utils/cover
 * 纯函数（JS 变量绑定，非样式表硬编码）。
 */
import { computed, ref, watch } from 'vue'
import { coverPalette } from '@shared/utils/cover'
import { API_BASE_URL } from '@/api/request'

/** 封面尺寸档位（决定容器高度与圆角） */
export type RecipeCoverSize = 'sm' | 'md' | 'lg'

/** 组件入参 */
const props = withDefaults(
  defineProps<{
    /** 菜名（占位回落块首字来源，同菜谱恒定同色兜底 seed） */
    name: string
    /** 封面图 URL（可选；空/加载失败均走占位回落块） */
    coverUrl?: string
    /** 色板映射 seed（可选；一般传菜谱 ID 字符串，缺省用菜名，同 seed 恒定同色） */
    paletteSeed?: string
    /** 尺寸档位：sm 缩略方图 / md 卡片横图 / lg 详情大图 */
    size?: RecipeCoverSize
  }>(),
  { coverUrl: '', paletteSeed: '', size: 'md' },
)

/** 图片是否加载失败（true → 回落占位封面，绝不裂图） */
const loadError = ref(false)

/** 图片是否已加载完成（控制骨架显隐） */
const loaded = ref(false)

/**
 * 封面地址解析：后端返回相对路径（/v1/media/recipe-covers/xxx.jpg），小程序 image
 * 组件会把 "/..." 当本地包内资源加载（Failed to load local image resource），必须
 * 拼接 API_BASE_URL 转为绝对地址；已是 http(s) 绝对地址的（如 CDN）原样返回。
 * 🔴 历史缺陷：相对路径未拼基址导致封面全部加载失败（勿回退）。
 */
const resolvedCover = computed(() => {
  const url = props.coverUrl
  if (!url) return ''
  if (/^https?:\/\//i.test(url)) return url
  return API_BASE_URL + url
})

// coverUrl 变化（组件复用 / 详情切换菜谱）时重置加载状态，避免残留旧图状态
watch(
  () => props.coverUrl,
  () => {
    loadError.value = false
    loaded.value = false
  },
)

/** 是否展示占位回落块（无 URL 或加载出错） */
const showPlaceholder = computed(() => !props.coverUrl || loadError.value)

/**
 * seed 字符串 → 稳定正整数（字符码累加哈希）。
 * 与 coverPalette(number) 签名对齐：同 seed 恒定同色，不同 seed 尽量分散到 8 色。
 * @param seed 任意字符串（空串返回 0）
 * @returns 非负整数哈希
 */
function seedToNumber(seed: string): number {
  let hash = 0
  for (let i = 0; i < seed.length; i++) {
    hash = (hash * 31 + seed.charCodeAt(i)) >>> 0
  }
  return hash
}

/** 占位色板（bg 浅底 / fg 深色文字，成对保证对比度可读；seed 缺省回落菜名） */
const palette = computed(() => coverPalette(seedToNumber(props.paletteSeed || props.name)))

/** 占位块首字（菜名首字；空名兜底「菜」） */
const firstChar = computed(() => props.name.charAt(0) || '菜')

/** 尺寸修饰类 */
const sizeClass = computed(() => `is-${props.size}`)
</script>

<template>
  <view class="recipe-cover" :class="sizeClass">
    <!-- 占位回落块：色板底色 + 菜名首字大字 + 右下角「示意图」角标 -->
    <view
      v-if="showPlaceholder"
      class="cover-placeholder"
      :style="{ background: palette.bg, color: palette.fg }"
    >
      <text class="placeholder-char">{{ firstChar }}</text>
      <text class="placeholder-badge">示意图</text>
    </view>
    <!-- 真实图分支：加载中骨架占满容器（渐入期间不留白、高度不跳动） -->
    <template v-else>
      <view v-if="!loaded" class="cover-skeleton" />
      <image
        class="cover-img"
        :src="resolvedCover"
        mode="aspectFill"
        lazy-load
        @load="loaded = true"
        @error="loadError = true"
      />
    </template>
  </view>
</template>

<style scoped lang="scss">
.recipe-cover {
  position: relative;
  box-sizing: border-box;
  width: 100%;
  height: 320rpx;
  overflow: hidden;
  border-radius: var(--radius-ctrl);
  background: var(--color-info-bg);

  /* sm：列表缩略方图 */
  &.is-sm {
    width: 160rpx;
    height: 160rpx;
    flex-shrink: 0;
  }

  /* lg：详情页大图 */
  &.is-lg {
    height: 420rpx;
    border-radius: var(--radius-card);
  }
}

/* 占位回落块：色板底 + 居中首字大字 */
.cover-placeholder {
  position: absolute;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  display: flex;
  align-items: center;
  justify-content: center;
}

.placeholder-char {
  font-size: 96rpx;
  font-weight: 600;
  line-height: 1;
}

/* 右下角「示意图」角标：半透明遮罩底（深浅色通用），不可关闭 */
.placeholder-badge {
  position: absolute;
  right: var(--space-xs);
  bottom: var(--space-xs);
  padding: 4rpx var(--space-sm);
  border-radius: var(--radius-ctrl);
  background: rgba(0, 0, 0, 0.45);
  color: var(--text-inverse);
  font-size: var(--font-size-sm);
  line-height: 1.5;
}

/* 加载中骨架：占满容器的灰块扫动动画（全部变量色，深色自动适配） */
.cover-skeleton {
  position: absolute;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background: linear-gradient(90deg, var(--bg-page) 25%, var(--divider) 37%, var(--bg-page) 63%);
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

/* 真实图：裁切填充不变形 */
.cover-img {
  display: block;
  width: 100%;
  height: 100%;
}
</style>
