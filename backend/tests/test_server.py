"""FastAPI 端点测试（SSE 流、健康检查、工具清单）。"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient  # noqa: E402

import server  # noqa: E402


@pytest.fixture()
def client(monkeypatch):
    # 测试绝不访问真实网络：强制 Mock 模式
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    server.SESSION_HISTORY.clear()
    return TestClient(server.app)


def test_health(client):
    r = client.get("/api/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


def test_tools_list(client):
    r = client.get("/api/tools")
    assert r.status_code == 200
    names = {t["name"] for t in r.json()["tools"]}
    assert {"query_order", "query_logistics", "calculate_refund"} <= names


def test_chat_sse_stream(client):
    r = client.post(
        "/api/chat",
        json={"message": "查一下订单 SO20261001 的物流", "session_id": "t1"},
    )
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/event-stream")

    body = r.text
    assert "event: meta" in body
    assert "event: step_start" in body
    assert "event: observation" in body
    assert "event: usage" in body
    assert body.rstrip().endswith("event: done\ndata: {}")
    # 每帧格式：event 行 + data 行 + 空行
    assert "event: step_start\ndata:" in body.replace("\r\n", "\n")


def test_chat_session_history_recorded(client):
    client.post("/api/chat", json={"message": "推荐一款耳机", "session_id": "t2"})
    history = server.SESSION_HISTORY.get("t2", [])
    assert any(m["role"] == "assistant" for m in history)


def test_reset_session(client):
    client.post("/api/chat", json={"message": "你好", "session_id": "t3"})
    r = client.delete("/api/session/t3")
    assert r.json() == {"reset": True}
    assert "t3" not in server.SESSION_HISTORY
