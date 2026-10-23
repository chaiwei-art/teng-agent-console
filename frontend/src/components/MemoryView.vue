<script setup>
/**
 * 记忆可视化：展示会话上下文窗口。
 * - 每条消息一个色块，高度 ∝ 估算 token
 * - 超出保留阈值的旧消息标记为"已压缩"（对应后端 history 截断策略）
 */
import { computed } from 'vue'

const props = defineProps({
  history: { type: Array, default: () => [] }, // [{ role, content }]
  keepLast: { type: Number, default: 8 },
})

const items = computed(() => {
  const h = props.history
  const start = Math.max(0, h.length - props.keepLast)
  return h.map((m, i) => {
    const cn = (m.content.match(/[一-鿿]/g) || []).length
    const tokens = Math.max(1, cn + (m.content.length - cn) / 4)
    return {
      ...m,
      tokens: Math.round(tokens),
      compressed: i < start,
      short: m.content.slice(0, 48).replace(/\n/g, ' '),
    }
  })
})

const totalTokens = computed(() => items.value.reduce((a, b) => a + b.tokens, 0))
</script>

<template>
  <div class="memory">
    <div class="mem-header">
      <span>上下文占用 ≈ {{ totalTokens }} tokens</span>
      <span class="mem-hint">保留最近 {{ keepLast }} 条</span>
    </div>
    <div class="mem-window">
      <div
        v-for="(m, i) in items"
        :key="i"
        class="mem-block"
        :class="[m.role, { compressed: m.compressed }]"
        :title="m.content"
      >
        <span class="mem-role">{{ m.role === 'assistant' ? 'AI' : 'USR' }}</span>
        <span class="mem-text">{{ m.short }}</span>
        <span class="mem-tokens">~{{ m.tokens }}</span>
      </div>
      <div v-if="!items.length" class="mem-empty">尚无历史消息</div>
    </div>
  </div>
</template>
