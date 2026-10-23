/**
 * 浏览器端模拟流引擎（离线 Demo 模式）。
 *
 * 后端不可达时（GitHub Pages / 后端未启动），在浏览器内重放与
 * FastAPI 后端完全同构的 SSE 事件序列：meta → step_start → thought_delta
 * → action_start → observation → answer_delta → usage → done。
 * 事件协议与 backend/agent/loop.py 一致，前端渲染路径零分叉。
 */

const ORDERS = {
  SO20261001: {
    order_id: 'SO20261001',
    product: 'Teng Buds Pro 3 真无线耳机',
    amount: 599.0,
    status: '已发货',
    pay_time: '2026-10-18 21:34',
    tracks: [
      { time: '10-19 09:12', node: '深圳分拨中心，已发出' },
      { time: '10-19 23:40', node: '广州转运中心，运输中' },
      { time: '10-20 14:05', node: '到达武汉江汉区网点' },
    ],
  },
  SO20261002: {
    order_id: 'SO20261002',
    product: 'Teng Phone 15 Ultra 手机壳（磨砂黑）',
    amount: 69.0,
    status: '已完成',
    pay_time: '2026-10-10 10:02',
    tracks: [{ time: '10-11 08:30', node: '已签收，签收人：本人' }],
  },
  SO20261003: {
    order_id: 'SO20261003',
    product: 'Teng Watch S4 智能手表',
    amount: 1299.0,
    status: '待付款',
    pay_time: null,
    tracks: [],
  },
}

const PRODUCTS = [
  { name: 'Teng Buds Pro 3', category: '耳机', price: 599, stock: 128, rating: 4.8 },
  { name: 'Teng Buds Air', category: '耳机', price: 299, stock: 340, rating: 4.5 },
  { name: 'Teng Phone 15 Ultra', category: '手机', price: 4999, stock: 56, rating: 4.9 },
  { name: 'Teng Phone 15', category: '手机', price: 3299, stock: 200, rating: 4.7 },
  { name: 'Teng Watch S4', category: '手表', price: 1299, stock: 89, rating: 4.6 },
  { name: 'Teng Pad Air 11', category: '平板', price: 1899, stock: 0, rating: 4.4 },
]

const sleep = (ms) => new Promise((r) => setTimeout(r, ms))
const est = (t) => Math.max(1, Math.ceil((t.match(/[一-鿿]/g) || []).length + (t.length - (t.match(/[一-鿿]/g) || []).length) / 4))

function findOrderId(text) {
  const m = text.match(/SO\d{6,}/i)
  return m ? m[0].toUpperCase() : null
}

function buildPlan(message) {
  const oid = findOrderId(message)
  if ((/退款|退货|退多少/.test(message)) && oid) {
    return { steps: ['query_order', 'calculate_refund'], answer: 'refund', oid }
  }
  if (/物流|快递|到哪|发货/.test(message) && oid) {
    return { steps: ['query_order', 'query_logistics'], answer: 'logistics', oid }
  }
  if (oid) return { steps: ['query_order'], answer: 'order', oid }
  if (/推荐|买|哪个好|什么好|优惠/.test(message)) {
    const steps = ['search_products']
    if (/库存|有货/.test(message)) steps.push('get_inventory')
    return { steps, answer: 'products', oid: null }
  }
  return { steps: [], answer: 'general', oid: null }
}

function execTool(name, args, results) {
  switch (name) {
    case 'query_order': {
      const o = ORDERS[args.order_id]
      return o
        ? { order_id: o.order_id, product: o.product, amount: o.amount, status: o.status, pay_time: o.pay_time }
        : { error: `未找到订单 ${args.order_id}，请确认单号是否正确` }
    }
    case 'query_logistics': {
      const o = ORDERS[args.order_id]
      if (!o) return { error: `未找到订单 ${args.order_id}` }
      return o.tracks.length
        ? { order_id: args.order_id, status: o.status, tracks: o.tracks }
        : { order_id: args.order_id, status: o.status, tracks: [], note: '暂无物流信息' }
    }
    case 'search_products': {
      let r = PRODUCTS
      if (args.category) r = r.filter((p) => p.category === args.category)
      if (args.keyword) r = r.filter((p) => p.name.includes(args.keyword) || p.category.includes(args.keyword))
      return r.slice(0, 5)
    }
    case 'get_inventory': {
      const p = PRODUCTS.find((x) => x.name.includes(args.product_name))
      return p
        ? { product: p.name, stock: p.stock, available: p.stock > 0 }
        : { error: `未找到商品 ${args.product_name}` }
    }
    case 'calculate_refund': {
      const o = ORDERS[args.order_id]
      if (!o) return { error: `未找到订单 ${args.order_id}` }
      if (o.status === '待付款') return { refundable: 0.0, note: '订单未付款，无需退款' }
      const note =
        o.status === '已发货' ? '已发货但未签收，可拦截退款' : '签收 7 天内，无理由全额退款'
      return { order_id: args.order_id, order_amount: o.amount, refund_amount: o.amount, policy_note: note, reason: args.reason }
    }
    default:
      return { error: `未知工具: ${name}` }
  }
}

function renderAnswer(kind, results) {
  const byTool = Object.fromEntries(results.map((r) => [r.tool, r.result]))
  if (kind === 'refund') {
    const r = byTool.calculate_refund || {}
    if (r.error) return `抱歉，${r.error}。请提供正确的订单号，我再帮你查询。`
    const o = byTool.query_order || {}
    return (
      `关于订单 **${r.order_id}**（${o.product || '未知商品'}）的退款：\n\n` +
      `- 订单金额：¥${r.order_amount}\n- **可退金额：¥${r.refund_amount}**\n- 政策依据：${r.policy_note}\n\n` +
      `如确认退款，可在「我的订单」中发起申请，款项将原路退回。还有其他问题吗？`
    )
  }
  if (kind === 'logistics') {
    const lg = byTool.query_logistics || {}
    if (lg.error) return `抱歉，${lg.error}。请确认单号后我再帮你查。`
    if (!lg.tracks?.length) return `订单 ${lg.order_id} 当前状态为「${lg.status}」，暂无物流信息。`
    const lines = lg.tracks.map((t) => `- \`${t.time}\` ${t.node}`).join('\n')
    return `订单 **${lg.order_id}** 当前状态：**${lg.status}**，最新物流轨迹：\n\n${lines}\n\n预计 1-2 天内送达，请保持电话畅通。`
  }
  if (kind === 'order') {
    const o = byTool.query_order || {}
    if (o.error) return `抱歉，${o.error}。请提供正确的订单号，我再帮你查询。`
    return (
      `查到了，订单 **${o.order_id}** 的信息如下：\n\n` +
      `- 商品：${o.product}\n- 金额：¥${o.amount}\n- 状态：**${o.status}**\n- 支付时间：${o.pay_time || '未支付'}\n\n` +
      `需要我进一步查询物流或退款政策吗？`
    )
  }
  if (kind === 'products') {
    const items = byTool.search_products || []
    if (!items.length) return '暂时没有找到匹配的商品，换个关键词试试？比如「耳机」「手机」。'
    const rows = items
      .map((p) => `| ${p.name} | ¥${p.price} | ${p.stock > 0 ? '有货' : '缺货'} | ${p.rating} |`)
      .join('\n')
    let note = ''
    const inv = byTool.get_inventory
    if (inv && inv.stock !== undefined) note = `\n另外，${inv.product} 当前库存 ${inv.stock} 件，可以直接下单。`
    return (
      '为你挑选了几款热门商品：\n\n| 商品 | 价格 | 库存 | 评分 |\n| --- | --- | --- | --- |\n' +
      `${rows}\n\n点击商品可查看详情与优惠券。${note}`
    )
  }
  return (
    '你好，我是 TengMall 智能客服。我可以帮你：\n\n' +
    '- 查询订单与物流进度（试试发「查一下订单 SO20261001 的物流」）\n' +
    '- 计算退款金额（「订单 SO20261001 能退多少」）\n' +
    '- 推荐商品（「推荐一款耳机」）\n\n有什么可以帮你？'
  )
}

async function emitThought(emit, step, text) {
  for (let i = 0; i < text.length; i += 3) {
    await emit('thought_delta', { step, text: text.slice(i, i + 3) })
    await sleep(14)
  }
  await emit('thought_done', { step, text })
}

async function emitAnswer(emit, text) {
  await emit('answer_start', { step: 999 })
  for (let i = 0; i < text.length; i += 3) {
    await emit('answer_delta', { text: text.slice(i, i + 3) })
    await sleep(12)
  }
  await emit('answer_done', { text })
}

/** 与后端 run_agent 同构的事件序列 */
export async function runLocalChat(message, emit) {
  const t0 = performance.now()
  const plan = buildPlan(message)
  await emit('meta', { model: 'browser-demo-rules', mode: 'local', max_steps: 6 })

  const results = []
  const toolThoughts = {
    query_order: '用户提供了订单号，先查询订单基本信息。',
    query_logistics: '已拿到订单状态，继续查询详细物流轨迹。',
    calculate_refund: '根据订单状态匹配退款政策，计算可退金额。',
    search_products: '用户想要选购商品，按条件搜索在售商品。',
    get_inventory: '用户关心是否有货，查询库存。',
  }
  const toolArgs = (name) => {
    switch (name) {
      case 'query_order':
      case 'query_logistics':
        return { order_id: plan.oid }
      case 'calculate_refund':
        return { order_id: plan.oid, reason: '用户申请退款' }
      case 'search_products': {
        const cat = ['手机', '耳机', '手表', '平板'].find((c) => message.includes(c)) || ''
        return { category: cat }
      }
      default:
        return { product_name: 'Teng Buds Pro 3' }
    }
  }

  let step = 0
  for (const tool of plan.steps) {
    step += 1
    await emit('step_start', { step })
    await emitThought(emit, step, toolThoughts[tool] || '调用工具获取数据。')
    const args = toolArgs(tool)
    await emit('action_start', { step, action: tool, args })
    const start = performance.now()
    await sleep(300 + Math.random() * 350) // 模拟工具耗时
    const result = execTool(tool, args, results)
    const duration = Math.round(performance.now() - start)
    const obs = { step, tool, args, result, duration_ms: duration }
    results.push(obs)
    await emit('observation', obs)
  }

  step += 1
  await emit('step_start', { step })
  await emitThought(emit, step, results.length ? '信息已齐全，整理后直接回答用户。' : '意图识别完成，直接回答用户。')
  const answer = renderAnswer(plan.answer, results)
  await emitAnswer(emit, answer)

  const prompt = results.reduce((a, r) => a + JSON.stringify(r.result).length, 0)
  const completion = answer.length + step * 40
  await emit('usage', {
    prompt_tokens: est('x'.repeat(Math.round(prompt / 3))),
    completion_tokens: est(answer),
    total_tokens: est(answer) + est('x'.repeat(Math.round(prompt / 3))),
    latency_ms: Math.round(performance.now() - t0),
    steps: step,
  })
  await emit('done', {})
}
