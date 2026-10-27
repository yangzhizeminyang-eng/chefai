<script setup lang="ts">
/**
 * 组件职责：推荐结果卡片（自 W-02 RecommendView 内联卡片迁移，行为保持一致，供推荐列表复用）。
 * - 卡顶图片区（RecipeCover，16:9）：有 cover_image_url 加载真实语料图（懒加载 + 骨架），
 *   无图或加载失败回落程序化占位封面（色板 + 🍳 + 菜名 + 「示意图」角标），绝不裂图；
 * - 卡头：菜名 +「为什么推荐给你」rank_reasons 弹层（DEF-13：hover → click 触发，
 *   误悬浮不再弹出；按钮保留 @click.stop 与键盘可达性）；
 * - 元信息：⏱耗时 / 🍳难度 / 🔥热量（null → 如实标注「热量未纳入统计」）/
 *   📦覆盖率（showCoverage=false 时不渲染，ask 直达态无食材匹配数据）；
 * - 缺料标签区：DEF-04 渲染前过滤无名/纯数字脏项 + DEF-12 超过 5 个折叠为
 *   「前 5 个 + 等 N 样」（组件内每卡独立展开状态，点击展开不提供再收起）；
 * - 设备标签（需要 X 设备）；
 * - 整卡点击跳菜谱详情 W-03（/recipe/{id}，组件内 useRouter 完成跳转）。
 */
import { computed, ref } from 'vue'
import { useRouter } from 'vue-router'
import type { RecommendResultItem } from '@/api/types'
import {
  MISSING_TAGS_VISIBLE_LIMIT,
  coveragePercent,
  filterValidMissing,
  foldMissingTags,
} from '@/utils/recipe'
import RecipeCover from '@/components/RecipeCover.vue'

/** 组件入参 */
const props = withDefaults(
  defineProps<{
    /** 推荐结果条目（契约对齐 RecommendResultItem） */
    item: RecommendResultItem
    /** 是否展示覆盖率列（默认 true；ask 直达态父级传 false 隐藏） */
    showCoverage?: boolean
  }>(),
  { showCoverage: true },
)

/** 路由（整卡点击跳详情 W-03） */
const router = useRouter()

/** 难度编码 → 中文标签（契约 difficulty: easy/medium/hard） */
const DIFFICULTY_LABELS: Record<RecommendResultItem['difficulty'], string> = {
  easy: '简单',
  medium: '中等',
  hard: '较难',
}

/**
 * 难度编码转中文标签。
 * @param d 难度编码
 * @returns 中文标签
 */
function difficultyLabel(d: RecommendResultItem['difficulty']): string {
  return DIFFICULTY_LABELS[d]
}

// ── DEF-04/DEF-12：缺料标签过滤 + 折叠（逻辑迁自 RecommendView；页面级 Set
//    改为组件内单卡布尔状态，每卡独立展开互不影响） ──

/** 本卡片是否已展开全部缺料标签（点击「等 N 样」后置 true，入口消失，不提供再收起） */
const expandedMissing = ref(false)

/** 过滤脏项后的完整缺料列表（DEF-04：无名/纯数字项剔除 + 去重） */
const validMissing = computed(() => filterValidMissing(props.item.missing_ingredients))

/** 折叠结果（DEF-12）：visible 前 5 个 / overflow 折叠数量 */
const folded = computed(() => foldMissingTags(validMissing.value, MISSING_TAGS_VISIBLE_LIMIT))

/** 当前应展示的缺料标签列表：已展开（或未超阈值）展示全量，否则只展示前 5 个 */
const visibleMissing = computed(() =>
  expandedMissing.value || folded.value.overflow === 0 ? validMissing.value : folded.value.visible,
)

/** 是否需要渲染「等 N 样」折叠入口（有被折叠项且尚未展开） */
const hasMissingOverflow = computed(() => folded.value.overflow > 0 && !expandedMissing.value)

/** 被折叠的缺料数量（「等 N 样」文案用） */
const missingOverflowCount = computed(() => folded.value.overflow)

/** 覆盖率百分比（0~100 整数，ask 直达态 covered/missing 为空 → 0，该态整列隐藏） */
const coverage = computed(() =>
  coveragePercent(props.item.covered_ingredients, props.item.missing_ingredients),
)

/**
 * 点击「等 N 样」展开本卡片全部缺料标签（点击后入口消失，不提供再收起，保持交互简单）。
 * @returns 无
 */
function expandMissing(): void {
  expandedMissing.value = true
}

/**
 * 卡片点击 → 菜谱详情 W-03。
 * @returns 无
 */
function goDetail(): void {
  void router.push(`/recipe/${props.item.recipe_id}`)
}
</script>

<template>
  <div class="recipe-card" role="button" @click="goDetail">
    <!-- 卡顶图片区：有图加载真实图（懒加载 + 骨架），无图/失败回落占位封面（内边距内，圆角 8px） -->
    <RecipeCover
      class="card-cover"
      :src="item.cover_image_url"
      :title="item.title"
      :recipe-id="item.recipe_id"
    />
    <div class="card-head">
      <span class="card-title">{{ item.title }}</span>
      <!-- 为什么推荐给你：rank_reasons 弹层（DEF-13：hover → click 触发，
           误悬浮不再弹出；按钮可聚焦，click 触发保留键盘可达性） -->
      <el-popover placement="top" :width="320" trigger="click">
        <template #reference>
          <el-button link type="primary" size="small" @click.stop>为什么推荐给你</el-button>
        </template>
        <ul class="reason-list">
          <li v-for="(reason, i) in item.rank_reasons" :key="i">{{ reason }}</li>
        </ul>
      </el-popover>
    </div>
    <div class="card-meta">
      <span>⏱ {{ item.time_minutes }} 分钟</span>
      <span>🍳 {{ difficultyLabel(item.difficulty) }}</span>
      <span>
        🔥 {{ item.calories_kcal != null ? `${item.calories_kcal} kcal/份` : '热量未纳入统计' }}
      </span>
      <!-- 覆盖率：showCoverage=false（ask 直达态无食材匹配数据）时不渲染 -->
      <span v-if="showCoverage">📦 覆盖率 {{ coverage }}%</span>
    </div>
    <!-- 缺料标签区（DEF-04：渲染前过滤无名/纯数字脏项；DEF-12：>5 个折叠为
         前 5 个 + 「等 N 样」，点击展开全部）。缺料为空且无设备标注时区块不渲染 -->
    <div v-if="visibleMissing.length > 0 || item.required_equipment.length > 0" class="card-tags">
      <el-tag v-for="m in visibleMissing" :key="`miss-${m}`" type="warning" size="small">
        缺 {{ m }}
      </el-tag>
      <!-- 折叠入口：点击展开该卡片全部缺料标签（.stop 防止冒泡触发卡片跳详情） -->
      <el-tag
        v-if="hasMissingOverflow"
        class="missing-more"
        type="warning"
        size="small"
        effect="plain"
        role="button"
        @click.stop="expandMissing"
      >
        等 {{ missingOverflowCount }} 样
      </el-tag>
      <el-tag
        v-for="eq in item.required_equipment"
        :key="`eq-${eq}`"
        class="equipment-tag"
        type="info"
        size="small"
      >
        需要 {{ eq }} 设备
      </el-tag>
    </div>
  </div>
</template>

<style scoped>
.recipe-card {
  padding: 14px 16px;
  border: 1px solid var(--color-info-border);
  border-radius: 10px;
  background: var(--card-bg);
  cursor: pointer;
  transition:
    border-color 0.2s ease,
    box-shadow 0.2s ease;
}

.recipe-card:hover {
  border-color: var(--el-color-primary);
  box-shadow: 0 2px 10px rgba(0, 0, 0, 0.08);
}

/* 卡顶图片区：置于内边距内，与下方卡头留出一行间距 */
.card-cover {
  margin-bottom: 10px;
}

.card-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
}

.card-title {
  font-size: var(--font-lg);
  font-weight: 600;
  color: var(--text-main);
}

.reason-list {
  margin: 0;
  padding-left: 18px;
  font-size: var(--font-sm);
  line-height: 1.8;
}

.card-meta {
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
  margin-top: 10px;
  font-size: var(--font-sm);
  color: var(--text-main);
}

.card-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin-top: 10px;
}

/* DEF-12：「等 N 样」折叠入口可点击展开（role=button + 手型光标提示可交互） */
.missing-more {
  cursor: pointer;
}
</style>
