# Архитектура DocIntel (m3_b3)

**DocIntel** — AI-ассистент системного аналитика с циклом **LLM tool calling**: генерация документации фичи по корпоративному шаблону и standard kits, поиск по проектной документации (заглушка).

Документ описывает **целевую production-архитектуру** дипломного проекта и отмечает, что уже реализовано в коде. Текущая версия репозитория — **v0.2.0**.

---

## Что изменилось в архитектуре (v0.2.0 vs v0.1.0)

| Область | v0.1.0 (m3_b1) | v0.2.0 (m3_b3) |
|---------|----------------|----------------|
| LLM-слой | Синхронный `OpenAI` в `ToolCallClient` | **Async** `AsyncOpenAI` — единый `ToolCallClient` |
| Точки входа | Только CLI / Python API | + **FastAPI** (`/health`, `/chat/stream` SSE) |
| Параллелизм | Нет | `asyncio.gather` + `Semaphore` в `batch_chat()` |
| Fallback | Ручной `provider="primary"\|"fallback"` | **Auto-fallback** primary → Ollama/DeepSeek при ошибке + ручной выбор |
| Дублирование | Планировался отдельный `app/services/` | **Убрано** — всё в `app/llm/` |
| Бенчмарк | Нет | `SyncLLMClient` (baseline) vs `ToolCallClient.batch_chat()` |
| Sectioned flow | Sync `chat_sectioned()` | Async `await chat_sectioned_json()` — **логика та же**, последовательно |
| Tool handlers | Sync | Sync (без изменений — работа с файлами) |

**Не изменилось:** kit-tools, GAP-политики, `build_execution_plan`, последовательная оркестрация секций (зависимость `context_summary`), заглушка `search_kb`.

---

## Текущая реализация v0.2.0 (слой LLM и точки входа)

```mermaid
flowchart TB
    subgraph Entry["Точки входа (v0.2.0)"]
        CLI["examples/run_tool_call*.py<br/>asyncio.run()"]
        BENCH["scripts/benchmark.py"]
        API["FastAPI app/main.py<br/>/health · /chat/stream SSE"]
    end

    subgraph LLM["app/llm/ — единый async-слой"]
        TC["ToolCallClient<br/>AsyncOpenAI"]
        SYNC["SyncLLMClient<br/>OpenAI sync · только бенчмарк"]
        PROV["providers.py<br/>resolve_llm_credentials<br/>create_async_openai_client()"]
        ORCH["SectionOrchestrator<br/>async generate()"]
        TTC["text_tool_calls.py"]
    end

    subgraph Tools["app/tools/ — sync"]
        REG["ToolHandlers + registry"]
        KITS["feature_sections/kits.py"]
        GAP["gap_policies.py"]
    end

    subgraph Data["Data (локально)"]
        FS["shablon.md + standard kits"]
        DOCS["app/data/docs/"]
        KB["knowledge_base.txt"]
    end

    CLI -->|await chat_sectioned_json| TC
    BENCH -->|batch_chat async| TC
    BENCH -->|complete sync ×20| SYNC
    API -->|stream_chat| TC

    TC --> PROV
    SYNC --> PROV
    TC --> ORCH
    ORCH --> REG
    TC --> REG
    REG --> KITS
    REG --> FS
    REG --> DOCS
    REG --> KB
    TC --> TTC

    TC -->|primary fail| FB["Fallback AsyncOpenAI<br/>Ollama / DeepSeek"]
```

**Ключевой принцип v0.2.0:** один класс `ToolCallClient` обслуживает DocIntel (sectioned), бенчмарк (`complete` / `batch_chat`) и SSE (`stream_chat`). Синхронный код остаётся только в handlers и в `SyncLLMClient` для сравнения производительности.

---

## Диаграмма компонентов (целевая production)

```mermaid
flowchart TB
    subgraph Client["Клиент"]
        UI["Web UI / IDE-плагин"]
        CLI["examples/run_tool_call*.py"]
    end

    subgraph Gateway["Слой API Gateway"]
        NGINX["nginx<br/>reverse proxy"]
        AUTH["Auth<br/>OAuth 2.0 / API Key"]
        RL["Rate Limiter<br/>100 req/min per client"]
    end

    subgraph Service["Слой Service"]
        API["FastAPI<br/>✅ v0.2: /chat/stream SSE<br/>🔜 POST /v1/features/generate"]
        ORCH["SectionOrchestrator<br/>async · kit-tools → N секций"]
        REG["ToolHandlers + registry<br/>sync · dispatch по имени tool"]
        PROMPT["Prompt loader<br/>Jinja2 system prompts"]
    end

    subgraph LLM["Слой LLM"]
        TC["ToolCallClient<br/>✅ AsyncOpenAI · auto-fallback"]
        ROUTER["LLM Router + CB<br/>🔜 app/llm/router.py"]
        CB1["⚡ CB OpenAI"]
        CB2["⚡ CB DeepSeek"]
        CB3["⚡ CB Ollama"]
        OAI["OpenAI API<br/>gpt-4o-mini · primary"]
        DS["DeepSeek API<br/>deepseek-chat · fallback"]
        OLL["Ollama<br/>llama3.2:3b · fallback"]
    end

    subgraph Data["Слой Data"]
        FS["Локальные файлы<br/>shablon.md + standard kits"]
        DOCS["Markdown docs<br/>app/data/docs/"]
        KBTXT["knowledge_base.txt<br/>плоский индекс"]
        PG[("PostgreSQL<br/>метаданные сессий, audit")]
        REDIS[("Redis<br/>кэш KB-фрагментов, rate-limit counters")]
        S3[("S3 / MinIO<br/>сгенерированные .md, импорт Confluence")]
        VDB[("Vector DB<br/>pgvector / Qdrant · v0.3+")]
    end

    UI -->|HTTPS| NGINX
    CLI -.->|v0.2 напрямую| TC
    NGINX --> AUTH
    AUTH --> RL
    RL --> API

    API --> TC
    API --> ORCH
    API --> REG
    ORCH --> REG
    ORCH --> PROMPT
    TC --> ORCH
    REG --> FS
    REG --> DOCS
    REG --> KBTXT
    REG -.->|v0.3+| REDIS
    REG -.->|v0.3+| VDB

    TC -->|auto-fallback v0.2| DS
    TC -->|auto-fallback v0.2| OLL
    TC -.->|v0.3+ CB chain| ROUTER
    ROUTER --> CB1 --> OAI
    ROUTER -->|CB1 OPEN| CB2 --> DS
    ROUTER -->|CB1+CB2 OPEN| CB3 --> OLL

    API -.->|сохранение артефакта| S3
    API -.->|лог сессии| PG
    RL -.->|счётчики| REDIS

    classDef cb fill:#fff3cd,stroke:#856404,stroke-width:2px
    classDef ext fill:#e7f3ff,stroke:#0d6efd
    classDef done fill:#d1e7dd,stroke:#0f5132
    class CB1,CB2,CB3 cb
    class OAI,DS,OLL,PG,REDIS,S3,VDB ext
    class TC,API,ORCH done
```

**Условные обозначения**

| Символ | Значение |
|--------|----------|
| ✅ v0.2 | Реализовано в текущем коде |
| ⚡ CB | Circuit Breaker (один экземпляр на провайдера) — **план v0.3** |
| Сплошная стрелка | Реализовано или заложено в текущем коде |
| Пунктир | Планируется в дорожной карте (v0.3–v1.0) |

---

## Поток: генерация документации фичи (sectioned)

Сценарий: аналитик отправляет **feature brief** → получает **единый Markdown-документ**. В v0.2.0 все LLM-вызовы — **async**, секции — **последовательно**.

```mermaid
sequenceDiagram
    autonumber
    actor User as Аналитик
    participant CLI as CLI / Python API<br/>(v0.2 напрямую)
    participant TC as ToolCallClient<br/>(AsyncOpenAI)
    participant Orch as SectionOrchestrator
    participant Hand as ToolHandlers<br/>(sync)
    participant Data as Data Layer<br/>(kits + docs)
    participant LLM as LLM Provider<br/>(primary / fallback)

    User->>CLI: feature_brief + protocol
    CLI->>TC: await chat_sectioned_json(brief)

    TC->>Orch: generate(client, brief)
    Orch->>Orch: build_execution_plan(brief)<br/>→ 4–7 kit-tools

    loop Для каждого kit-tool (await, sequential)
        Orch->>Hand: write_section(tool, brief, context_summary)
        Hand->>Data: shablon_loader + standard kits
        Data-->>Hand: INTERNAL-пакет
        Hand-->>Orch: kit package

        Orch->>TC: await _create_completion(section prompt)
        alt primary OK
            TC->>LLM: AsyncOpenAI · gpt-4o-mini
        else primary error + fallback configured
            TC->>LLM: AsyncOpenAI · DeepSeek / Ollama
        end
        LLM-->>Orch: Markdown секции
        Orch->>Orch: context_summary += секция
    end

    Orch->>Orch: merge_section_documents()
    Orch-->>TC: финальный .md
    TC-->>CLI: {answer, model, tool_calls_made}
    CLI-->>User: сохранение в examples/answers/
```

**Соответствие коду (v0.2.0):** шаги 3–18 — `SectionOrchestrator.generate()` + async `ToolCallClient`; CLI/examples вызывают оркестратор **напрямую**, минуя Gateway. HTTP endpoint для полной генерации фичи — **ещё не реализован** (только SSE для простых промптов).

---

## Поток: SSE-стрим (v0.2.0)

Отдельный сценарий — **не** sectioned DocIntel, а демонстрация `stream_chat()` через FastAPI.

```mermaid
sequenceDiagram
    autonumber
    actor Client as curl / HTTP-клиент
    participant API as FastAPI<br/>POST /chat/stream
    participant TC as ToolCallClient
    participant LLM as AsyncOpenAI

    Client->>API: {"prompt": "..."}
    API->>TC: stream_chat(prompt)

    loop async for delta
        TC->>LLM: chat.completions stream=True
        LLM-->>TC: token delta
        TC-->>API: yield delta
        API-->>Client: SSE event: message
    end

    API-->>Client: SSE event: done [DONE]
```

Заголовки ответа: `X-Accel-Buffering: no`, `Cache-Control: no-cache` — для корректной работы через nginx.

---

## Поток: бенчмарк sync vs async (v0.2.0)

```mermaid
sequenceDiagram
    participant B as scripts/benchmark.py
    participant Sync as SyncLLMClient
    participant Async as ToolCallClient
    participant LLM as OpenAI API

    B->>Sync: 20× complete() последовательно
    loop sync loop
        Sync->>LLM: OpenAI sync
    end
    Sync-->>B: T_sync

    B->>Async: batch_chat(20 prompts, concurrency=10)
    par asyncio.gather + Semaphore
        Async->>LLM: AsyncOpenAI × N параллельно
    end
    Async-->>B: T_async (~6× быстрее при c=10)
```

---

## Точки отказоустойчивости

| # | Точка | Механизм | Где в коде / план |
|---|-------|----------|-------------------|
| 1 | **Rate Limiter** (Gateway) | 100 req/min → HTTP 429 | План: nginx + Redis |
| 2 | **Auth fallback** | IdP недоступен → 401 closed | План: Gateway |
| 3 | **CB OpenAI / DeepSeek / Ollama** | 50% errors / 30 s → OPEN | План: `app/llm/router.py` |
| 4 | **Auto-fallback primary → fallback** | При exception в `_create_completion` | ✅ `app/llm/client.py` |
| 5 | **Ручной выбор провайдера** | `provider="primary"\|"fallback"` | ✅ `ToolCallClient.__init__` |
| 6 | **Concurrency limit** | `Semaphore(LLM_CONCURRENCY)` | ✅ `batch_chat`, `complete` |
| 7 | **Sectioned orchestration** | 4–7 коротких вызовов вместо одного контекста | ✅ `section_orchestrator.py` |
| 8 | **Timeout per section** | `SUPPORT_TIMEOUT_SECONDS` (180–300 с) | ✅ `config.py` |
| 9 | **Business timeout** | `asyncio.timeout(LLM_BUSINESS_TIMEOUT)` | ✅ `complete()` |
| 10 | **SDK retry** | `max_retries=LLM_MAX_RETRIES` (429/5xx) | ✅ `create_async_openai_client()` |
| 11 | **GAP-политики** | Неизвестные факты → `GAP-*` | ✅ `gap_policies.py` |
| 12 | **Кэш KB** | Redis cache-aside | План: v0.3 |

---

## ADR-001: Паттерн взаимодействия клиента с сервисом

**Status:** Accepted (уточнён в v0.2.0)  
**Date:** 2026-06-19

### Context

| Параметр | Значение |
|----------|----------|
| **Сценарий** | Агент с tool calling: brief → plan kit-tools → handler (kits) + LLM (Markdown). Вспомогательно: `search_kb` (заглушка). |
| **Нагрузка (целевая)** | 5–20 RPM на инстанс |
| **Sectioned-режим** | 4–7 async-вызовов **последовательно** (`await` в цикле) |
| **Batch-режим (v0.2)** | N **независимых** промптов параллельно — только бенчмарк / utility, не DocIntel |

### Decision

1. **Генерация документа фичи** — **Request-Response** (async внутри, один артефакт наружу). Sectioned flow не стримится по секциям.
2. **Простые промпты (v0.2)** — дополнительно реализован **SSE** (`POST /chat/stream`) для демонстрации `stream_chat()`. Это **не** меняет основной DocIntel-flow.
3. Tool calling по-прежнему требует **полного ответа модели** перед dispatch handler — streaming несовместим с native tool calls в одном round-trip.

### Изменение относительно v0.1.0

В v0.1.0 SSE отвергался как избыточный для DocIntel. В v0.2.0 SSE добавлен **изолированно** для `stream_chat()` (учебный модуль async LLM), без интеграции в sectioned orchestrator.

### Consequences

**Выиграно:** простая отладка sectioned flow; параллелизм там, где секции независимы (`batch_chat`); TTFT-метрики через SSE.

**Trade-offs:** длинный CLI-запрос (до 8 мин) без прогресса «секция 3 из 7»; при обрыве — потеря всей генерации (mitigation: черновики в Redis — v0.4+).

---

## ADR-002: Стратегия fault tolerance для LLM-провайдеров

**Status:** Accepted (частично реализовано в v0.2.0)  
**Date:** 2026-06-19

### Decision

| Роль | Провайдер | Модель |
|------|-----------|--------|
| **Primary** | OpenAI API | `gpt-4o-mini` |
| **Fallback** | DeepSeek **или** Ollama (`FALLBACK_BACKEND`) | `deepseek-chat` / `llama3.2:3b` |

**Реализация v0.2.0:**

- `ToolCallClient` при `provider="primary"` создаёт второй `AsyncOpenAI` для fallback.
- При **любом exception** в `_create_completion()` — повторный вызов через fallback-клиент (если настроен).
- Ручной режим: `ToolCallClient(provider="fallback")` — только Ollama/DeepSeek без primary.
- **Circuit Breaker** и полноценный **LLM Router** — по-прежнему план (`app/llm/router.py`, v0.3).

**Удалено в v0.2.0:** поддержка Anthropic как отдельного провайдера.

---

## Потенциальные точки отказа

### API Gateway

| При выпадении | Паттерн смягчения | Graceful degradation |
|---------------|-------------------|----------------------|
| nginx / LB недоступен | Health checks + второй ingress | 502; CLI v0.2 работает напрямую с Python API |
| Auth (IdP) недоступен | Cached JWKS | **Closed failure:** 401 |
| Rate limiter (Redis) недоступен | Fail-open in-memory | Сервис жив, алерт ops |

### Service

| При выпадении | Паттерн смягчения | Graceful degradation |
|---------------|-------------------|----------------------|
| FastAPI crash | 2+ replicas, K8s probes | Retry; 503 |
| SSE client disconnect | `request.is_disconnected()` | ✅ генератор останавливается (`app/main.py`) |
| OOM на большом brief | Лимит body 32 KB | 413 |

### LLM

| При выпадении | Паттерн смягчения | Graceful degradation |
|---------------|-------------------|----------------------|
| **OpenAI недоступен** | Auto-fallback v0.2 → DeepSeek/Ollama | ✅ прозрачно в `_create_completion` |
| **Все провайдеры недоступны** | Exception → caller | CLI/API возвращает ошибку |
| Timeout одной секции | Per-section timeout | Частичный документ (план v0.4) |
| Rate limit 429 | SDK retry + fallback | ✅ `max_retries` + auto-fallback |

### Data

| При выпадении | Паттерн смягчения | Graceful degradation |
|---------------|-------------------|----------------------|
| **kits / shablon.md** | Git-versioned mount | **Hard failure:** 500 |
| **Markdown docs** | S3 replica (план) | `search_kb` — «не найдено»; генерация по brief OK |
| **PostgreSQL / Redis / S3** | План v0.3–v1.0 | Генерация без persistence |

---

## Маппинг на текущий код (v0.2.0)

| Компонент | Файл / модуль | Статус |
|-----------|---------------|--------|
| ToolCallClient (async) | `app/llm/client.py` | ✅ |
| SyncLLMClient (benchmark) | `app/llm/client.py` | ✅ baseline only |
| AsyncOpenAI factory | `app/llm/providers.py` | ✅ |
| SectionOrchestrator | `app/llm/section_orchestrator.py` | ✅ async |
| Text tool calls parser | `app/llm/text_tool_calls.py` | ✅ |
| ToolHandlers / registry | `app/tools/registry.py` | ✅ sync |
| FastAPI + SSE | `app/main.py`, `app/schemas/chat.py` | ✅ partial |
| Бенчмарк | `scripts/benchmark.py` | ✅ |
| Standard kits + shablon | `feature-methodology-project/` | ✅ |
| search_kb (token overlap) | `app/tools/search_kb/handler.py` | ⚠️ заглушка |
| LLM Router + Circuit Breaker | — | 🔜 v0.3 |
| POST /v1/features/generate | — | 🔜 |
| API Gateway (nginx) | — | 🔜 |
| PostgreSQL / Redis / S3 | — | 🔜 v0.3–v1.0 |
| ~~app/services/~~ | удалён в v0.2.0 | — |

---

## Связанные документы

- [README.md](../README.md) — установка, tools, переменные окружения, таблица «Что изменилось в v0.2.0»
- [scripts/benchmark_results.md](../scripts/benchmark_results.md) — результаты sync vs async
- [Дорожная карта](../README.md#дорожная-карта) — v0.3 … v1.0
