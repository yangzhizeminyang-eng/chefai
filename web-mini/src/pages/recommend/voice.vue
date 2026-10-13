<!--
  文件级注释：P-09 语音点菜页（pages/recommend/voice，阶段二新页面）。
  阶段一无独立语音页，本页为小程序新增增强入口（增强功能，手动路径始终可用）：
  - 大按钮「按住说话」：uni.getRecorderManager() 录音（touchstart start / touchend stop，
    热区整卡 ≥88rpx）；录音计时展示；
  - 🔴 ASR 占位：录音完成后不做识别上传——语音识别服务暂不可用
    （微信同声传译插件待申请，注释与本页文案如实说明），录音结果仅本地提示；
  - 手动输入兜底（始终可用）：BaseInput textarea（placeholder「或直接输入食材/菜名」）
    +「去搜索」（携 q 跳 RECOMMEND_SEARCH + '?q='）+「去手选」（→ RECOMMEND_SELECT）；
  - 麦克风权限拒绝（recorder onError errMsg 含 auth/deny）→ PermissionGuide
    （scope microphone）+ fallback 手动输入区（保底不阻断）；
  - 五态：空闲 / 录音中 / 已录音（待 ASR）/ 无权限（PermissionGuide）/ 离线（OfflineBar）。
-->
<script setup lang="ts">
import { computed, onBeforeUnmount, ref } from 'vue'
import { onHide, onUnload } from '@dcloudio/uni-app'
import { ROUTES, goRoute } from '@/utils/routes'
import { flushOnHide } from '@/utils/track'
import { toastWarning } from '@/utils/toast'
import { useAppNetwork } from '@/platform/network'
import { useTheme } from '@/platform/theme'
import { useFontSize } from '@/platform/fontSize'
import PermissionGuide from '@/components/PermissionGuide.vue'
import OfflineBar from '@/components/OfflineBar.vue'
import DisclaimerBar from '@/components/DisclaimerBar.vue'
import BaseButton from '@/components-base/BaseButton.vue'
import BaseInput from '@/components-base/BaseInput.vue'

/* 🔴 ASR 占位说明：
   录音完成后本端不做任何语音识别上传——语音识别服务暂不可用（微信同声传译插件
   待申请）。recorderManager 产物仅停留本地（stop 后丢弃），用户经手动输入框走
   搜索/手选链路。插件接入后在此接管 onStop 产物调用识别 API，交互结构不变。 */

/** 深色模式标记（根节点 class） */
const { isDark } = useTheme()
/** 字号档位 class（根节点 class） */
const { fontSizeClass } = useFontSize()
/** 全局网络态（离线提示条显隐） */
const network = useAppNetwork()

/** 页面阶段：idle 空闲 / recording 录音中 / recorded 已录音 / denied 无权限 */
const stage = ref<'idle' | 'recording' | 'recorded' | 'denied'>('idle')
/** 录音计时（秒，录音中每秒累加） */
const recordSeconds = ref(0)
/** 计时器句柄（录音中循环累加；stop/clear 时清理） */
let timerId: ReturnType<typeof setInterval> | null = null
/** 手动输入内容（textarea） */
const manualText = ref('')

/** 录音管理器（页面级单例；uni 全局同一实例） */
const recorder = uni.getRecorderManager()

/** 录音按钮展示文案（按阶段切换） */
const micLabel = computed(() => {
  if (stage.value === 'recording') return `松开结束（${recordSeconds.value}s）`
  if (stage.value === 'recorded') return '已录音 · 语音识别暂不可用'
  return '按住说话'
})

/**
 * 开始录音（touchstart 触发）：权限/占用错误经 onError 捕获转无权限态。
 * @returns 无
 */
function startRecord(): void {
  if (stage.value === 'recording') return
  stage.value = 'recording'
  recordSeconds.value = 0
  // 计时：录音中每秒累加（纯 UI 展示，超 60s 自动 stop 防超长录音）
  timerId = setInterval(() => {
    recordSeconds.value += 1
    if (recordSeconds.value >= 60) stopRecord()
  }, 1000)
  try {
    recorder.start({ duration: 60000 })
  } catch {
    // 平台不支持录音等同步异常：回空闲态（手动输入始终可用）
    stage.value = 'idle'
    clearTimer()
  }
}

/**
 * 结束录音（touchend 触发）：onStop 回调标记「已录音」态（ASR 占位，不做识别）。
 * @returns 无
 */
function stopRecord(): void {
  if (stage.value !== 'recording') return
  clearTimer()
  try {
    recorder.stop()
  } catch {
    // 同步异常静默：走 onError/onStop 兜底
  }
}

/**
 * 清理计时器（stop / 卸载时调用，防泄漏）。
 * @returns 无
 */
function clearTimer(): void {
  if (timerId != null) {
    clearInterval(timerId)
    timerId = null
  }
}

// 录音自然结束/主动停止回调：进入「已录音」态（🔴 ASR 占位：不识别不上传，仅提示）
recorder.onStop(() => {
  clearTimer()
  if (stage.value === 'recording') stage.value = 'recorded'
})

// 录音错误回调：权限拒绝（errMsg 含 auth/authorize/deny）转无权限态；其余回空闲态
recorder.onError((err) => {
  clearTimer()
  const msg = (err as { errMsg?: string } | null)?.errMsg ?? ''
  if (msg.includes('auth') || msg.includes('authorize') || msg.includes('deny')) {
    stage.value = 'denied'
    return
  }
  stage.value = 'idle'
  toastWarning('录音不可用，请直接输入文字')
})

/**
 * 「去搜索」：携 q 跳搜索/提问页（手动输入为语音增强功能的常驻兜底）。
 * @returns 无
 */
function goSearch(): void {
  const q = manualText.value.trim()
  if (!q) {
    toastWarning('请先输入食材或菜名')
    return
  }
  goRoute(`${ROUTES.RECOMMEND_SEARCH}?q=${encodeURIComponent(q)}`)
}

/**
 * 「去手选」：跳食材选择页。
 * @returns 无
 */
function goSelect(): void {
  goRoute(ROUTES.RECOMMEND_SELECT)
}

/**
 * 无权限态「去设置」回包：授权开启麦克风后回空闲态（可重新按住说话）。
 * @param authSetting 授权结果（PermissionGuide emit result）
 * @returns 无
 */
function onAuthResult(authSetting: Record<string, boolean>): void {
  const granted = Object.values(authSetting).some((v) => v === true)
  if (granted) stage.value = 'idle'
}

// onHide：尽力上报缓冲埋点
onHide(() => {
  flushOnHide()
})

// 卸载：清理计时器，防止页面栈销毁后定时器泄漏
onUnload(() => {
  clearTimer()
})

// 组件卸载兜底（非页面栈卸载场景）
onBeforeUnmount(() => {
  clearTimer()
})
</script>

<template>
  <view class="page" :class="[isDark ? 'dark' : '', fontSizeClass]">
    <!-- 离线提示条 -->
    <OfflineBar v-if="!network.isConnected" />

    <view class="voice">
      <!-- 无权限态：PermissionGuide + fallback 手动输入（保底不阻断） -->
      <template v-if="stage === 'denied'">
        <PermissionGuide scope="microphone" @result="onAuthResult">
          <template #fallback>
            <!-- 手动输入兜底区（与空闲态共用结构） -->
            <view class="voice__manual">
              <text class="voice__manual-title">直接输入</text>
              <BaseInput
                v-model="manualText"
                type="textarea"
                placeholder="或直接输入食材/菜名"
                :maxlength="-1"
              />
              <view class="voice__manual-actions">
                <BaseButton block size="lg" @click="goSearch">去搜索</BaseButton>
                <BaseButton block type="default" @click="goSelect">去手选</BaseButton>
              </view>
            </view>
          </template>
        </PermissionGuide>
      </template>

      <template v-else>
        <!-- 大按钮「按住说话」：整卡热区 ≥88rpx（实际 320rpx 高），状态双通道表达 -->
        <view
          class="voice__mic"
          :class="{ 'is-recording': stage === 'recording', 'is-recorded': stage === 'recorded' }"
          @touchstart="startRecord"
          @touchend="stopRecord"
          @touchcancel="stopRecord"
        >
          <text class="voice__mic-icon">🎤</text>
          <text class="voice__mic-label">{{ micLabel }}</text>
          <!-- ASR 占位如实说明（文案一字不改的承诺见文件头注释） -->
          <text v-if="stage === 'recorded'" class="voice__mic-note">
            语音识别服务暂不可用（微信同声传译插件待申请），请直接输入文字
          </text>
        </view>

        <!-- 手动输入兜底区：语音为增强功能，手动始终可用 -->
        <view class="voice__manual">
          <text class="voice__manual-title">直接输入</text>
          <BaseInput
            v-model="manualText"
            type="textarea"
            placeholder="或直接输入食材/菜名"
            :maxlength="-1"
          />
          <view class="voice__manual-actions">
            <BaseButton block size="lg" @click="goSearch">去搜索</BaseButton>
            <BaseButton block type="default" @click="goSelect">去手选</BaseButton>
          </view>
        </view>

        <DisclaimerBar scene="home" />
      </template>
    </view>
  </view>
</template>

<style scoped lang="scss">
.voice {
  box-sizing: border-box;
  min-height: 100%;
  padding: var(--space-md);
}

/* ── 大按钮：按住说话 ── */
.voice__mic {
  box-sizing: border-box;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: var(--space-sm);
  min-height: 320rpx;
  padding: var(--space-lg);
  margin-bottom: var(--space-lg);
  border-radius: var(--radius-card);
  background: var(--bg-card);
  border: 2rpx solid var(--border-color);
  box-shadow: var(--shadow-card);

  /* 录音中：主色描边 + 弱底（形状 + 色彩双通道，不依赖颜色单独传达） */
  &.is-recording {
    border-color: var(--color-primary);
    background: var(--color-primary-weak);
  }

  &.is-recorded {
    border-color: var(--color-warning);
    background: var(--color-warning-bg);
  }
}

.voice__mic-icon {
  font-size: 96rpx;
  line-height: 1.2;
}

.voice__mic-label {
  font-size: var(--font-size-lg);
  font-weight: 600;
  color: var(--text-primary);
  text-align: center;
}

.voice__mic-note {
  font-size: var(--font-size-sm);
  line-height: 1.6;
  color: var(--color-warning);
  text-align: center;
  word-break: break-all;
}

/* ── 手动输入兜底区 ── */
.voice__manual {
  display: flex;
  flex-direction: column;
  gap: var(--space-md);
  padding: var(--space-md);
  border-radius: var(--radius-card);
  background: var(--bg-card);
}

.voice__manual-title {
  font-size: var(--font-size-base);
  font-weight: 600;
  color: var(--text-primary);
}

.voice__manual-actions {
  display: flex;
  flex-direction: column;
  gap: var(--space-sm);
}
</style>
