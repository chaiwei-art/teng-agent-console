/**
 * SSE 分帧与帧重组测试 —— 对应简历点"手写 SSE 客户端完成网络分包与帧重组"。
 * 网络层的 chunk 切分是任意的：半帧、跨事件、多帧混合都必须正确处理。
 */
import { describe, expect, it } from 'vitest'
import { createFrameSplitter, dispatchFrame } from '../useAgentStream.js'

function collect() {
  const events = []
  const handlers = {
    meta: (d) => events.push(['meta', d]),
    step_start: (d) => events.push(['step_start', d]),
    answer_delta: (d) => events.push(['answer_delta', d]),
    done: (d) => events.push(['done', d]),
    message: (d) => events.push(['message', d]),
  }
  return { events, handlers }
}

describe('dispatchFrame 单帧解析', () => {
  it('解析 event + data 帧', () => {
    const { events, handlers } = collect()
    dispatchFrame('event: step_start\ndata: {"step": 1}', handlers)
    expect(events).toEqual([['step_start', { step: 1 }]])
  })

  it('缺省 event 名为 message', () => {
    const { events, handlers } = collect()
    dispatchFrame('data: {"x":1}', handlers)
    expect(events).toEqual([['message', { x: 1 }]])
  })

  it('坏 JSON 帧被忽略而不抛错', () => {
    const { events, handlers } = collect()
    expect(() => dispatchFrame('event: done\ndata: {broken', handlers)).not.toThrow()
    expect(events).toEqual([])
  })

  it('无 data 行的帧被忽略', () => {
    const { events, handlers } = collect()
    dispatchFrame('event: ping', handlers)
    expect(events).toEqual([])
  })

  it('未注册的事件不抛错', () => {
    expect(() => dispatchFrame('event: unknown\ndata: {}', {})).not.toThrow()
  })

  it('中文内容正确传递', () => {
    const { events, handlers } = collect()
    dispatchFrame('event: answer_delta\ndata: {"text":"物流已发货"}', handlers)
    expect(events[0][1].text).toBe('物流已发货')
  })
})

describe('createFrameSplitter 跨 chunk 帧重组', () => {
  it('完整流一次性到达', () => {
    const { events, handlers } = collect()
    const s = createFrameSplitter(handlers)
    s.push('event: meta\ndata: {"mode":"mock"}\n\nevent: done\ndata: {}\n\n')
    expect(events.map((e) => e[0])).toEqual(['meta', 'done'])
    expect(s.pending).toBe('')
  })

  it('帧被切在任意字节处（半帧缓存到下一轮）', () => {
    const { events, handlers } = collect()
    const s = createFrameSplitter(handlers)
    s.push('event: step_start\nda')
    expect(events).toEqual([]) // 半帧不触发
    s.push('ta: {"step":2}\n')
    expect(events).toEqual([]) // 尚无空行分隔
    s.push('\n')
    expect(events).toEqual([['step_start', { step: 2 }]])
  })

  it('一个 chunk 混着多帧与残帧', () => {
    const { events, handlers } = collect()
    const s = createFrameSplitter(handlers)
    s.push(
      'event: answer_delta\ndata: {"text":"AB"}\n\nevent: answer_delta\ndata: {"text":"CD"}\n\nevent: answer_delta\ndata: {"te',
    )
    expect(events.map((e) => e[1].text)).toEqual(['AB', 'CD'])
    expect(s.pending).toBe('event: answer_delta\ndata: {"te') // 残帧保留
    s.push('xt":"EF"}\n\n')
    expect(events.map((e) => e[1].text)).toEqual(['AB', 'CD', 'EF'])
  })

  it('逐字符喂入也能完整重组（极端分包）', () => {
    const { events, handlers } = collect()
    const s = createFrameSplitter(handlers)
    const raw = 'event: meta\ndata: {"model":"mimo-v2.6-flash"}\n\nevent: done\ndata: {}\n\n'
    for (const ch of raw) s.push(ch)
    expect(events.map((e) => e[0])).toEqual(['meta', 'done'])
    expect(events[0][1].model).toBe('mimo-v2.6-flash')
    expect(s.pending).toBe('')
  })

  it('CRLF 换行的帧也能处理', () => {
    const { events, handlers } = collect()
    const s = createFrameSplitter(handlers)
    // frame 内部行分隔是 \r\n，帧间分隔需 \n\n——与服务端约定一致
    s.push('event: done\r\ndata: {}\r\n\r\n')
    expect(events.map((e) => e[0])).toEqual(['done'])
  })

  it('流结束无残帧（服务端每帧都以空行收尾）', () => {
    const { handlers } = collect()
    const s = createFrameSplitter(handlers)
    s.push('event: meta\ndata: {"mode":"mock"}\n\n')
    expect(s.pending).toBe('')
  })
})
