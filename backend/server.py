"""teng-agent-console 后端：FastAPI + SSE 流式输出 ReAct 事件。"""
from __future__ import annotations

import asyncio
import json
from typing import Any, Dict, List

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from agent.loop import run_agent
from agent.tools import TOOL_SPECS

app = FastAPI(title="teng-agent-console", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# 简单的会话内历史（生产环境应换成 Redis/DB）
SESSION_HISTORY: Dict[str, List[Dict[str, Any]]] = {}


class ChatRequest(BaseModel):
    message: str
    session_id: str = "default"


@app.get("/api/health")
async def health() -> Dict[str, str]:
    return {"status": "ok"}


@app.get("/api/tools")
async def tools() -> Dict[str, Any]:
    return {
        "tools": [
            {"name": s["name"], "description": s["description"], "parameters": list(s["parameters"].keys())}
            for s in TOOL_SPECS
        ]
    }


@app.post("/api/chat")
async def chat(req: ChatRequest) -> StreamingResponse:
    history = SESSION_HISTORY.setdefault(req.session_id, [])

    queue: asyncio.Queue = asyncio.Queue()
    done_marker = object()

    async def emit(event: str, data: Dict[str, Any]) -> None:
        queue.put_nowait((event, data))

    async def worker() -> None:
        try:
            await run_agent(req.message, history, emit)
        except Exception as exc:  # noqa: BLE001 - 把错误也推给前端展示
            await emit("error", {"message": f"{type(exc).__name__}: {exc}"})
        finally:
            queue.put_nowait((done_marker, None))

    asyncio.ensure_future(worker())

    async def event_stream():
        while True:
            event, data = await queue.get()
            if event is done_marker:
                yield "event: done\ndata: {}\n\n"
                break
            payload = json.dumps(data, ensure_ascii=False)
            yield f"event: {event}\ndata: {payload}\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.delete("/api/session/{session_id}")
async def reset_session(session_id: str) -> Dict[str, bool]:
    SESSION_HISTORY.pop(session_id, None)
    return {"reset": True}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
