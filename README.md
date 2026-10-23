# ⚡ TengAgent Console

**Agent 可视化调试台** — 实时拆解 ReAgent/ReAct 推理链路：Thought 流式推理 → 工具调用 → Observation 观测 → 最终回答，全链路可观测。

> 为 AI 前端开发面试打造的全栈作品：后端 ReAct 循环用 Python 实现，前端可视化从零设计。

![status](https://img.shields.io/badge/status-demo%20ready-brightgreen)
![backend](https://img.shields.io/badge/backend-FastAPI%20%2B%20SSE-blue)
![frontend](https://img.shields.io/badge/frontend-Vue3%20%2B%20Vite-purple)
![deps](https://img.shields.io/badge/runtime%20deps-zero%20UI%20libraries-lightgrey)

## 🎯 为什么做这个

Agent 落地最大的障碍是**黑盒问题**：用户和开发者都不知道它为什么调这个工具、卡在哪一步、花了多少 token。本项目把 Agent 的每次推理过程端到端可视化。

## ✨ 功能

| 面板 | 能力 |
|------|------|
| 💬 对话 | SSE 流式对话，手写增量 Markdown 渲染（代码块未闭合锁定、表格防闪烁） |
| 🧠 链路 | ReAct 时间线：Thought（逐 token 打字机）→ Action（工具名 + 参数）→ Observation（结果 + 耗时） |
| 📊 Token | 每步 prompt/completion token 瀑布图，总耗时统计 |
| 🗂 记忆 | 会话上下文窗口可视化：每条消息 token 占用、保留策略一目了然 |
| 🛟 降级 | 真实 LLM 调用失败时自动回退 Mock 引擎，demo 永不白屏 |

## 🏗 架构

```
┌─────────────────────────────┐        SSE (text/event-stream)        ┌──────────────────────────┐
│  Frontend (Vue3 + Vite)     │ ◄──── step_start / thought_delta ──── │  Backend (FastAPI)       │
│                             │       action_start / observation      │                          │
│  · useAgentStream (手写SSE) │       answer_delta / usage / done     │  · ReAct 循环 (loop.py)  │
│  · StreamMarkdown (增量渲染)│ ───── POST /api/chat ───────────────► │  · 工具注册表 (tools.py) │
│  · StepCard / Timeline      │                                       │  · Mock LLM / OpenAI 兼容│
│  · TokenWaterfall / Memory  │                                       │  · 优雅降级 fallback     │
└─────────────────────────────┘                                       └──────────────────────────┘
```

### 事件协议

后端以 SSE 推送以下事件，前端按事件类型分发：

```
meta          → { model, mode, max_steps }
step_start    → { step }
thought_delta → { step, text }        # 流式逐 token
action_start  → { step, action, args }
observation   → { step, tool, result, duration_ms }
answer_delta  → { text }
usage         → { prompt_tokens, completion_tokens, total_tokens, latency_ms }
fallback      → { reason, to }        # 真实模型失败降级
done          → {}
```

## 🚀 运行

### 后端

```bash
cd backend
python -m venv .venv && .venv\Scripts\pip install -r requirements.txt   # Windows
# source .venv/bin/activate && pip install -r requirements.txt          # macOS/Linux
python -m uvicorn server:app --port 8000
```

### 前端

```bash
cd frontend
npm install
npm run dev        # 开发：http://localhost:5173（已代理 /api → :8000）
npm run build      # 生产构建
```

### 可选：接入真实模型

默认使用 **Mock 规则引擎**（无需任何 Key，工具是真实执行的，只有决策是脚本化的）。如需接入真实 LLM：

```bash
setx OPENAI_API_KEY sk-xxx
setx OPENAI_BASE_URL https://your-proxy/v1   # 可选，OpenAI 兼容网关
setx AGENT_MODEL gpt-4o-mini                  # 可选
```

若真实调用失败，会自动降级为 Mock 并在界面提示，保证演示可用。

## 🧩 内置工具

| 工具 | 说明 |
|------|------|
| `query_order` | 查询订单基本信息 |
| `query_logistics` | 查询物流轨迹 |
| `search_products` | 搜索商品（关键词/品类） |
| `calculate_refund` | 按退款政策计算可退金额 |
| `get_inventory` | 查询库存 |

试试这些问题：

- `查一下订单 SO20261001 的物流`
- `订单 SO20261001 能退多少？`
- `推荐一款耳机`

## 🔧 技术亮点（面试可讲）

1. **手写 SSE 客户端**：基于 `fetch` + `ReadableStream`，维护跨 chunk 的帧缓冲（网络分包可能切在任意字节处），比 `EventSource` 支持 POST 与更精细的流控。
2. **增量 Markdown 渲染**：未闭合 ``` 围栏锁定为 `<pre>` 防止整篇错乱；表格行未写完暂缓渲染，避免逐帧闪烁。
3. **Token 级打字机**：Thought/Answer 按 3 字符分片推送，前端逐片拼接，还原真实模型流式体验。
4. **优雅降级**：真实 LLM 异常时自动回退 Mock 引擎并推送 `fallback` 事件，UI 展示降级横幅——生产级韧性思维。
5. **零 UI 依赖**：图表、时间线、记忆视图全部手写（CSS Grid/Flex + SVG），产物 gzip 后仅 ~35 kB。

## 📁 目录结构

```
teng-agent-console/
├── backend/
│   ├── server.py            # FastAPI + SSE 端点
│   ├── requirements.txt
│   └── agent/
│       ├── loop.py          # ReAct 循环 / Mock LLM / OpenAI 兼容客户端
│       └── tools.py         # 工具注册表 + Mock 商城数据
└── frontend/
    ├── vite.config.js       # dev 代理 /api → :8000
    └── src/
        ├── App.vue          # 主界面（对话 + 观测面板）
        ├── composables/
        │   └── useAgentStream.js   # 手写 SSE 客户端
        └── components/
            ├── StreamMarkdown.vue  # 增量 Markdown 渲染器
            ├── StepCard.vue        # Thought/Action/Observation 卡片
            ├── Timeline.vue        # ReAct 链路时间线
            ├── TokenWaterfall.vue  # Token 瀑布图
            └── MemoryView.vue      # 上下文记忆可视化
```

## License

MIT
