<script setup>
/**
 * 单个 ReAct 步骤卡片：Thought（流式）→ Action（参数 JSON）→ Observation（结果 + 耗时）。
 * status: pending | thinking | acting | observed | done
 */
import { ref, computed } from 'vue'

const props = defineProps({
  step: { type: Object, required: true }, // { index, thought, thoughtStreaming, action, args, observation, durationMs, status }
})

const expanded = ref(true)
const showJson = ref(false)

const statusMeta = computed(() => {
  switch (props.step.status) {
    case 'thinking':
      return { label: '思考中', cls: 'st-thinking' }
    case 'acting':
      return { label: '调用工具', cls: 'st-acting' }
    case 'observed':
    case 'done':
      return { label: '完成', cls: 'st-done' }
    default:
      return { label: '等待', cls: 'st-pending' }
  }
})

function pretty(obj) {
  return JSON.stringify(obj, null, 2)
}
</script>

<template>
  <div class="step-card" :class="step.status">
    <button class="step-head" @click="expanded = !expanded">
      <span class="step-index">step {{ step.index }}</span>
      <span class="step-action" v-if="step.action">
        <svg width="12" height="12" viewBox="0 0 16 16" fill="currentColor"><path d="M8 1a2 2 0 0 1 2 2v2h2a2 2 0 0 1 2 2v6a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V7a2 2 0 0 1 2-2h2V3a2 2 0 0 1 2-2Zm0 1.5A.5.5 0 0 0 7.5 3v2h1V3a.5.5 0 0 0-.5-.5Z"/></svg>
        {{ step.action }}
      </span>
      <span class="step-badge" :class="statusMeta.cls">{{ statusMeta.label }}</span>
      <span class="step-chevron" :class="{ open: expanded }">▾</span>
    </button>

    <div v-show="expanded" class="step-body">
      <!-- Thought -->
      <div class="thought-line">
        <span class="thought-label">Thought</span>
        <p class="thought-text">
          {{ step.thought }}<span v-if="step.thoughtStreaming" class="caret"></span>
        </p>
      </div>

      <!-- Action -->
      <template v-if="step.action">
        <div class="action-line">
          <span class="action-label">Action</span>
          <code class="action-name">{{ step.action }}</code>
          <button class="json-toggle" @click="showJson = !showJson">
            {{ showJson ? '收起参数' : '查看参数' }}
          </button>
        </div>
        <pre v-if="showJson" class="json-block">{{ pretty(step.args) }}</pre>

        <!-- Observation -->
        <div class="obs-line" v-if="step.observation">
          <span class="obs-label">Observation</span>
          <span class="obs-duration">{{ step.durationMs }}ms</span>
          <pre class="obs-result">{{ pretty(step.observation) }}</pre>
        </div>
      </template>
    </div>
  </div>
</template>
