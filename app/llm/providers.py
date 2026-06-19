"""Разрешение credentials для primary / fallback (Ollama | DeepSeek API)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from openai import AsyncOpenAI

from app.config import Settings

ProviderKind = Literal["primary", "fallback"]
FallbackBackend = Literal["ollama", "deepseek"]

DEEPSEEK_DEFAULT_BASE_URL = "https://api.deepseek.com/v1"
DEEPSEEK_DEFAULT_MODEL = "deepseek-chat"


@dataclass(frozen=True)
class LlmCredentials:
    api_key: str
    base_url: str
    model: str
    backend: FallbackBackend | Literal["primary"]


def resolve_llm_credentials(
    settings: Settings,
    provider: ProviderKind,
    *,
    fallback_backend: FallbackBackend | None = None,
) -> LlmCredentials:
    if provider == "primary":
        api_key = settings.openai_api_key
        if not api_key:
            raise ValueError(
                "OPENAI_API_KEY не задан. Скопируйте .env.example в .env и укажите ключ."
            )
        return LlmCredentials(
            api_key=api_key,
            base_url=settings.openai_base_url or "https://api.openai.com/v1",
            model=settings.model,
            backend="primary",
        )

    backend = fallback_backend or settings.fallback_backend
    if backend == "deepseek":
        api_key = settings.deepseek_api_key
        if not api_key:
            raise ValueError(
                "DeepSeek не настроен. Укажите DEEPSEEK_API_KEY в .env "
                "(ключ: https://platform.deepseek.com)."
            )
        return LlmCredentials(
            api_key=api_key,
            base_url=settings.deepseek_base_url or DEEPSEEK_DEFAULT_BASE_URL,
            model=settings.deepseek_model or DEEPSEEK_DEFAULT_MODEL,
            backend="deepseek",
        )

    api_key = settings.fallback_api_key
    base_url = settings.fallback_base_url
    if not api_key or not base_url:
        raise ValueError(
            "Ollama не настроена. Укажите FALLBACK_API_KEY и FALLBACK_BASE_URL в .env "
            "(например: http://localhost:11434/v1)."
        )
    return LlmCredentials(
        api_key=api_key,
        base_url=base_url,
        model=settings.fallback_model,
        backend="ollama",
    )


def create_async_openai_client(
    settings: Settings,
    creds: LlmCredentials,
    *,
    timeout: float | None = None,
    max_retries: int | None = None,
) -> AsyncOpenAI:
    """OpenAI-compatible AsyncOpenAI для primary / Ollama / DeepSeek."""
    return AsyncOpenAI(
        api_key=creds.api_key,
        base_url=creds.base_url,
        timeout=timeout if timeout is not None else settings.llm_sdk_timeout,
        max_retries=max_retries if max_retries is not None else settings.llm_max_retries,
    )
