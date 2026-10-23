<script setup>
/**
 * Token 消耗瀑布图：每个 step 一根横条（宽度 ∝ token 数），
 * 用纯 SVG/div 实现，不引第三方图表库（保持零 UI 依赖）。
 */
import { computed } from 'vue'

const props = defineProps({
  steps: { type: Array, default: () => [] }, // [{ index, action, promptTokens, completionTokens }]
  usage: { type: Object, default: null }, // { prompt_tokens, completion_tokens, total_tokens, latency_ms }
})

const maxTokens = computed(() =>
  Math.max(1, ...props.steps.map((s) => (s.promptTokens || 0) + (s.completionTokens || 0))),
)

function width(t) {
  return `${((t / maxTokens.value) * 100).toFixed(1)}%`
}
</script>

<template>
  <div class="waterfall">
    <div v-if="!steps.length" class="wf-empty">等待 Agent 运行…</div>
    <div v-for="s in steps" :key="s.index" class="wf-row">
      <span class="wf-label">{{ s.action || `step ${s.index}` }}</span>
      <div class="wf-bar-track">
        <div class="wf-bar prompt" :style="{ width: width(s.promptTokens || 0) }"></div>
        <div class="wf-bar completion" :style="{ width: width(s.completionTokens || 0) }"></div>
      </div>
      <span class="wf-count">{{ (s.promptTokens || 0) + (s.completionTokens || 0) }}</span>
    </div>

    <div v-if="usage" class="wf-total">
      <div class="wf-total-item">
        <span class="wf-dot prompt"></span>输入 {{ usage.prompt_tokens }}
      </div>
      <div class="wf-total-item">
        <span class="wf-dot completion"></span>输出 {{ usage.completion_tokens }}
      </div>
      <div class="wf-total-item strong">共 {{ usage.total_tokens }} tokens</div>
      <div class="wf-total-item">⏱ {{ usage.latency_ms }}ms</div>
    </div>
  </div>
</template>
