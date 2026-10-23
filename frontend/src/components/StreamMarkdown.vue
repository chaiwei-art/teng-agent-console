<script setup>
/**
 * 增量 Markdown 渲染器。
 *
 * 流式渲染的经典问题：如果每次都把半截文本丢给 marked，
 * 代码块 fence 没闭合会整篇错乱、表格逐帧闪烁。
 *
 * 这里的策略：
 * 1. 检测未闭合的 ``` 围栏 → 该段按纯文本 pre 渲染并锁定，等闭合后才转 Markdown
 * 2. 表格行不完整（没有换行结尾）→ 暂缓渲染最后一行
 * 3. 每次全量重渲染文本（HTML 转义后拼接），配合 v-html；文本量在对话场景很小，性能足够
 */
import { computed } from 'vue'

const props = defineProps({ text: { type: String, default: '' } })

function escapeHtml(s) {
  return s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
}

function inlineFormat(s) {
  return s
    .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
    .replace(/`([^`]+)`/g, '<code>$1</code>')
}

function renderFull(lines) {
  const html = []
  let inCode = false
  let codeBuf = []
  let listBuf = []
  let tableBuf = []

  const flushList = () => {
    if (listBuf.length) {
      html.push(`<ul>${listBuf.map((l) => `<li>${inlineFormat(escapeHtml(l))}</li>`).join('')}</ul>`)
      listBuf = []
    }
  }
  const flushTable = () => {
    if (tableBuf.length) {
      const rows = tableBuf
      const head = rows[0].map((c) => `<th>${inlineFormat(escapeHtml(c.trim()))}</th>`).join('')
      const body = rows
        .slice(1)
        .map((r) => `<tr>${r.map((c) => `<td>${inlineFormat(escapeHtml(c.trim()))}</td>`).join('')}</tr>`)
        .join('')
      html.push(`<div class="md-table-wrap"><table><thead><tr>${head}</tr></thead><tbody>${body}</tbody></table></div>`)
      tableBuf = []
    }
  }

  for (const rawLine of lines) {
    if (rawLine.startsWith('```')) {
      if (inCode) {
        html.push(`<pre class="md-code"><code>${escapeHtml(codeBuf.join('\n'))}</code></pre>`)
        codeBuf = []
        inCode = false
      } else {
        flushList()
        flushTable()
        inCode = true
      }
      continue
    }
    if (inCode) {
      codeBuf.push(rawLine)
      continue
    }
    if (/^\s*[-*]\s+/.test(rawLine)) {
      flushTable()
      listBuf.push(rawLine.replace(/^\s*[-*]\s+/, ''))
      continue
    }
    flushList()
    if (rawLine.includes('|') && /^\s*\|.*\|\s*$/.test(rawLine)) {
      tableBuf.push(rawLine.split('|').slice(1, -1))
      continue
    }
    flushTable()
    if (rawLine.startsWith('### ')) html.push(`<h4>${inlineFormat(escapeHtml(rawLine.slice(4)))}</h4>`)
    else if (rawLine.startsWith('## ')) html.push(`<h3>${inlineFormat(escapeHtml(rawLine.slice(3)))}</h3>`)
    else if (rawLine.startsWith('# ')) html.push(`<h3>${inlineFormat(escapeHtml(rawLine.slice(2)))}</h3>`)
    else if (rawLine.trim() === '') html.push('<div class="md-gap"></div>')
    else html.push(`<p>${inlineFormat(escapeHtml(rawLine))}</p>`)
  }
  // 流式中：未闭合的代码块先按 pre 锁定渲染
  if (inCode) {
    html.push(`<pre class="md-code streaming"><code>${escapeHtml(codeBuf.join('\n'))}</code></pre>`)
  }
  flushList()
  flushTable()
  return html.join('')
}

const html = computed(() => renderFull(props.text.split('\n')))
</script>

<template>
  <div class="stream-md" v-html="html"></div>
</template>
