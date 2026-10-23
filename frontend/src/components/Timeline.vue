<script setup>
/**
 * ReAct 时间线：垂直节点图，展示 Thought → Action → Observation 的推进。
 * 每个节点显示工具名与状态，连线随步骤增长动态出现。
 */
defineProps({
  steps: { type: Array, default: () => [] },
  answered: { type: Boolean, default: false },
})
</script>

<template>
  <div class="timeline">
    <div v-for="(s, i) in steps" :key="s.index" class="tl-node">
      <div class="tl-dot" :class="s.status">
        <span v-if="s.status === 'thinking' || s.status === 'acting'" class="tl-pulse"></span>
      </div>
      <div v-if="i < steps.length - 1 || answered" class="tl-line"></div>
      <div class="tl-content">
        <div class="tl-title">
          <template v-if="s.action">{{ s.action }}</template>
          <template v-else>思考</template>
        </div>
        <div class="tl-sub" v-if="s.observation">观测完成 · {{ s.durationMs }}ms</div>
        <div class="tl-sub muted" v-else-if="s.status === 'thinking'">推理中…</div>
        <div class="tl-sub muted" v-else-if="s.status === 'acting'">调用中…</div>
      </div>
    </div>
    <div v-if="answered" class="tl-node">
      <div class="tl-dot answer">✓</div>
      <div class="tl-content">
        <div class="tl-title">生成回答</div>
      </div>
    </div>
  </div>
</template>
