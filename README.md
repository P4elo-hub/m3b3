# DocIntel (m3_b3) — AI-ассистент системного аналитика с async tool calling

**DocIntel** — учебно-демонстрационный проект AI-ассистента для работы с проектной документацией системного аналитика. Ассистент построен на цикле **LLM tool calling**: модель получает system prompt, при необходимости вызывает инструменты (tools), получает их результат и формирует ответ пользователю.

Текущая версия — **v0.2.0**. Главная функция — **написание документации новой фичи** по корпоративному шаблону и standard kits. Поиск по документации — **заглушка** с демо-данными.

---

## Что изменилось в v0.2.0 (относительно v0.1.0 / m3_b1)

| Было (v0.1.0) | Стало (v0.2.0) |
|---------------|----------------|
| Синхронный `OpenAI` в `ToolCallClient` | **Async** `AsyncOpenAI` — единый async-клиент |
| Только `chat()` / `chat_sectioned()` (sync) | + `complete()`, `batch_chat()`, `batch_chat_strict()`, `stream_chat()` |
| Examples: прямой вызов без `await` | Examples: `asyncio.run()` + `await client.chat_sectioned_json()` |
| Нет HTTP API | **FastAPI** + SSE `/chat/stream` (`app/main.py`) |
| Нет бенчмарка | **`scripts/benchmark.py`** — sync vs async (ускорение до ~6× при c=10) |
| Отдельный слой `app/services/` | **Убран** — всё в `app/llm/client.py` |
| Один путь к LLM | Единая фабрика `create_async_openai_client()` в `providers.py` |
| Fallback вручную через `provider=` | Auto-fallback primary → Ollama / DeepSeek при ошибке primary |
| `SyncLLMClient` не было | `SyncLLMClient` — только baseline для бенчмарка |
| 22 теста | **29 тестов** (+ async client, SSE, TaskGroup) |

**Не изменилось (намеренно):**

- Логика kit-tools, `shablon.md`, standard kits, GAP-политики
- Sectioned-генерация **последовательная** (секция за секцией — нужен `context_summary`)
- Handlers в `app/tools/` — sync (работа с файлами, не с сетью)
- `search_kb` — по-прежнему заглушка

---

## Статус компонентов

| Компонент | Статус | Комментарий |
|-----------|--------|-------------|
| **Kit-tools + sectioned orchestrator** | ✅ | Async `ToolCallClient.chat_sectioned_json()` |
| **`ToolCallClient.complete / batch / stream`** | ✅ | Один клиент для DocIntel, бенчмарка и SSE |
| **FastAPI SSE** (`/chat/stream`) | ✅ | `uvicorn app.main:app` |
| **Бенчмарк sync vs async** | ✅ | `python scripts/benchmark.py` |
| **Legacy `write_feature_doc`** | ✅ | Для сравнения и тестов |
| **`search_kb`** | ⚠️ | Заглушка (token overlap, демо-данные) |
| **`app/data/docs/`** | ⚠️ | 2 демо-файла |
| **Семантический поиск** | 🔜 | v0.3+ |

---

## Архитектура

```text
examples/run_tool_call*.py          scripts/benchmark.py       uvicorn app.main
        │                                    │                        │
        └──────────────────┬─────────────────┴────────────────────────┘
                           ▼
              ToolCallClient (app/llm/client.py)  ← единый async-клиент
                • AsyncOpenAI (primary / Ollama / DeepSeek)
                • chat / chat_sectioned  — DocIntel + tools
                • complete / batch_chat  — бенчмарк
                • stream_chat            — SSE
                           │
         ┌─────────────────┼─────────────────┐
         ▼                 ▼                 ▼
  SectionOrchestrator   ToolHandlers    providers.py
  (async, sequential)   (sync, files)   create_async_openai_client()
```

**Sectioned-режим** (основной в examples): kit-tool → LLM → секция → склейка. Секции идут **последовательно** (async `await`, но не параллельно) — каждая следующая видит `context_summary` предыдущих.

**Batch-режим** (бенчмарк): N независимых промптов параллельно через `asyncio.gather` + `Semaphore`.

---

## Структура репозитория

```text
m3_b3/
├── app/
│   ├── config.py                 # Settings (.env)
│   ├── main.py                   # FastAPI + SSE /chat/stream
│   ├── schemas/                  # Pydantic-схемы API
│   ├── llm/
│   │   ├── client.py             # ToolCallClient + SyncLLMClient
│   │   ├── providers.py          # credentials + AsyncOpenAI factory
│   │   ├── section_orchestrator.py
│   │   └── text_tool_calls.py
│   ├── tools/                    # handlers (sync)
│   ├── prompts/
│   └── data/                     # ⚠️ демо-данные
├── feature-methodology-project/  # shablon.md + standard kits
├── examples/                     # run_tool_call*.py
├── scripts/
│   ├── benchmark.py              # sync vs async
│   └── benchmark_results.md
├── tests/
├── docs/architecture.md
├── .env.example
└── pyproject.toml
```

---

## ToolCallClient — единая точка входа

Все сценарии используют **один класс** `ToolCallClient` и **одни настройки** из `.env`.

| Метод | Назначение |
|-------|------------|
| `chat()` / `chat_json()` | Классический tool_call цикл |
| `chat_sectioned()` / `chat_sectioned_json()` | **DocIntel**: генерация документа фичи |
| `complete(prompt)` | Один prompt → ответ |
| `batch_chat(prompts)` | Параллельные запросы (`gather` + `Semaphore`) |
| `batch_chat_strict(prompts)` | TaskGroup: все или ничего |
| `stream_chat(prompt)` | Async-генератор дельт (SSE) |
| `aclose()` | Закрыть HTTP-соединения |

**Провайдеры:** OpenAI (primary) → fallback Ollama или DeepSeek (`FALLBACK_BACKEND`).

```python
import asyncio
from app.llm import ToolCallClient

async def main():
    client = ToolCallClient(provider="primary")
    try:
        result = await client.chat_sectioned_json(
            feature_brief="Перевести уведомления на Kafka...",
            feature_name="Асинхронные уведомления по переводам",
            protocol="Async",
        )
        print(result["answer"])
    finally:
        await client.aclose()

asyncio.run(main())
```

---

## Установка и запуск

### Требования

- Python **3.11+**
- API-ключ OpenAI **или** Ollama / DeepSeek для fallback-скриптов

### Установка

```bash
cd m3_b3
python3 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
cp .env.example .env
# Заполните OPENAI_API_KEY (и при необходимости DEEPSEEK_API_KEY)
```

**Важно:** убедитесь, что venv принадлежит **этой** папке (`m3_b3`), а не скопирован из `m3_b1`:

```bash
which python
# → .../m3_b3/.venv/bin/python

python -c "import app.llm.client as c; print(c.__file__)"
# → .../m3_b3/app/llm/client.py
```

### Генерация документации фичи

```bash
python examples/run_tool_call.py              # OpenAI (primary)
python examples/run_tool_call_fallback.py     # Ollama
python examples/run_tool_call_deepseek.py     # DeepSeek
# → examples/answers/transfer-notifications-kafka_*_YYYYMMDD_HHMMSS.md
```

### FastAPI + SSE

```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000

curl -N -X POST http://localhost:8000/chat/stream \
  -H "Content-Type: application/json" \
  -d '{"prompt": "Что такое event loop?"}'
```

### Бенчмарк sync vs async

```bash
python scripts/benchmark.py
python scripts/benchmark.py --strict-demo   # batch_chat vs TaskGroup
```

### Тесты

```bash
pytest
```

---

## Переменные окружения

| Переменная | По умолчанию | Описание |
|------------|--------------|----------|
| `OPENAI_API_KEY` | — | Ключ primary (OpenAI) |
| `OPENAI_BASE_URL` | OpenAI | Base URL |
| `SUPPORT_PRIMARY_MODEL` | `gpt-4o-mini` | Модель primary |
| `FALLBACK_BACKEND` | `ollama` | `ollama` или `deepseek` |
| `FALLBACK_API_KEY` | `ollama` | Ключ Ollama |
| `FALLBACK_BASE_URL` | `http://localhost:11434/v1` | URL Ollama |
| `FALLBACK_MODEL` | `llama3.2:3b` | Локальная модель |
| `DEEPSEEK_API_KEY` | — | Ключ DeepSeek |
| `DEEPSEEK_BASE_URL` | `https://api.deepseek.com/v1` | URL DeepSeek |
| `DEEPSEEK_MODEL` | `deepseek-chat` | Модель DeepSeek |
| `SUPPORT_SERVICE_NAME` | `DocIntel` | Имя в промптах |
| `SUPPORT_TIMEOUT_SECONDS` | `30` | Таймаут LLM-запроса (sectioned: **180–300**) |
| `SUPPORT_MAX_TOOL_ROUNDS` | `5` | Лимит раундов tool_call |
| `LLM_CONCURRENCY` | `5` | Semaphore для `batch_chat` |
| `LLM_SDK_TIMEOUT` | `30` | Таймаут SDK (`AsyncOpenAI`) |
| `LLM_BUSINESS_TIMEOUT` | `15` | `asyncio.timeout` в `complete()` |
| `LLM_MAX_RETRIES` | `3` | Retry SDK (429/5xx) |
| `LLM_MAX_TOKENS` | `512` | Лимит токенов в `complete` / `stream` |
| `SUPPORT_METHODOLOGY_DIR` | `feature-methodology-project` | Папка kits |
| `SUPPORT_SHABLON_PATH` | `feature-methodology-project/shablon.md` | Шаблон фичи |

---

## Kit-tools (без изменений в v0.2.0)

| Tool | Kit | Разделы | Когда |
|------|-----|---------|-------|
| `write_requirements` | requirements | `1.1`, `2` | Всегда |
| `write_use_case_as_is` | use-case | `1.2-usecase` | Миграция / AS IS |
| `write_use_case_to_be` | use-case | `1.3-usecase` | Всегда |
| `write_integration` | integration | `4.1.1`, `4.1.2` | REST/Kafka/async |
| `write_data_model` | data | `4.2.3` | БД, entity |
| `write_nfr` | nfr | `5.1`, `5.2-*`, … | NFR |
| `write_observability` | observability | `5.3.1`, `5.3.2` | Логи, метрики |

Подробности — в `feature-methodology-project/` и `app/tools/feature_sections/`.

---

## SyncLLMClient — зачем он есть

`SyncLLMClient` — **только для бенчмарка**: 20 последовательных sync-запросов как baseline. DocIntel, examples и FastAPI его **не используют**.

---

## Быстрая шпаргалка

| Задача | Как |
|--------|-----|
| Документ фичи из brief | `python examples/run_tool_call.py` |
| Программно (async) | `await ToolCallClient(...).chat_sectioned_json(...)` |
| SSE-стрим | `uvicorn app.main:app` → `POST /chat/stream` |
| Сравнить sync vs async | `python scripts/benchmark.py` |
| INTERNAL-пакет без LLM | `ToolHandlers.write_section()` |
| Поиск по KB | `search_kb` ⚠️ заглушка |

---

## Ограничения v0.2.0

1. Sectioned-генерация — **последовательная** (не параллельная по секциям).
2. `search_kb` — заглушка, без embeddings.
3. `SyncLLMClient` — только для бенчмарка, не для production.
4. Нет UI — CLI, Python API, FastAPI SSE.
5. Auto-fallback primary → Ollama/DeepSeek — без Circuit Breaker (в планах).

---

## Дорожная карта

| Версия | План |
|--------|------|
| **v0.2** ✅ | Async LLM-клиент, FastAPI SSE, бенчмарк |
| **v0.3** | BM25/embeddings для search_kb; LLM router + CB |
| **v0.4** | Confluence import; CI quality gates |
| **v1.0** | Полноценный DocIntel: поиск + генерация + KB |

---

## Контекст

Проект — модуль **m3_b3** учебного набора **ai-tools-and-links**: паттерн **LLM tool calling** для системного анализа — facts (tools/data) отделены от instructions (prompts), генерация маршрутизируется через **standard kits**.

Подробная production-архитектура — [`docs/architecture.md`](docs/architecture.md).
