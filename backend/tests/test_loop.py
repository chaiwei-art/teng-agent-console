"""ReAct 循环与模型输出解析测试。"""
import asyncio
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from agent.loop import MockLLM, parse_react_text, run_agent  # noqa: E402


# ---------------- parse_react_text：真实模型输出格式兼容 ----------------

def test_parse_bold_action():
    text = "**Thought**: 需要查物流\n**Action**: query_logistics\n**Action Input**: {\"order_id\": \"SO20261001\"}"
    d = parse_react_text(text)
    assert d["type"] == "action"
    assert d["action"] == "query_logistics"
    assert d["args"]["order_id"] == "SO20261001"
    assert "需要查物流" in d["thought"]
    assert "Action" not in d["thought"]  # Thought 不吞掉后续段


def test_parse_bold_answer():
    text = "**Thought**: 信息足够了\n**Answer**: 订单已发货，预计明天到达。"
    d = parse_react_text(text)
    assert d["type"] == "answer"
    assert d["text"] == "订单已发货，预计明天到达。"
    assert "信息足够了" in d["thought"]


def test_parse_plain_answer():
    text = "Thought: 已获取数据\n\nAnswer: 结果如下。"
    d = parse_react_text(text)
    assert d["type"] == "answer"
    assert d["text"] == "结果如下。"


def test_parse_missing_answer_label_strips_thought_line():
    """回归用例：模型不输出 Answer 标签时，回答区不能重复展示 Thought 行。"""
    text = "Thought: 物流轨迹已获取，信息完整，直接答复用户。\n\n订单 SO20261001 已发货，轨迹见下。"
    d = parse_react_text(text)
    assert d["type"] == "answer"
    assert not d["text"].startswith("Thought")
    assert "订单 SO20261001 已发货" in d["text"]


def test_parse_unknown_tool_falls_to_answer():
    text = "Thought: 试试\nAction: drop_database"
    d = parse_react_text(text)
    assert d["type"] == "answer"  # 未知工具不当作 action 执行


def test_parse_action_input_invalid_json_keeps_no_args():
    text = "Thought: 查\nAction: query_order\nAction Input: {broken"
    d = parse_react_text(text)
    if d["type"] == "action":
        assert d["args"] == {}


# ---------------- MockLLM 计划 ----------------

def test_mock_plan_refund_flow():
    m = MockLLM()
    m.plan("订单 SO20261001 能退多少")
    first = m.next_step([])
    assert first["type"] == "action"
    assert first["action"] == "query_order"


def test_mock_plan_default_greeting():
    m = MockLLM()
    m.plan("你好")
    d = m.next_step([])
    assert d["type"] == "answer"


# ---------------- run_agent 全链路（Mock 模式，无网络） ----------------

def _collect_run(message, monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    events = []

    async def emit(event, data):
        events.append((event, data))

    history = []
    asyncio.run(run_agent(message, history, emit))
    return events, history


def test_run_agent_logistics_sequence(monkeypatch):
    events, history = _collect_run("查一下订单 SO20261001 的物流", monkeypatch)
    names = [e for e, _ in events]
    assert names[0] == "meta"
    assert "fallback" not in names  # Mock 模式不应有降级事件
    assert "step_start" in names
    assert "action_start" in names
    assert "observation" in names
    # run_agent 以 usage 收尾（done 事件由 server 层追加，见 test_server）
    assert names[-1] == "usage"
    # 事件顺序：thought 必须在 action 之前
    assert names.index("thought_done") < names.index("action_start")
    # 工具结果确实进入 history
    assert any("query_order" in str(m.get("content", "")) for m in history)


def test_run_agent_answer_comes_last(monkeypatch):
    events, _ = _collect_run("推荐一款耳机", monkeypatch)
    names = [e for e, _ in events]
    assert "answer_done" in names
    assert names.index("answer_done") < names.index("usage")
    answer = next(d for e, d in events if e == "answer_done")
    assert "Teng" in answer["text"]


def test_run_agent_usage_shape(monkeypatch):
    events, _ = _collect_run("订单 SO20261001 能退多少", monkeypatch)
    usage = next(d for e, d in events if e == "usage")
    assert set(usage) >= {"prompt_tokens", "completion_tokens", "total_tokens", "latency_ms", "steps"}
    assert usage["total_tokens"] > 0
