/**
 * SSE 客户端（基于 fetch + ReadableStream）。
 *
 * 为什么不用 EventSource：
 * 1. EventSource 只支持 GET，而对话需要 POST 传 message
 * 2. EventSource 不暴露原始字节流，无法做增量 Markdown 的精细控制
 *
 * 关键点：网络分包是任意的（一个 chunk 可能是半行、也可能跨多个事件），
 * 所以必须维护 buffer，按 \n\n 切帧后再解析 event/data。
 */
import { ref } from 'vue'

/**
 * 解析单帧 SSE 文本并分发（纯函数，便于单测）。
 * 帧格式：event: xxx\ndata: {...}
 * 坏 JSON 帧静默忽略，不让整个流崩掉。
 */
export function dispatchFrame(frame, handlers) {
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
    return
  }
  handlers[event]?.(data)
}

/**
 * 帧重组器：喂入任意切分的网络 chunk，完整帧到达即分发。
 * 这是"跨 chunk 帧缓冲"的核心逻辑（纯函数式，便于单测）。
 */
export function createFrameSplitter(handlers) {
  let buffer = ''
  return {
    push(text) {
      // 换行归一化：兼容 CRLF 帧（含 \r | \n 恰好切在两个 chunk 的情况）
      buffer = (buffer + text).replace(/\r\n/g, '\n')
      let idx
      while ((idx = buffer.indexOf('\n\n')) !== -1) {
        const frame = buffer.slice(0, idx)
        buffer = buffer.slice(idx + 2)
        dispatchFrame(frame, handlers)
      }
    },
    /** 流结束时的残余（不足一帧）——正常情况下应为空 */
    get pending() {
      return buffer
    },
  }
}

/** 后端可用性（页面生命周期内探测一次并缓存） */
let _backendOk = null
async function probeBackend() {
  if (_backendOk !== null) return _backendOk
  try {
    const ctrl = new AbortController()
    const timer = setTimeout(() => ctrl.abort(), 2500)
    const r = await fetch('/api/health', { signal: ctrl.signal })
    clearTimeout(timer)
    _backendOk = r.ok
  } catch {
    _backendOk = false
  }
  return _backendOk
}

export function useAgentStream() {
  const connected = ref(false)
  const streaming = ref(false)
  const localMode = ref(false)
  let abortController = null

  /**
   * @param {string} message 用户消息
   * @param {Record<string, Function>} handlers 事件回调表 event -> fn(data)
   */
  async function send(message, sessionId, handlers) {
    abortController = new AbortController()
    streaming.value = true

    try {
      // 后端不可达（GitHub Pages / 未启动服务）→ 浏览器端同构模拟流
      if (!(await probeBackend())) {
        localMode.value = true
        const { runLocalChat } = await import('../lib/mockStream.js')
        await runLocalChat(message, (event, data) => {
          handlers[event]?.(data)
        })
        return
      }
      localMode.value = false

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
      const splitter = createFrameSplitter(handlers)

      for (;;) {
        const { done, value } = await reader.read()
        if (done) break
        splitter.push(decoder.decode(value, { stream: true }))
      }
      // 收尾残余的 UTF-8 字节
      const tail = decoder.decode()
      if (tail) splitter.push(tail)
    } finally {
      streaming.value = false
    }
  }

  function abort() {
    abortController?.abort()
  }

  return { send, abort, streaming, connected, localMode }
}
