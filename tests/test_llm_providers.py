"""Тесты разрешения credentials для LLM-провайдеров."""

from __future__ import annotations

import pytest

from app.config import Settings
from app.llm.providers import resolve_llm_credentials


def test_resolve_primary_credentials() -> None:
    settings = Settings(
        OPENAI_API_KEY="sk-test",
        SUPPORT_PRIMARY_MODEL="gpt-4o-mini",
    )
    creds = resolve_llm_credentials(settings, "primary")
    assert creds.backend == "primary"
    assert creds.model == "gpt-4o-mini"
    assert creds.api_key == "sk-test"


def test_resolve_ollama_fallback() -> None:
    settings = Settings(
        FALLBACK_BACKEND="ollama",
        FALLBACK_API_KEY="ollama",
        FALLBACK_BASE_URL="http://localhost:11434/v1",
        FALLBACK_MODEL="qwen2.5:7b",
    )
    creds = resolve_llm_credentials(settings, "fallback")
    assert creds.backend == "ollama"
    assert creds.model == "qwen2.5:7b"
    assert creds.base_url == "http://localhost:11434/v1"


def test_resolve_deepseek_fallback() -> None:
    settings = Settings(
        FALLBACK_BACKEND="deepseek",
        DEEPSEEK_API_KEY="sk-ds-test",
        DEEPSEEK_MODEL="deepseek-chat",
    )
    creds = resolve_llm_credentials(settings, "fallback")
    assert creds.backend == "deepseek"
    assert creds.model == "deepseek-chat"
    assert creds.api_key == "sk-ds-test"
    assert creds.base_url == "https://api.deepseek.com/v1"


def test_resolve_deepseek_fallback_with_override() -> None:
    settings = Settings(
        FALLBACK_BACKEND="ollama",
        DEEPSEEK_API_KEY="sk-ds-test",
    )
    creds = resolve_llm_credentials(settings, "fallback", fallback_backend="deepseek")
    assert creds.backend == "deepseek"
    assert creds.api_key == "sk-ds-test"


def test_deepseek_fallback_requires_api_key() -> None:
    settings = Settings(FALLBACK_BACKEND="deepseek", DEEPSEEK_API_KEY=None)
    with pytest.raises(ValueError, match="DEEPSEEK_API_KEY"):
        resolve_llm_credentials(settings, "fallback")
