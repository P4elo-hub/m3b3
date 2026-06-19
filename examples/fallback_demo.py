"""Общая логика демо fallback (Ollama / DeepSeek API)."""

from __future__ import annotations

import sys

from openai import (
    APIConnectionError,
    APITimeoutError,
    APIStatusError,
    AuthenticationError,
    BadRequestError,
    PermissionDeniedError,
)

from app.config import Settings
from app.llm import ToolCallClient
from app.llm.providers import FallbackBackend
from demo_common import FEATURE_BRIEF, FEATURE_NAME, FEATURE_PROTOCOL, save_answer


def run_sectioned_fallback_demo(*, backend: FallbackBackend, answer_suffix: str) -> int:
    settings = Settings()
    client = ToolCallClient(provider="fallback", fallback_backend=backend)
    backend_label = "Ollama (локально)" if backend == "ollama" else "DeepSeek API"

    print(
        f"=== {client.settings.service_name} — документация фичи "
        f"(sectioned / fallback / {backend_label}) ===\n"
    )
    print(f"Backend: {backend}")
    print(f"Модель: {client._model}")
    if backend == "ollama":
        print(f"Base URL: {settings.fallback_base_url}\n")
    else:
        print(f"Base URL: {settings.deepseek_base_url or 'https://api.deepseek.com/v1'}\n")

    print(f"Запрос:\n{FEATURE_BRIEF}\n")
    print(
        f"Таймаут: {settings.request_timeout_seconds}s на секцию\n"
        "Режим: kit-tool → секция → склейка (несколько LLM-вызовов)\n"
    )
    if backend == "ollama":
        print(
            "Убедитесь, что Ollama запущена и модель скачана:\n"
            "  ollama serve && ollama pull qwen2.5:7b\n"
            "Cloud-модели (:cloud) требуют подписку Ollama Pro.\n"
        )
    else:
        print(
            "Нужен ключ DEEPSEEK_API_KEY (platform.deepseek.com).\n"
            "Оплата по токенам; у новых аккаунтов часто есть стартовые credits.\n"
        )
    print(
        "При таймаутах увеличьте SUPPORT_TIMEOUT_SECONDS в .env (например, 300).\n"
        "---"
    )

    result = client.chat_sectioned_json(
        FEATURE_BRIEF,
        feature_name=FEATURE_NAME,
        protocol=FEATURE_PROTOCOL,
    )
    output_path = save_answer(result, suffix=answer_suffix)

    print(f"Kit-tools (секций): {result['tool_calls_made']} | Модель: {result['model']}")
    print(f"Сохранено: {output_path}")
    print(f"\nОтвет:\n{result['answer']}\n")
    return 0


def handle_fallback_demo_errors(error: BaseException, *, backend: str) -> int:
    if isinstance(error, ValueError):
        print(error, file=sys.stderr)
        return 1
    if isinstance(error, AuthenticationError):
        if backend == "deepseek":
            print(
                "DeepSeek отклонил API-ключ. Проверьте DEEPSEEK_API_KEY в .env "
                "и баланс на platform.deepseek.com.",
                file=sys.stderr,
            )
        else:
            print("Ошибка авторизации fallback API.", file=sys.stderr)
        return 1
    if isinstance(error, APIConnectionError):
        if backend == "deepseek":
            print(
                "Не удалось подключиться к DeepSeek API. Проверьте интернет и DEEPSEEK_BASE_URL.",
                file=sys.stderr,
            )
        else:
            print(
                "Не удалось подключиться к Ollama. Запустите сервер:\n  ollama serve",
                file=sys.stderr,
            )
        return 1
    if isinstance(error, BadRequestError) and "does not support tools" in str(error):
        model = Settings().fallback_model
        print(
            f"Модель {model!r} не поддерживает tool calling.\n"
            "Скачайте модель с поддержкой tools:\n"
            "  ollama pull qwen2.5:7b",
            file=sys.stderr,
        )
        return 1
    if isinstance(error, PermissionDeniedError) and (
        "requires a subscription" in str(error) or "upgrade" in str(error)
    ):
        model = Settings().fallback_model
        print(
            f"Модель {model!r} доступна только по подписке Ollama Pro.\n"
            "Варианты:\n"
            "  1. Подписка: https://ollama.com/upgrade\n"
            "  2. Локальная модель: FALLBACK_BACKEND=ollama, FALLBACK_MODEL=qwen2.5:7b\n"
            "  3. DeepSeek API: python examples/run_tool_call_deepseek.py + DEEPSEEK_API_KEY",
            file=sys.stderr,
        )
        return 1
    if isinstance(error, APIStatusError) and (
        error.status_code == 402 or "Insufficient Balance" in str(error)
    ):
        print(
            "На аккаунте DeepSeek недостаточно баланса (402 Insufficient Balance).\n"
            "Пополните баланс: https://platform.deepseek.com/top_up\n"
            "Или проверьте granted/topped-up balance в личном кабинете.\n"
            "Sectioned-режим делает 6+ запросов — нужен положительный баланс.",
            file=sys.stderr,
        )
        return 1
    if isinstance(error, APITimeoutError):
        print(
            "Запрос к LLM не уложился в таймаут. "
            "Увеличьте SUPPORT_TIMEOUT_SECONDS в .env.",
            file=sys.stderr,
        )
        return 1
    raise error
