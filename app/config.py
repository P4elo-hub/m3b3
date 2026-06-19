"""Конфигурация приложения через pydantic-settings."""

from __future__ import annotations

from pathlib import Path

from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

FallbackBackend = Literal["ollama", "deepseek"]

APP_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = APP_DIR.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=PROJECT_ROOT / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    openai_api_key: str | None = Field(default=None, validation_alias="OPENAI_API_KEY")
    openai_base_url: str | None = Field(default=None, validation_alias="OPENAI_BASE_URL")
    model: str = Field(default="gpt-4o-mini", validation_alias="SUPPORT_PRIMARY_MODEL")
    fallback_api_key: str | None = Field(default="ollama", validation_alias="FALLBACK_API_KEY")
    fallback_base_url: str | None = Field(
        default="http://localhost:11434/v1",
        validation_alias="FALLBACK_BASE_URL",
    )
    fallback_model: str = Field(default="llama3.2:3b", validation_alias="FALLBACK_MODEL")
    fallback_backend: FallbackBackend = Field(
        default="ollama",
        validation_alias="FALLBACK_BACKEND",
    )
    deepseek_api_key: str | None = Field(default=None, validation_alias="DEEPSEEK_API_KEY")
    deepseek_base_url: str | None = Field(
        default="https://api.deepseek.com/v1",
        validation_alias="DEEPSEEK_BASE_URL",
    )
    deepseek_model: str = Field(default="deepseek-chat", validation_alias="DEEPSEEK_MODEL")
    service_name: str = Field(default="DocIntel", validation_alias="SUPPORT_SERVICE_NAME")
    request_timeout_seconds: float = Field(default=30.0, validation_alias="SUPPORT_TIMEOUT_SECONDS")
    max_tool_rounds: int = Field(default=5, validation_alias="SUPPORT_MAX_TOOL_ROUNDS")
    docs_dir: Path = Field(
        default=APP_DIR / "data" / "docs",
        validation_alias="SUPPORT_DOCS_DIR",
    )
    knowledge_base_path: Path | None = Field(
        default=APP_DIR / "data" / "knowledge_base.txt",
        validation_alias="SUPPORT_KB_PATH",
    )
    methodology_dir: Path = Field(
        default=PROJECT_ROOT / "feature-methodology-project",
        validation_alias="SUPPORT_METHODOLOGY_DIR",
    )
    shablon_path: Path = Field(
        default=PROJECT_ROOT / "feature-methodology-project" / "shablon.md",
        validation_alias="SUPPORT_SHABLON_PATH",
    )
