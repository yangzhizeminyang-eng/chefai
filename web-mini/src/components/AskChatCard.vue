<script setup lang="ts">
/**
 * 文件级注释：受限问答结果卡（业务组件）。
 * 自 web-stage1/src/components/AskChatCard.vue 迁移：阶段一数据源为 ask store 的 chat 态，
 * 小程序端收敛为受控 props（页面请求数据后传入，组件不做网络与 store 依赖）：
 * - 问答气泡布局：用户问句（右侧主色弱底气泡）+ 厨娘回答（左侧卡片气泡）+ 免责小字；
 * - refuse = true（RL-7 医疗拒答）：回答气泡改用中性视觉（info 色系）呈现
 *   MEDICAL_REFUSE_TEXT 或页面定制 refuseText，不用红色警示样式（就医引导非警告）；
 * - 免责小字固定 DISCLAIMER_TEXT（@shared/constants 收口）；
 * - question 与 answer 均为空时整体不渲染。
 * 使用约束：由页面根 .page/.dark 提供主题变量上下文。
 */
import { computed } from 'vue'
import { MEDICAL_REFUSE_TEXT, DISCLAIMER_TEXT } from '@shared/constants'

/** 组件入参 */
const props = withDefaults(
  defineProps<{
    /** 用户问句（溯源回显；空则不渲染问句气泡） */
    question: string
    /** 回答正文（空则不渲染整卡） */
    answer: string
    /** 是否拒答态（RL-7 医疗拒答：中性视觉 + 就医引导，非红色警示） */
    refuse?: boolean
    /** 页面定制拒答文案（可选；缺省用 MEDICAL_REFUSE_TEXT 常量） */
    refuseText?: string
  }>(),
  { refuse: false, refuseText: '' },
)

/** 是否渲染整卡（回答为空则不渲染） */
const hasContent = computed(() => props.answer.length > 0 || props.question.length > 0)

/** 拒答态实际展示文案：refuseText 优先，缺省 MEDICAL_REFUSE_TEXT 常量 */
const refuseDisplayText = computed(() => (props.refuseText ? props.refuseText : MEDICAL_REFUSE_TEXT))
</script>

<template>
  <view v-if="hasContent" class="ask-card">
    <!-- 问句气泡（用户侧，右对齐）：有问句才渲染 -->
    <view v-if="question" class="ask-card__question-row">
      <view class="ask-card__question">{{ question }}</view>
    </view>

    <!-- 回答气泡（厨娘侧，左对齐）：拒答态切中性 info 视觉 -->
    <view class="ask-card__answer-row">
      <view class="ask-card__answer" :class="{ 'is-refuse': refuse }">
        <text class="ask-card__tag">{{ refuse ? '无法回答' : '厨娘回答' }}</text>
        <text class="ask-card__answer-text">{{ refuse ? refuseDisplayText : answer }}</text>
      </view>
    </view>

    <!-- 免责小字（G-02 语义，不使用警示色） -->
    <text class="ask-card__disclaimer">{{ DISCLAIMER_TEXT }}</text>
  </view>
</template>

<style scoped lang="scss">
.ask-card {
  box-sizing: border-box;
  display: block;
  width: 100%;
}

.ask-card__question-row {
  display: flex;
  justify-content: flex-end;
  margin-bottom: var(--space-sm);
}

/* 问句气泡：主色弱底 */
.ask-card__question {
  box-sizing: border-box;
  max-width: 80%;
  padding: var(--space-sm) var(--space-md);
  border-radius: var(--radius-card);
  border-top-right-radius: var(--radius-ctrl);
  background: var(--color-primary-weak);
  color: var(--text-primary);
  font-size: var(--font-size-sm);
  line-height: 1.6;
  word-break: break-all;
}

.ask-card__answer-row {
  display: flex;
  justify-content: flex-start;
}

/* 回答气泡：卡片底 */
.ask-card__answer {
  box-sizing: border-box;
  max-width: 88%;
  padding: var(--space-sm) var(--space-md);
  border-radius: var(--radius-card);
  border-top-left-radius: var(--radius-ctrl);
  background: var(--bg-card);
  border: 1rpx solid var(--border-color);
  display: flex;
  flex-direction: column;

  /* 拒答态（RL-7）：中性 info 视觉 + 就医引导，不用红色警示 */
  &.is-refuse {
    background: var(--color-info-bg);
    border-color: transparent;
  }
}

.ask-card__tag {
  font-size: var(--font-size-sm);
  font-weight: 600;
  line-height: 1.6;
  color: var(--color-primary);
}

.ask-card__answer-text {
  margin-top: var(--space-xs);
  font-size: var(--font-size-sm);
  line-height: 1.7;
  color: var(--text-primary);
  word-break: break-all;
}

.ask-card__disclaimer {
  display: block;
  margin-top: var(--space-sm);
  font-size: var(--font-size-sm);
  line-height: 1.5;
  color: var(--text-tertiary);
  word-break: break-all;
}
</style>
