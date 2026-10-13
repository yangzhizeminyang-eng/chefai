<script setup lang="ts">
/**
 * 文件级注释：权限引导卡（五态-无权限态，安全组件，主包内置）。
 * 相机/相册/麦克风被拒后的引导语义（阶段一拍照识别/语音点菜的权限分支）：
 * - 按 scope 展示权限用途说明（中文友好，不暴露技术细节）；
 * - 「去设置」按钮：组件内直接调 uni.openSetting（热区 ≥88rpx），打开前 emit openSetting
 *   通知页面，授权结果回包后 emit result 携带 authSetting（页面据此重试业务）；
 * - 底部保底入口 slot name="fallback"（如「手选食材」，未授权也能走通的兜底路径）。
 * 使用约束：由页面根 .page/.dark 提供主题变量上下文。
 */
import { computed } from 'vue'

/** 权限域（决定用途说明文案） */
export type PermissionScope = 'camera' | 'album' | 'microphone'

/** 组件入参 */
const props = withDefaults(
  defineProps<{
    /** 权限域：camera 相机 / album 相册 / microphone 麦克风 */
    scope: PermissionScope
    /** 页面定制说明文案（可选；覆盖 scope 缺省说明） */
    fallbackText?: string
  }>(),
  { fallbackText: '' },
)

/** 打开系统设置事件（点击「去设置」时先于 openSetting 调用触发，页面可埋点） */
const emit = defineEmits<{
  (e: 'openSetting'): void
  (e: 'result', authSetting: Record<string, boolean>): void
}>()

/** scope → 缺省用途说明（中文友好） */
const SCOPE_TEXT: Record<PermissionScope, string> = {
  camera: '需要使用相机拍摄食材照片，用于识别食材并推荐菜谱',
  album: '需要访问相册选取食材照片，用于识别食材并推荐菜谱',
  microphone: '需要使用麦克风进行语音点菜，用于识别你的语音指令',
}

/** 实际说明文案：fallbackText 优先，按 scope 取缺省 */
const guideText = computed(() => (props.fallbackText ? props.fallbackText : SCOPE_TEXT[props.scope]))

/** scope → 缺省图标字符 */
const SCOPE_ICON: Record<PermissionScope, string> = {
  camera: '📷',
  album: '🖼️',
  microphone: '🎤',
}

/** 图标字符 */
const scopeIcon = computed(() => SCOPE_ICON[props.scope])

/**
 * 点击「去设置」：先 emit openSetting，再直接调 uni.openSetting 打开授权设置页；
 * 成功回包后 emit result 携带授权结果（authSetting），页面据此决定是否重试业务。
 * @returns 无
 * @throws 不向外抛出（openSetting 失败静默：用户未发生授权变化，页面保持引导态）
 */
function onOpenSetting(): void {
  emit('openSetting')
  uni.openSetting({
    /** 设置页返回：把授权结果回传页面 */
    success: (res) => {
      const auth = (res as { authSetting?: Record<string, boolean> }).authSetting ?? {}
      emit('result', auth)
    },
    /** 失败静默：不抛出，页面保持引导态 */
    fail: () => {},
  })
}
</script>

<template>
  <view class="permission-guide">
    <!-- 图标：scope 对应 emoji（形状表达，不依赖颜色） -->
    <text class="permission-guide__icon">{{ scopeIcon }}</text>
    <text class="permission-guide__title">需要你的授权</text>
    <text class="permission-guide__desc">{{ guideText }}</text>
    <!-- 去设置按钮：热区 ≥88rpx，组件内直接调 uni.openSetting -->
    <view class="permission-guide__btn" @click="onOpenSetting">去设置</view>

    <!-- 保底入口插槽：如「手选食材」等未授权也能走通的兜底路径 -->
    <view class="permission-guide__fallback">
      <slot name="fallback" />
    </view>
  </view>
</template>

<style scoped lang="scss">
.permission-guide {
  box-sizing: border-box;
  display: flex;
  flex-direction: column;
  align-items: center;
  padding: var(--space-xl) var(--space-md);
}

.permission-guide__icon {
  font-size: 96rpx;
  line-height: 1.2;
}

.permission-guide__title {
  margin-top: var(--space-md);
  font-size: var(--font-size-base);
  font-weight: 600;
  color: var(--text-primary);
}

.permission-guide__desc {
  margin-top: var(--space-xs);
  font-size: var(--font-size-sm);
  line-height: 1.6;
  color: var(--text-tertiary);
  text-align: center;
  word-break: break-all;
}

/* 去设置按钮：主色实底，热区 ≥88rpx */
.permission-guide__btn {
  margin-top: var(--space-lg);
  box-sizing: border-box;
  min-width: 240rpx;
  min-height: var(--hit-min);
  padding: 0 var(--space-lg);
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: var(--radius-pill);
  background: var(--color-primary);
  color: var(--text-inverse);
  font-size: var(--font-size-sm);
}

.permission-guide__fallback {
  margin-top: var(--space-md);
  display: flex;
  justify-content: center;
  width: 100%;
}
</style>
