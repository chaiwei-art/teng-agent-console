/**
 * 手写 SSE 客户端（基于 fetch + ReadableStream）。
 *
 * 为什么不用 EventSource：
 * 1. EventSource 只支持 GET，而对话需要 POST 传 message
 * 2. EventSource 不暴露原始字节流，无法做增量 Markdown 的精细控制
 *
 * 关键点：网络分包是任意的（一个 chunk 可能是半行、也可能跨多个事件），
 * 所以必须维护 buffer，按 \n\n 切帧后再解析 event/data。
 */
import { ref } from 'vue'

export function useAgentStream() {
  const connected = ref(false)
  const streaming = ref(false)
  let abortController = null

  /**
   * @param {string} message 用户消息
   * @param {Record<string, Function>} handlers 事件回调表 event -> fn(data)
   */
  async function send(message, sessionId, handlers) {
    abortController = new AbortController()
    streaming.value = true

    try {
      const resp = await fetch('/api/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ message, session_id: sessionId }),
        signal: abortController.signal,
      })
      if (!resp.ok || !resp.body) {
        throw new Error(`HTTP ${resp.status}`)
      }
      connected.value = true

      const reader = resp.body.getReader()
      const decoder = new TextDecoder('utf-8')
      let buffer = ''

      for (;;) {
        const { done, value } = await reader.read()
        if (done) break
        buffer += decoder.decode(value, { stream: true })

        // 按空行切帧；buffer 里可能残留半帧，留到下一轮
        let idx
        while ((idx = buffer.indexOf('\n\n')) !== -1) {
          const frame = buffer.slice(0, idx)
          buffer = buffer.slice(idx + 2)
          _dispatchFrame(frame, handlers)
        }
      }
    } finally {
      streaming.value = false
    }
  }

  function _dispatchFrame(frame, handlers) {
    let event = 'message'
    const dataLines = []
    for (const line of frame.split('\n')) {
      if (line.startsWith('event:')) event = line.slice(6).trim()
      else if (line.startsWith('data:')) dataLines.push(line.slice(5).trim())
    }
    if (!dataLines.length) return
    let data = {}
    try {
      data = JSON.parse(dataLines.join('\n'))
    } catch {
      return // 忽略坏帧，不让整个流崩掉
    }
    handlers[event]?.(data)
  }

  function abort() {
    abortController?.abort()
  }

  return { send, abort, streaming, connected }
}
