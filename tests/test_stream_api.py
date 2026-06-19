"""Тесты SSE-эндпоинта /chat/stream."""

from __future__ import annotations

from collections.abc import AsyncIterator
from unittest.mock import patch

import pytest
from httpx import ASGITransport, AsyncClient

from app.llm.client import ToolCallClient
from app.main import app


class FakeStreamClient(ToolCallClient):
    async def stream_chat(self, prompt: str, *, model: str | None = None) -> AsyncIterator[str]:
        yield "Event "
        yield "loop "
        yield "— это механизм asyncio."

    async def aclose(self) -> None:
        return None


@pytest.fixture
def fake_client() -> FakeStreamClient:
    with patch("app.llm.client.create_async_openai_client"):
        return FakeStreamClient(enable_fallback=False)


@pytest.mark.asyncio
async def test_chat_stream_sse(fake_client: FakeStreamClient) -> None:
    app.state.llm_client = fake_client
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        async with client.stream(
            "POST",
            "/chat/stream",
            json={"prompt": "Что такое event loop?"},
        ) as response:
            assert response.status_code == 200
            assert "text/event-stream" in response.headers.get("content-type", "")
            body = ""
            async for chunk in response.aiter_text():
                body += chunk

    assert "Event" in body or "event loop" in body.lower()
    assert "[DONE]" in body or "done" in body.lower()
