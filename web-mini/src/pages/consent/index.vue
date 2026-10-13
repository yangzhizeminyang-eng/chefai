<!--
  文件级注释：P-00b 敏感个人信息单独同意页（RL-14：独立于总免责门，单独勾选、单独落库）。
  - onLoad options：scene（'allergen' | 'goal'）+ from（返回标记，预留）；
  - 场景化说明文本：过敏原 / 健康目标属敏感个人信息，单独说明用途（仅用于后端过滤
    推荐与营养展示，不用于其他目的，可随时删除）；
  - 独立勾选 + 「同意并继续」：postConsentSensitive 落库（失败按本地同意放行，对齐阶段一策略）
    → profile.markSensitiveConsented() → uni.$emit('aicook:consent-sensitive', { scene })
    → navigateBack（由发起页监听事件续跑保存）；「暂不同意」：navigateBack 不标记。
-->
<script setup lang="ts">
import { computed, ref } from 'vue'
import { onHide, onLoad } from '@dcloudio/uni-app'
import { postConsentSensitive } from '@/api/endpoints'
import { useProfileStore } from '@/stores/profile'
import { flushOnHide } from '@/utils/track'
import { useTheme } from '@/platform/theme'
import { useFontSize } from '@/platform/fontSize'
import BaseButton from '@/components-base/BaseButton.vue'

/** 敏感同意场景（allergen 过敏原 / goal 健康目标） */
type ConsentScene = 'allergen' | 'goal'

/** 深色模式标记（根节点 class） */
const { isDark } = useTheme()
/** 字号档位 class（根节点 class） */
const { fontSizeClass } = useFontSize()

/** profile store（markSensitiveConsented） */
const profile = useProfileStore()

/** 当前场景（onLoad 注入，缺省 allergen） */
const scene = ref<ConsentScene>('allergen')

/** 发起页透传的 from 标记（预留，暂不参与逻辑） */
const fromFlag = ref('')

/** 是否已独立勾选同意 */
const agreed = ref(false)

/** 落库请求进行中（防连点） */
const submitting = ref(false)

/** 场景 → 后端落库 scene 编码（allergen 对齐阶段一 'family_allergen'；goal 为健康目标场景） */
const SCENE_CODE: Record<ConsentScene, string> = {
  allergen: 'family_allergen',
  goal: 'diet_goal',
}

/** 场景 → 标题与用途说明（场景化文案：单独说明敏感数据的用途与删除权利） */
const SCENE_TEXT: Record<ConsentScene, { title: string; subject: string }> = {
  allergen: {
    title: '过敏原信息使用授权',
    subject: '过敏原',
  },
  goal: {
    title: '健康目标信息使用授权',
    subject: '健康目标',
  },
}

/** 用途说明固定小字（不散落硬编码到多处：本页单点维护，随场景响应式切换） */
const PURPOSE_TEXT = computed(
  () => `${SCENE_TEXT[scene.value].subject}属敏感个人信息，仅用于后端过滤推荐与营养展示，不用于其他目的，可随时在设置中删除。`,
)

/** 页面标题（按场景取） */
const titleText = computed(() => SCENE_TEXT[scene.value].title)

/**
 * onLoad：解析 scene / from 参数（非法 scene 兜底 allergen）。
 * @param options 页面参数（scene、from）
 * @returns 无
 */
onLoad((options) => {
  const rawScene = options?.scene
  if (rawScene === 'goal') scene.value = 'goal'
  else if (rawScene === 'allergen') scene.value = 'allergen'
  fromFlag.value = options?.from ?? ''
})

/**
 * 切换独立勾选（自绘勾选框，热区 ≥88rpx）。
 * @returns 无
 */
function toggleAgreed(): void {
  agreed.value = !agreed.value
}

/**
 * 「暂不同意」：不标记、不落库、不发事件，直接返回上一页（中断发起页保存流程）。
 * @returns 无
 */
function onDecline(): void {
  uni.navigateBack({ fail: () => {} })
}

/**
 * 「同意并继续」：落库（失败本地放行）→ 标记 → 广播事件 → 返回上一页续跑。
 * @returns 无
 * @throws 不抛出（落库失败按本地同意处理，不阻塞流程）
 */
async function onAgree(): Promise<void> {
  if (!agreed.value || submitting.value) return
  submitting.value = true
  try {
    try {
      await postConsentSensitive(SCENE_CODE[scene.value])
    } catch {
      // 落库失败：按本地同意放行（对齐阶段一「同意记录同步失败，已按本地同意处理」策略）
    }
    profile.markSensitiveConsented()
    uni.$emit('aicook:consent-sensitive', { scene: scene.value })
    uni.navigateBack({ fail: () => {} })
  } finally {
    submitting.value = false
  }
}

// 页面隐匿时尽力上报缓冲埋点
onHide(() => {
  flushOnHide()
})
</script>

<template>
  <view class="page" :class="[isDark ? 'dark' : '', fontSizeClass]">
    <view class="consent">
      <view class="consent__head">
        <text class="consent__title">{{ titleText }}</text>
      </view>

      <!-- 场景化用途说明（单独同意的告知要素：用途 / 范围 / 删除权利） -->
      <view class="consent__body">
        <text class="consent__purpose">{{ PURPOSE_TEXT }}</text>
        <text class="consent__note">本授权独立于免责声明，可单独撤回；不同意仅影响相关功能，不影响其余功能使用。</text>
      </view>

      <!-- 独立勾选（RL-14：不与总免责复用） -->
      <view class="consent__agree" @click="toggleAgreed">
        <view class="consent__checkbox" :class="{ 'is-checked': agreed }">
          <text v-if="agreed" class="consent__check-mark">✓</text>
        </view>
        <text class="consent__agree-text">我已知晓并单独同意</text>
      </view>

      <view class="consent__actions">
        <BaseButton class="consent__btn" type="default" block :disabled="submitting" @click="onDecline">
          暂不同意
        </BaseButton>
        <BaseButton
          class="consent__btn"
          block
          :disabled="!agreed"
          :loading="submitting"
          @click="onAgree"
        >
          同意并继续
        </BaseButton>
      </view>
    </view>
  </view>
</template>

<style scoped lang="scss">
.consent {
  box-sizing: border-box;
  min-height: 100%;
  padding: var(--space-lg) var(--space-md) var(--space-xl);
}

.consent__head {
  margin-bottom: var(--space-lg);
}

.consent__title {
  font-size: var(--font-size-lg);
  font-weight: 600;
  color: var(--text-primary);
}

.consent__body {
  display: flex;
  flex-direction: column;
  gap: var(--space-sm);
  padding: var(--space-md);
  border-radius: var(--radius-card);
  background: var(--bg-card);
}

.consent__purpose {
  font-size: var(--font-size-base);
  line-height: 1.6;
  color: var(--text-primary);
}

.consent__note {
  font-size: var(--font-size-sm);
  line-height: 1.6;
  color: var(--text-tertiary);
}

.consent__agree {
  display: flex;
  align-items: center;
  gap: var(--space-sm);
  min-height: var(--hit-min);
  margin-top: var(--space-lg);
}

.consent__checkbox {
  box-sizing: border-box;
  display: flex;
  align-items: center;
  justify-content: center;
  width: 40rpx;
  height: 40rpx;
  border: 2rpx solid var(--border-color);
  border-radius: var(--radius-ctrl);
  background: var(--bg-card);
  flex-shrink: 0;

  &.is-checked {
    border-color: var(--color-primary);
    background: var(--color-primary);
  }
}

.consent__check-mark {
  font-size: var(--font-size-sm);
  color: var(--text-inverse);
}

.consent__agree-text {
  font-size: var(--font-size-base);
  color: var(--text-primary);
}

.consent__actions {
  display: flex;
  flex-direction: column;
  gap: var(--space-sm);
  margin-top: var(--space-md);
}
</style>
