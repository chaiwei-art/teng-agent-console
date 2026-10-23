"""ReAct Agent 循环。

- MockLLM：无需 API Key，基于规则规划工具调用序列，让 demo 完整跑通
- OpenAI-compatible LLM：设置 OPENAI_API_KEY（可选 OPENAI_BASE_URL / AGENT_MODEL）即可切换真实模型

Agent 以 async generator 的形式产出事件，方便直接对接 SSE 流式输出。
"""
from __future__ import annotations

import json
import os
import re
import time
from typing import Any, AsyncGenerator, Dict, List, Optional

from .tools import TOOL_SPECS, execute_tool

MAX_STEPS = 6

SYSTEM_PROMPT = """你是"TengMall"商城的智能客服助手。请使用 ReAct 模式回答：
先输出 Thought（思考），再决定调用工具（Action + JSON 参数），观察结果（Observation）后继续，
信息足够时直接给出最终 Answer。

可用工具：
{tools}

严格按格式输出，JSON 参数用单行。"""

# ---------------------------------------------------------------- 事件工具

def _estimate_tokens(text: str) -> int:
    """粗略 token 估算：中文约 1 字/token，英文约 4 字符/token。"""
    cn = len(re.findall(r"[一-鿿]", text))
    other = len(text) - cn
    return max(1, cn + other // 4)


def _tool_prompt() -> str:
    lines = []
    for spec in TOOL_SPECS:
        params = ", ".join(spec["parameters"].keys())
        lines.append(f"- {spec['name']}({params}): {spec['description']}")
    return "\n".join(lines)


# ---------------------------------------------------------------- Mock LLM

class MockLLM:
    """规则版"大脑"：根据用户消息规划 (thought, action, args) 序列。

    不是黑盒——每一步都真实调用 tools.execute_tool，只有决策是脚本化的。
    """

    def __init__(self) -> None:
        self._plans: List[Dict[str, Any]] = []
        self._answers: List[str] = []

    @staticmethod
    def _find_order_id(text: str) -> Optional[str]:
        m = re.search(r"SO\d{6,}", text, re.IGNORECASE)
        return m.group(0).upper() if m else None

    def plan(self, user_message: str) -> None:
        """根据用户消息生成本轮的工具调用计划与最终回答。"""
        self._plans, self._answers = [], []
        msg = user_message.strip()
        oid = self._find_order_id(msg)

        if any(k in msg for k in ("退款", "退货", "退多少")) and oid:
            self._plans = [
                ("正在识别用户的订单号，先查询订单当前状态", "query_order", {"order_id": oid}),
                ("已拿到订单状态，接下来根据退款政策计算可退金额", "calculate_refund",
                 {"order_id": oid, "reason": "用户申请退款"}),
            ]
            self._answers.append("__REFUND__")
        elif any(k in msg for k in ("物流", "快递", "到哪", "发货")) and oid:
            self._plans = [
                ("用户想了解配送进度，先确认订单存在及其状态", "query_order", {"order_id": oid}),
                ("订单存在，继续查询详细物流轨迹", "query_logistics", {"order_id": oid}),
            ]
            self._answers.append("__LOGISTICS__")
        elif oid:
            self._plans = [("用户提供了订单号但未说明意图，先查询订单基本信息", "query_order", {"order_id": oid})]
            self._answers.append("__ORDER__")
        elif any(k in msg for k in ("推荐", "买", "哪个好", "什么好", "优惠")):
            cat = ""
            for c in ("手机", "耳机", "手表", "平板"):
                if c in msg:
                    cat = c
                    break
            self._plans = [("用户想要选购商品，按品类搜索在售商品", "search_products", {"category": cat})]
            if "库存" in msg or "有货" in msg:
                self._plans.append(("用户关心是否有货，查询库存", "get_inventory", {"product_name": "Teng Buds Pro 3"}))
            self._answers.append("__PRODUCT__")
        else:
            self._answers.append("__GENERAL__")

    def next_step(self, observations: List[Dict[str, Any]]) -> Dict[str, Any]:
        """返回下一步：{'type':'action', ...} 或 {'type':'answer', 'text': ...}。"""
        if self._plans:
            thought, action, args = self._plans.pop(0)
            return {"type": "action", "thought": thought, "action": action, "args": args}
        text = self._render_answer(observations)
        return {"type": "answer", "text": text}

    @staticmethod
    def _render_answer(observations: List[Dict[str, Any]]) -> str:
        by_tool = {o["tool"]: o["result"] for o in observations}
        if "__REFUND__" in by_tool or "calculate_refund" in by_tool:
            r = by_tool.get("calculate_refund", {})
            if "error" in r:
                return f"抱歉，{r['error']}。请提供正确的订单号，我再帮你查询。"
            o = by_tool.get("query_order", {})
            return (
                f"关于订单 **{r.get('order_id', '')}**（{o.get('product', '未知商品')}）的退款：\n\n"
                f"- 订单金额：¥{r.get('order_amount')}\n"
                f"- **可退金额：¥{r.get('refund_amount')}**\n"
                f"- 政策依据：{r.get('policy_note')}\n\n"
                f"如确认退款，可在「我的订单」中发起申请，款项将原路退回。还有其他问题吗？"
            )
        if "query_logistics" in by_tool:
            lg = by_tool.get("query_logistics", {})
            if "error" in lg:
                return f"抱歉，{lg['error']}。请确认单号后我再帮你查。"
            tracks = lg.get("tracks", [])
            if not tracks:
                return f"订单 {lg.get('order_id')} 当前状态为「{lg.get('status')}」，暂无物流信息。"
            lines = "\n".join(f"- `{t['time']}` {t['node']}" for t in tracks)
            return (
                f"订单 **{lg.get('order_id')}** 当前状态：**{lg.get('status')}**，最新物流轨迹：\n\n{lines}\n\n"
                f"预计 1-2 天内送达，请保持电话畅通。"
            )
        if "query_order" in by_tool:
            o = by_tool.get("query_order", {})
            if "error" in o:
                return f"抱歉，{o['error']}。请提供正确的订单号，我再帮你查询。"
            pay = o.get("pay_time") or "未支付"
            return (
                f"查到了，订单 **{o['order_id']}** 的信息如下：\n\n"
                f"- 商品：{o['product']}\n- 金额：¥{o['amount']}\n"
                f"- 状态：**{o['status']}**\n- 支付时间：{pay}\n\n需要我进一步查询物流或退款政策吗？"
            )
        if "search_products" in by_tool:
            items = by_tool.get("search_products", [])
            if not items:
                return "暂时没有找到匹配的商品，换个关键词试试？比如「耳机」「手机」。"
            rows = "\n".join(
                f"| {p['name']} | ¥{p['price']} | {'有货' if p['stock'] > 0 else '缺货'} | {p['rating']} |"
                for p in items
            )
            stock_note = ""
            inv = by_tool.get("get_inventory")
            if inv and "stock" in inv:
                stock_note = f"\n另外，{inv['product']} 当前库存 {inv['stock']} 件，可以直接下单。"
            return (
                "为你挑选了几款热门商品：\n\n"
                "| 商品 | 价格 | 库存 | 评分 |\n| --- | --- | --- | --- |\n"
                f"{rows}\n\n点击商品可查看详情与优惠券。{stock_note}"
            )
        return (
            "你好，我是 TengMall 智能客服。我可以帮你：\n\n"
            "- 查询订单与物流进度（试试发「查一下订单 SO20261001 的物流」）\n"
            "- 计算退款金额（「订单 SO20261001 能退多少」）\n"
            "- 推荐商品（「推荐一款耳机」）\n\n有什么可以帮你？"
        )


# ---------------------------------------------------------------- ReAct 循环

async def run_agent(
    user_message: str,
    history: List[Dict[str, Any]],
    emit: Any,
) -> None:
    """执行一轮 ReAct 循环，通过 emit(event, data) 推送 SSE 事件。"""
    use_real = bool(os.getenv("OPENAI_API_KEY"))
    mock = MockLLM()
    mock.plan(user_message)

    model_name = os.getenv("AGENT_MODEL", "gpt-4o-mini" if use_real else "mock-rules-v1")
    await emit("meta", {"model": model_name, "mode": "real" if use_real else "mock", "max_steps": MAX_STEPS})

    total_prompt_tokens = 0
    total_completion_tokens = 0
    observations: List[Dict[str, Any]] = []
    t_start = time.perf_counter()

    for step in range(1, MAX_STEPS + 1):
        await emit("step_start", {"step": step})

        if use_real:
            try:
                decision = await _real_llm_step(user_message, history, observations, emit)
            except Exception as exc:  # noqa: BLE001 - 真实 LLM 失败时优雅降级到 Mock，保证 demo 可用
                await emit("fallback", {
                    "reason": f"{type(exc).__name__}: {exc}",
                    "to": "mock-rules-v1",
                })
                use_real = False
                decision = mock.next_step(observations)
        else:
            decision = mock.next_step(observations)

        # Thought（流式逐 token 推送）
        thought = decision.get("thought") or ("我来整理已有信息，直接回答用户。" if decision["type"] == "answer" else "")
        thought_tokens = _split_tokens(thought)
        for tk in thought_tokens:
            await emit("thought_delta", {"step": step, "text": tk})
            time.sleep(0)  # 让出事件循环
        await emit("thought_done", {"step": step, "text": thought})
        total_completion_tokens += _estimate_tokens(thought)

        if decision["type"] == "action":
            action, args = decision["action"], decision["args"]
            await emit("action_start", {"step": step, "action": action, "args": args})
            t0 = time.perf_counter()
            result = execute_tool(action, args)
            duration_ms = int((time.perf_counter() - t0) * 1000)
            obs = {"step": step, "tool": action, "args": args, "result": result, "duration_ms": duration_ms}
            observations.append(obs)
            history.append({"role": "assistant", "content": f"Action: {action} {json.dumps(args, ensure_ascii=False)}"})
            history.append({"role": "user", "content": f"Observation: {json.dumps(result, ensure_ascii=False)}"})
            await emit("observation", obs)
            total_prompt_tokens += _estimate_tokens(json.dumps(result, ensure_ascii=False))
            continue

        # 最终回答：流式推送
        answer = decision.get("text", "")
        await emit("answer_start", {"step": step})
        for tk in _split_tokens(answer):
            await emit("answer_delta", {"text": tk})
        await emit("answer_done", {"text": answer})
        total_completion_tokens += _estimate_tokens(answer)
        history.append({"role": "user", "content": user_message})
        history.append({"role": "assistant", "content": answer})
        break

    latency_ms = int((time.perf_counter() - t_start) * 1000)
    await emit("usage", {
        "prompt_tokens": total_prompt_tokens,
        "completion_tokens": total_completion_tokens,
        "total_tokens": total_prompt_tokens + total_completion_tokens,
        "latency_ms": latency_ms,
        "steps": len(observations) + 1,
    })


def _split_tokens(text: str, chunk: int = 3) -> List[str]:
    """把文本切成小块，模拟 token 级流式输出。"""
    return [text[i:i + chunk] for i in range(0, len(text), chunk)] or [""]


# ---------------------------------------------------------------- 真实 LLM（OpenAI 兼容）

async def _real_llm_step(
    user_message: str,
    history: List[Dict[str, Any]],
    observations: List[Dict[str, Any]],
    emit: Any,
) -> Dict[str, Any]:
    """调用 OpenAI 兼容 API 完成一次 ReAct 决策（非流式，简化实现）。"""
    from openai import AsyncOpenAI

    client = AsyncOpenAI()
    model = os.getenv("AGENT_MODEL", "gpt-4o-mini")
    messages: List[Dict[str, Any]] = [
        {"role": "system", "content": SYSTEM_PROMPT.format(tools=_tool_prompt())}
    ]
    messages += history[-8:]
    messages.append({"role": "user", "content": user_message})
    for o in observations:
        messages.append({"role": "assistant", "content": f"Action: {o['tool']} {json.dumps(o['args'], ensure_ascii=False)}"})
        messages.append({"role": "user", "content": f"Observation: {json.dumps(o['result'], ensure_ascii=False)}"})

    resp = await client.chat.completions.create(model=model, messages=messages, temperature=0.2)
    text = resp.choices[0].message.content or ""

    # 兼容模型输出的粗体标签（**Thought**:）与纯文本（Thought:）两种风格
    m = re.search(r"\*{0,2}Action\*{0,2}[:：]\s*(\w+)\s*(\{.*?\})?\s*$", text, re.MULTILINE | re.DOTALL)
    thought_m = re.search(
        r"\*{0,2}Thought\*{0,2}[:：]\s*(.*?)(?=\*{0,2}Action\*{0,2}[:：]|\*{0,2}Answer\*{0,2}[:：]|$)",
        text,
        re.DOTALL | re.MULTILINE,
    )
    thought = thought_m.group(1).strip() if thought_m else text[:200]
    if m and m.group(1) in {s["name"] for s in TOOL_SPECS}:
        args: Dict[str, Any] = {}
        if m.group(2):
            try:
                args = json.loads(m.group(2))
            except json.JSONDecodeError:
                args = {}
        return {"type": "action", "thought": thought, "action": m.group(1), "args": args}
    ans_m = re.search(r"\*{0,2}Answer\*{0,2}[:：]\s*(.*)", text, re.DOTALL)
    return {"type": "answer", "thought": thought, "text": (ans_m.group(1) if ans_m else text).strip()}
