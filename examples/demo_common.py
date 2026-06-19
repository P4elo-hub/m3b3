"""Общие константы и сохранение ответа для examples/."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

EXAMPLES_DIR = Path(__file__).resolve().parent
ANSWERS_DIR = EXAMPLES_DIR / "answers"
FEATURE_SLUG = "transfer-notifications-kafka"
FEATURE_NAME = "Асинхронная отправка уведомлений по переводам"
FEATURE_PROTOCOL = "Async"

FEATURE_BRIEF = """
Нужно задокументировать фичу «Асинхронная отправка уведомлений по переводам».

Контекст:
Сейчас сервис переводов после успешного P2P-перевода между счетами клиента
синхронно вызывает Notification Service по REST. Это увеличивает latency
операции и создаёт каскадные отказы, если Notification Service недоступен.

Целевое решение:
Перевести отправку уведомлений на асинхронную модель через Kafka.
Transfer Service после успешного списания публикует событие в топик
`transfer.completed`. Notification Service подписывается на топик и отправляет
клиенту SMS и push.

Ожидаемое содержимое события:
- transferId (UUID)
- clientId (UUID)
- amount (decimal)
- currency (ISO 4217, например RUB)
- completedAt (ISO 8601)
- channel (enum: SMS, PUSH, BOTH)

Требования:
- Гарантия доставки at-least-once
- Идемпотентная обработка на стороне Notification Service (по transferId)
- DLQ для сообщений, которые не удалось обработать после 3 retry
- Retention топика 7 дней
- При недоступности Kafka перевод не должен откатываться — уведомление
  считается best-effort, но событие должно попасть в outbox и быть
  переотправлено позже

Затронутые системы:
- Transfer Service (producer)
- Notification Service (consumer)
- Kafka cluster (корпоративный)

Нужна полная документация фичи по корпоративному шаблону: бизнес-цель,
use case TO BE, асинхронная интеграция (событие Kafka), логирование
и метрики для producer/consumer.
""".strip()


def normalize_markdown_answer(text: str) -> str:
    """Оставляет только Markdown-документ фичи без преамбулы и code fence."""
    text = text.strip()

    for prefix in (
        "Вот полная документация",
        "Вот документация",
        "Ниже документация",
        "# INTERNAL:",
        "# Пакет методологии",
    ):
        if text.lower().startswith(prefix.lower()):
            lines = text.splitlines()
            for index, line in enumerate(lines):
                if line.startswith("# ") and "пакет" not in line.lower() and "internal" not in line.lower():
                    text = "\n".join(lines[index:]).strip()
                    break

    if text.startswith("```"):
        lines = text.splitlines()
        if lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        text = "\n".join(lines).strip()

    for marker in ("Если нужно внести изменения", "Дайте знать", "Если нужны уточнения"):
        idx = text.find(marker)
        if idx != -1:
            text = text[:idx].strip()

    return text.strip() + "\n"


def save_answer(result: dict[str, object], *, suffix: str = "") -> Path:
    ANSWERS_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    slug = FEATURE_SLUG if not suffix else f"{FEATURE_SLUG}_{suffix}"
    output_path = ANSWERS_DIR / f"{slug}_{timestamp}.md"
    output_path.write_text(normalize_markdown_answer(str(result["answer"])), encoding="utf-8")
    return output_path
