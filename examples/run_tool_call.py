"""Скрипт запуска: пошаговая генерация документации по kit-tools (OpenAI / primary)."""

from __future__ import annotations

import asyncio
import sys

from openai import APITimeoutError

from app.llm import ToolCallClient
from demo_common import (
    FEATURE_BRIEF,
    FEATURE_NAME,
    FEATURE_PROTOCOL,
    close_client,
    ensure_async_tool_call_client,
    save_answer,
)

ANSWER_SUFFIX = "openai"


async def main() -> int:
    ensure_async_tool_call_client()
    client = ToolCallClient(provider="primary")

    print(f"=== {client.settings.service_name} — документация фичи (sectioned / OpenAI) ===\n")
    print(f"Модель: {client.settings.model}\n")
    print(f"Запрос:\n{FEATURE_BRIEF}\n")
    print(
        f"Таймаут: {client.settings.request_timeout_seconds}s на секцию\n"
        "Режим: kit-tool → секция → склейка (несколько LLM-вызовов)\n"
        "Генерация может занять 3–8 минут...\n"
    )
    print("---")

    try:
        result = await client.chat_sectioned_json(
            FEATURE_BRIEF,
            feature_name=FEATURE_NAME,
            protocol=FEATURE_PROTOCOL,
        )
    finally:
        await close_client(client)

    output_path = save_answer(result, suffix=ANSWER_SUFFIX)

    print(f"Tool calls: {result['tool_calls_made']} | Модель: {result['model']}")
    print(f"Сохранено: {output_path}")
    print(f"\nОтвет:\n{result['answer']}\n")

    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(asyncio.run(main()))
    except ValueError as error:
        print(error, file=sys.stderr)
        raise SystemExit(1) from error
    except APITimeoutError as error:
        print(
            "Запрос к LLM не уложился в таймаут. "
            "Увеличьте SUPPORT_TIMEOUT_SECONDS в .env (например, 300) и повторите.",
            file=sys.stderr,
        )
        raise SystemExit(1) from error
