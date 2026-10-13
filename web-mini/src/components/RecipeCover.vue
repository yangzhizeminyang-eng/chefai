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
  if (/^(https?:\/\/|data:)/i.test(url)) return url
  return API_BASE_URL + url
})

/**
 * 远程封面 → data URL 缓存（模块级 Map：绝对 url → data:image/...;base64,...）。
 * 🔴 真机适配（最终方案）：Android/iOS 微信真机的 <image> 组件对 HTTP 明文图片受限、
 * downloadFile 通道真机同样被拦（实测），而 **request 通道真机已验证可连本地后端**——
 * 因此网络封面统一经 uni.request（responseType: 'arraybuffer'）拉取二进制，
 * 转 base64 data URL 渲染（data: 协议不受任何真机网络拦截）。
 * 上线 HTTPS 域名后本逻辑同样工作（request 对 HTTPS 照常可用）。
 * 内存评估：单封面 base64 约 300KB，列表页同屏 ≤8 张约 2.4MB，可接受；
 * 缓存 Map 避免滚动/复用重复拉取。
 */
const dataUrlCache = new Map<string, string>()

/** 实际渲染给 <image> 的 src（data URL；就绪前为空串显示骨架） */
const displaySrc = ref('')

/**
 * 从 URL 扩展名推断 MIME（base64 data URL 前缀用；未知扩展按 JPEG）。
 * @param url 封面绝对地址
 * @returns image MIME 字符串
 */
function coverMime(url: string): string {
  const lower = url.toLowerCase()
  if (lower.endsWith('.png')) return 'image/png'
  if (lower.endsWith('.webp')) return 'image/webp'
  if (lower.endsWith('.gif')) return 'image/gif'
  return 'image/jpeg'
}

/**
 * 经 request 通道拉取封面二进制并转 base64 data URL。
 * @param url 封面绝对地址
 * @returns data URL（data:image/...;base64,...）
 * @throws statusCode ≠ 200 或网络失败时抛出（由调用方静默处理走占位回落）
 */
function fetchCoverAsDataUrl(url: string): Promise<string> {
  return new Promise((resolve, reject) => {
    uni.request({
      url,
      method: 'GET',
      responseType: 'arraybuffer',
      timeout: 15000,
      success: (res) => {
        if (res.statusCode !== 200) {
          reject(new Error(`cover fetch status ${res.statusCode}`))
          return
        }
        const base64 = uni.arrayBufferToBase64(res.data as ArrayBuffer)
        resolve(`data:${coverMime(url)};base64,${base64}`)
      },
      fail: (err) => {
        reject(new Error(err.errMsg || 'request fail'))
      },
    })
  })
}

/**
 * 加载封面到可渲染状态：缓存命中直接用；未命中经 request 通道拉取转 data URL 后写缓存。
 * @param url 解析后的封面绝对地址（可空）
 * @returns 无
 * @throws 不抛出（拉取失败置 loadError 走占位回落，绝不裂图）
 */
async function loadDisplaySrc(url: string): Promise<void> {
  if (!url) {
    displaySrc.value = ''
    return
  }
  // data URL / 本地路径：直接渲染（缓存命中 / 未来 base64 场景）
  if (!/^https?:\/\//i.test(url)) {
    displaySrc.value = url
    return
  }
  const cached = dataUrlCache.get(url)
  if (cached) {
    displaySrc.value = cached
    return
  }
  try {
    const dataUrl = await fetchCoverAsDataUrl(url)
    dataUrlCache.set(url, dataUrl)
    // 异步期间组件可能已切换封面：仅当仍是当前封面时才落地，防旧图串场
    if (resolvedCover.value === url) {
      displaySrc.value = dataUrl
    }
  } catch {
    if (resolvedCover.value === url) {
      loadError.value = true
    }
  }
}

// coverUrl 变化（组件复用 / 详情切换菜谱）：重置状态并按解析结果加载封面
watch(
  () => props.coverUrl,
  () => {
    loadError.value = false
    loaded.value = false
    displaySrc.value = ''
    void loadDisplaySrc(resolvedCover.value)
  },
  { immediate: true },
)

/** 是否展示占位回落块（无可显示图或加载出错） */
const showPlaceholder = computed(() => !displaySrc.value || loadError.value)

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
        :src="displaySrc"
        mode="aspectFill"
        webp
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
