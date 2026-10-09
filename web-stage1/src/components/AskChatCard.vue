<script setup lang="ts">
/**
 * 组件职责：POST /v1/ask 受限问答（chat 意图）的就地结果卡。
 * 数据源为 ask store 的 chat 态；首页与食材选择页复用（缺陷修复：free_qa 原先
 * 在两视图分别为「toast + 跳转」与「ElMessageBox 弹窗」，现统一为搜索框下结果卡）。
 * 展示：用户问句、厨娘回答文本、AI 生成免责小字；无内容时整体不渲染。
 */
import { useAskStore } from '@/stores/ask'

/** ask store：chat 回答数据与收起动作 */
const askStore = useAskStore()
</script>

<template>
  <div v-if="askStore.chat" class="ask-chat-card">
    <!-- 头部：标识 + 收起（清空 store chat 态） -->
    <div class="chat-head">
      <span class="chat-tag">厨娘回答</span>
      <el-button link size="small" @click="askStore.clearChat()">收起</el-button>
    </div>
    <!-- 问句回显（溯源） -->
    <p class="chat-question">问：{{ askStore.chat.question }}</p>
    <!-- 回答正文 -->
    <p class="chat-answer">{{ askStore.chat.answer }}</p>
    <!-- 免责小字（G-02 语义，不使用警示色） -->
    <p class="chat-disclaimer">内容由 AI 生成，仅供参考；食品安全与健康状况请以专业意见为准。</p>
  </div>
</template>

<style scoped>
.ask-chat-card {
  padding: 14px 16px;
  margin-bottom: 16px;
  border: 1px solid var(--el-color-primary-light-7);
  border-radius: 10px;
  background: var(--el-color-primary-light-9);
}

.chat-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 6px;
}

.chat-tag {
  font-size: var(--font-sm);
  font-weight: 600;
  color: var(--el-color-primary);
}

.chat-question {
  margin: 0 0 6px;
  font-size: var(--font-sm);
  color: var(--color-info);
  word-break: break-word;
}

.chat-answer {
  margin: 0 0 8px;
  font-size: var(--font-md);
  line-height: 1.7;
  color: var(--text-main);
  white-space: pre-wrap;
  word-break: break-word;
}

.chat-disclaimer {
  margin: 0;
  font-size: 12px;
  color: var(--color-info);
}
</style>
