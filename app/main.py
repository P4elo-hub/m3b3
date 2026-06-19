"""FastAPI-приложение: SSE streaming и health."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, Request
from sse_starlette.sse import EventSourceResponse

from app.config import Settings
from app.llm import ToolCallClient
from app.schemas.chat import StreamChatRequest

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = Settings()
    client = ToolCallClient(settings=settings, provider="primary")
    app.state.llm_client = client
    logger.info(
        "ToolCallClient ready backend=%s model=%s fallback=%s",
        client.backend,
        client.model,
        settings.fallback_backend,
    )
    try:
        yield
    finally:
        await client.aclose()


app = FastAPI(
    title="DocIntel LLM API",
    description="Async LLM client with SSE streaming",
    version="0.2.0",
    lifespan=lifespan,
)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/chat/stream")
async def chat_stream(body: StreamChatRequest, request: Request) -> EventSourceResponse:
    """SSE-стрим ответа LLM: curl -N -X POST .../chat/stream -d '{"prompt":"..."}'."""

    client: ToolCallClient = request.app.state.llm_client

    async def event_generator() -> Any:
        try:
            async for delta in client.stream_chat(body.prompt, model=body.model):
                if await request.is_disconnected():
                    logger.info("SSE client disconnected")
                    break
                yield {"event": "message", "data": delta}
            yield {"event": "done", "data": "[DONE]"}
        except Exception as exc:
            logger.exception("stream_chat failed")
            yield {"event": "error", "data": str(exc)}

    return EventSourceResponse(
        event_generator(),
        ping=15,
        headers={"X-Accel-Buffering": "no", "Cache-Control": "no-cache"},
    )
