<script setup>
/**
 * TengAgent Console 主界面
 * 布局：左侧对话区 | 右侧观测面板（时间线 / 步骤详情 / Token 瀑布 / 记忆）
 */
import { ref, reactive, nextTick, watch, computed } from 'vue'
import { useAgentStream } from './composables/useAgentStream.js'
import StepCard from './components/StepCard.vue'
import StreamMarkdown from './components/StreamMarkdown.vue'
import Timeline from './components/Timeline.vue'
import TokenWaterfall from './components/TokenWaterfall.vue'
import MemoryView from './components/MemoryView.vue'

const { send, streaming } = useAgentStream()

const sessionId = `s-${Date.now()}`
const input = ref('')
const chatBox = ref(null)
const activeTab = ref('steps') // steps | tokens | memory

// 当前这一轮 agent 运行的状态
const run = reactive({
  meta: null,
  steps: [],
  answer: '',
  answerStreaming: false,
  usage: null,
  history: [],
  fallbackReason: null,
})

const suggestions = [
  '查一下订单 SO20261001 的物流',
  '订单 SO20261001 能退多少？',
  '推荐一款耳机',
]

const canSend = computed(() => input.value.trim() && !streaming.value)

async function submit(preset) {
  const message = (preset ?? input.value).trim()
  if (!message || streaming.value) return
  input.value = ''

  // 重置本轮运行状态
  run.meta = null
  run.steps = []
  run.answer = ''
  run.answerStreaming = false
  run.usage = null
  run.fallbackReason = null
  run.history.push({ role: 'user', content: message })
  activeTab.value = 'steps'
  scrollBottom()

  await send(message, sessionId, {
    meta: (d) => { run.meta = d },
    step_start: (d) => {
      run.steps.push({
        index: d.step,
        thought: '',
        thoughtStreaming: false,
        action: null,
        args: null,
        observation: null,
        durationMs: 0,
        status: 'thinking',
        promptTokens: 0,
        completionTokens: 0,
      })
      scrollBottom()
    },
    thought_delta: (d) => {
      const s = run.steps.find((x) => x.index === d.step)
      if (s) s.thought += d.text
    },
    thought_done: (d) => {
      const s = run.steps.find((x) => x.index === d.step)
      if (s) {
        s.thought = d.text
        s.thoughtStreaming = false
      }
    },
    action_start: (d) => {
      const s = run.steps.find((x) => x.index === d.step)
      if (s) {
        s.action = d.action
        s.args = d.args
        s.status = 'acting'
      }
    },
    observation: (d) => {
      const s = run.steps.find((x) => x.index === d.step)
      if (s) {
        s.observation = d.result
        s.durationMs = d.duration_ms
        s.status = 'done'
        s.promptTokens = Math.round(JSON.stringify(d.result).length / 3)
      }
      scrollBottom()
    },
    answer_start: () => {
      run.answerStreaming = true
      scrollBottom()
    },
    answer_delta: (d) => {
      run.answer += d.text
      scrollBottom()
    },
    answer_done: (d) => {
      run.answer = d.text
      run.answerStreaming = false
      run.history.push({ role: 'assistant', content: d.text })
      scrollBottom()
    },
    usage: (d) => {
      run.usage = d
      // 把 completion tokens 分摊到最后一个步骤上展示
      const last = run.steps[run.steps.length - 1]
      if (last) last.completionTokens = d.completion_tokens
    },
    fallback: (d) => {
      run.fallbackReason = d.reason
      if (run.meta) run.meta.mode = 'fallback'
    },
    error: (d) => {
      run.answer = `⚠️ 错误：${d.message}`
      run.answerStreaming = false
    },
  })
}

function scrollBottom() {
  nextTick(() => {
    const el = chatBox.value
    if (el) el.scrollTop = el.scrollHeight
  })
}

// thought 流式时给卡片加"思考中"状态
watch(
  () => run.steps.length,
  () => {
    const s = run.steps[run.steps.length - 1]
    if (s && s.status === 'thinking' && !s.thoughtStreaming) s.thoughtStreaming = true
  },
)
</script>

<template>
  <div class="layout">
    <!-- 左侧：对话 -->
    <section class="chat">
      <header class="chat-header">
        <div class="brand">
          <span class="brand-logo">⚡</span>
          <div>
            <h1>TengAgent Console</h1>
            <p>商城客服 Agent · ReAct 可视化调试台</p>
          </div>
        </div>
        <div class="mode-tag" v-if="run.meta">
          {{ run.meta.mode === 'real' ? `🤖 ${run.meta.model}` : run.meta.mode === 'fallback' ? '↩️ 已降级 Mock' : '🧪 Mock 模式' }}
        </div>
      </header>

      <div class="chat-box" ref="chatBox">
        <div class="welcome" v-if="!run.history.length">
          <h2>观察一个 Agent 是怎么"思考"的 👀</h2>
          <p>每次回复都会实时拆解：Thought 推理 → 工具调用 → Observation 观测 → 最终回答。</p>
          <p>试试下面的问题：</p>
          <div class="suggestions">
            <button v-for="s in suggestions" :key="s" class="sug-btn" @click="submit(s)">{{ s }}</button>
          </div>
        </div>

        <template v-for="(m, i) in run.history" :key="i">
          <div v-if="m.role === 'user'" class="msg user-msg">{{ m.content }}</div>
        </template>

        <!-- 本轮 agent 运行过程（只在流式中/最后一轮展示） -->
        <div v-if="streaming || run.answer || run.steps.length" class="agent-block">
          <div class="msg ai-msg">
            <div class="ai-label">TengAgent</div>

            <div v-if="run.fallbackReason" class="fallback-banner">
              ⚠️ 真实模型调用失败，已自动降级为 Mock 模式继续（生产环境可配置 <code>OPENAI_API_KEY</code>）
            </div>

            <div v-for="s in run.steps" :key="s.index" class="step-wrap">
              <StepCard :step="s" />
            </div>

            <div v-if="run.answer || run.answerStreaming" class="answer-wrap">
              <StreamMarkdown :text="run.answer" />
              <span v-if="run.answerStreaming" class="caret"></span>
            </div>

            <div v-else-if="streaming" class="thinking-hint">
              <span class="dot-pulse"></span> Agent 正在推理…
            </div>

            <div v-if="run.usage" class="usage-chip">
              {{ run.usage.total_tokens }} tokens · {{ run.usage.latency_ms }}ms · {{ run.usage.steps }} 步
            </div>
          </div>
        </div>
      </div>

      <footer class="chat-input">
        <textarea
          v-model="input"
          placeholder="Enter 发送，Shift+Enter 换行…"
          rows="2"
          @keydown.enter.exact.prevent="submit()"
        ></textarea>
        <button class="send-btn" :disabled="!canSend" @click="submit()">
          <span v-if="streaming" class="spinner"></span>
          <span v-else>发送</span>
        </button>
      </footer>
    </section>

    <!-- 右侧：观测面板 -->
    <aside class="panel">
      <nav class="panel-tabs">
        <button :class="{ active: activeTab === 'steps' }" @click="activeTab = 'steps'">链路</button>
        <button :class="{ active: activeTab === 'tokens' }" @click="activeTab = 'tokens'">Token</button>
        <button :class="{ active: activeTab === 'memory' }" @click="activeTab = 'memory'">记忆</button>
      </nav>

      <div class="panel-body">
        <template v-if="activeTab === 'steps'">
          <Timeline :steps="run.steps" :answered="!!run.answer" />
          <div v-if="!run.steps.length" class="panel-empty">发送消息后，这里会实时显示 ReAct 推理链路。</div>
        </template>

        <template v-else-if="activeTab === 'tokens'">
          <TokenWaterfall
            :steps="run.steps.map((s) => ({ index: s.index, action: s.action, promptTokens: s.promptTokens, completionTokens: s.completionTokens }))"
            :usage="run.usage"
          />
        </template>

        <template v-else>
          <MemoryView :history="run.history" :keep-last="8" />
        </template>
      </div>
    </aside>
  </div>
</template>
