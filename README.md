# DocIntel (m3_b1) — AI-ассистент системного аналитика с tool calling

**DocIntel** — учебно-демонстрационный проект AI-ассистента для работы с проектной документацией системного аналитика. Ассистент построен на цикле **LLM tool calling**: модель получает system prompt, при необходимости вызывает инструменты (tools), получает их результат и формирует ответ пользователю.

Главная рабочая функция проекта на текущей версии (**v0.1.0**) — **написание документации новой фичи** по корпоративному шаблону и standard kits. Поиск по документации реализован как **заглушка** с минимальными демо-данными.

---

## Статус компонентов (важно прочитать перед использованием)

| Компонент | Статус | Комментарий |
|-----------|--------|-------------|
| **Kit-tools** (`write_requirements`, `write_use_case_*`, …) | ✅ Реализован | Основной режим генерации: пошагово по standard kits, склейка в один Markdown |
| **Legacy `write_feature_doc`** | ✅ Реализован | Один tool → один большой INTERNAL-пакет на весь документ (для сравнения и тестов) |
| **`search_kb`** | ⚠️ Заглушка | Handler и схема tool корректны, но поиск — примитивный (пересечение токенов), без семантики и без реальной базы |
| **`app/data/docs/`** | ⚠️ Заглушка | 2 демо-файла, не реальная проектная документация |
| **`app/data/knowledge_base.txt`** | ⚠️ Заглушка | Плоский список строк-описаний для smoke-теста поиска |
| **Примеры готовой документации фич** | 🔜 Планируется | В будущих версиях появятся эталонные артефакты и расширенная KB |
| **Семантический / векторный поиск** | 🔜 Планируется | Сейчас не реализован |

**Итог:** если вам нужно **сгенерировать документ фичи из brief** — проект готов к использованию. Если вам нужен **поиск по реальной документации проекта** — пока это только каркас; данные и алгоритм поиска будут доработаны позже.

---

## Что делает проект

1. Принимает **brief** аналитика (краткое описание фичи на русском).
2. По ключевым словам brief определяет, **какие разделы** корпоративного шаблона нужны (AS IS, TO BE, Kafka-событие, логи, метрики и т.д.).
3. Для каждого релевантного раздела подгружает **standard kit**: skill, template, spec, example, quality gate и скелет из `shablon.md`.
4. Вызывает LLM **пошагово** (отдельный запрос на каждый kit-tool) или **одним пакетом** (legacy).
5. Возвращает **один Markdown-документ** фичи: бизнес-требования, use case, интеграции, NFR, observability.
6. Неизвестные факты помечает как **`GAP-*`** / **`DESIGN-*`** по политикам kits (не выдумывает цифры и контракты).

---

## Архитектура: как проходит запрос

```text
Пользователь / examples/run_tool_call*.py
        │
        ▼
ToolCallClient (app/llm/client.py)
  • system prompt из app/prompts/
  • список tools из app/tools/registry.py
        │
        ├─ Режим chat_sectioned (основной в examples)
        │       │
        │       ▼
        │   SectionOrchestrator (app/llm/section_orchestrator.py)
        │     1. build_execution_plan(brief) → список kit-tools
        │     2. для каждого шага:
        │          handlers.write_section() → INTERNAL-пакет
        │          LLM генерирует Markdown секции
        │          context_summary передаётся в следующий шаг
        │     3. merge_section_documents() → финальный .md
        │
        └─ Режим chat (классический tool_call цикл)
                модель сама выбирает tool → handlers.dispatch()
```

**Два уровня вызова tools:**

| Уровень | Кто вызывает | Что происходит |
|---------|--------------|----------------|
| **Внешний** (OpenAI API) | Модель в `chat()` | Модель решает вызвать `search_kb`, `write_requirements`, … |
| **Внутренний** (оркестратор) | `SectionOrchestrator` | Python напрямую вызывает `handlers.write_section()` без участия модели в выборе tool |

Демо-скрипты `examples/run_tool_call*.py` используют **внутренний оркестратор** (`chat_sectioned`) — это надёжнее для длинных документов.

---

## Структура репозитория

```text
m3_b1/
├── app/                              # Исходный код приложения
│   ├── config.py                     # Настройки через pydantic-settings (.env)
│   ├── prompts/                      # System prompt и descriptions tools
│   ├── tools/                        # Реализация tools (handlers + schemas)
│   ├── llm/                          # LLM-клиент, оркестратор, парсер tool calls
│   └── data/                         # ⚠️ Демо-данные (заглушки)
│
├── feature-methodology-project/      # Методология: шаблон + standard kits
│   ├── shablon.md                    # Umbrella-шаблон фичи v2.0
│   ├── standarts_features (3).md     # Исходный канон стандарта
│   ├── *-standard-kit/               # Наборы: requirements, use-case, integration, …
│   └── 01-Requirements/, 02-Use-Cases/, …  # Примеры артефактов по методологии
│
├── examples/                         # Демо-скрипты и сгенерированные ответы
├── tests/                            # Юнит-тесты (без реальных вызовов LLM)
├── multimodal_support_assistant_cli/ # ⚠️ Устаревший CLI-прообраз (не основной путь)
├── .env.example
├── pyproject.toml
└── README.md
```

Ниже — подробно по каждой значимой папке.

---

### `app/` — ядро приложения

#### `app/config.py`

Единая точка конфигурации. Читает переменные из `.env`:

- ключи и URL для **primary** (OpenAI) и **fallback** (Ollama / DeepSeek);
- пути к `docs/`, `shablon.md`, `feature-methodology-project/`;
- таймауты и лимиты tool_call.

#### `app/prompts/` — промпты

| Файл | Назначение |
|------|------------|
| `system_v1.j2` | System prompt для классического `chat()` (роль, язык, правила GAP, запрет служебных строк kits) |
| `section_writer_v1.j2` | System prompt для пошаговой генерации одной секции |
| `loader.py` | Загрузка и рендер Jinja2-шаблонов |
| `tools/*.md` | Длинные **description** для OpenAI tools (модель читает их при выборе инструмента) |

Файлы в `tools/`:

- `search_kb.md` — когда искать в базе (⚠️ база пока демо)
- `write_requirements.md`, `write_use_case_as_is.md`, `write_use_case_to_be.md`
- `write_integration.md`, `write_data_model.md`, `write_nfr.md`, `write_observability.md`
- `write_feature_doc.md` — legacy single-shot tool

#### `app/tools/` — инструменты (handlers)

Центральная точка — **`registry.py`**:

- `get_openai_tools()` — собирает JSON-схемы tools для OpenAI API;
- `ToolHandlers` — единый dispatch по имени tool;
- `dispatch(name, arguments)` — маршрутизация в нужный handler.

Подпапки:

| Папка | Tool(s) | Роль |
|-------|---------|------|
| `search_kb/` | `search_kb` | ⚠️ Заглушка поиска по Markdown |
| `feature_sections/` | kit-tools (7 штук) | ✅ Пошаговая генерация по kits |
| `write_feature_doc/` | `write_feature_doc` | ✅ Legacy: полный пакет документа |
| `gap_policies.py` | — | Политики `GAP-*` / `DESIGN-*` по каждому kit-tool |

> **Примечание:** файл `app/tools/shablon_loader.py` — устаревшая копия; рабочая логика в `app/tools/write_feature_doc/shablon_loader.py`.

#### `app/llm/` — работа с моделью

| Файл | Назначение |
|------|------------|
| `client.py` | `ToolCallClient`: цикл chat + tool_call, `chat_sectioned()` |
| `section_orchestrator.py` | План kit-tools → N вызовов LLM → склейка |
| `text_tool_calls.py` | Парсер tool calls из текста (для слабых локальных моделей) |
| `providers.py` | Резолв credentials: primary / ollama / deepseek |

#### `app/data/` — ⚠️ демо-данные (заглушки)

```text
app/data/
├── docs/
│   ├── docintel-overview.md    # Выдуманный обзор продукта DocIntel
│   └── payment-gateway.md      # Выдуманный фрагмент про «Платёжный шлюз»
└── knowledge_base.txt          # Плоский список строк для smoke-теста search_kb
```

**Это не реальная документация вашего проекта.** Файлы нужны только чтобы:

- показать, как `search_kb` режет Markdown по заголовкам;
- пройти юнит-тест `test_search_docs_finds_confluence_import`;
- продемонстрировать формат хранения (Markdown + YAML front matter).

В **будущих версиях** планируется:

- набор эталонных артефактов документации фич;
- импорт из Confluence / корпоративного wiki;
- полноценная база для поиска.

---

### `feature-methodology-project/` — методология написания фич

Это **рабочий** источник для tool написания фич. Не заглушка.

| Элемент | Описание |
|---------|----------|
| `shablon.md` | Umbrella-шаблон v2.0: структура документа фичи + `<!-- kit-section -->` маршрутизация |
| `standarts_features (3).md` | Полный корпоративный стандарт (канон) |
| `requirements-standard-kit/` | §1.1 Цель, §2 Ограничения |
| `use-case-standard-kit/` | §1.2 AS IS, §1.3 TO BE |
| `integration-standard-kit/` | §4.1 REST/gRPC/Kafka/… |
| `data-standard-kit/` | §4.2.3 Модель данных |
| `nfr-standard-kit/` | §5.1, §5.2, §5.4, §5.5 |
| `observability-standard-kit/` | §5.3.1 Логи, §5.3.2 Метрики |
| `uml-diagram-standard-kit/` | Диаграммы (опционально) |

Каждый kit содержит: `skills/`, `templates/`, `spec-kit/`, `examples/`, `quality-gates/`.

**Как tool использует kits** (`write_feature_doc/shablon_loader.py`):

1. `parse_shablon()` — парсит `shablon.md` по `kit-section`, вырезает служебные blockquote-строки (`> **Kit`, `> **Покрывает стандарты`).
2. `infer_sections(brief)` — по ключевым словам brief выбирает разделы (Kafka → `4.1.2`, логи → `5.3.1`, миграция → `1.2-usecase`).
3. `build_section_package()` / `build_write_package()` — собирает INTERNAL-пакет: скелет, контракт, kit templates, gap policy.
4. LLM заполняет скелет → пользователь получает Markdown (без INTERNAL-обёртки).

---

### `examples/` — демонстрация и артефакты прогонов

| Файл | Что делает |
|------|------------|
| `demo_common.py` | Общий `FEATURE_BRIEF` (Kafka transfer-notifications), `save_answer()` |
| `run_tool_call.py` | Primary (OpenAI) → `answers/*_openai_*.md` |
| `run_tool_call_fallback.py` | Fallback Ollama → `answers/*_local_*.md` |
| `run_tool_call_deepseek.py` | Fallback DeepSeek → `answers/*_deepseek_*.md` |
| `answers/` | Сгенерированные ответы (в `.gitignore`) |

Все demo-скрипты вызывают **`chat_sectioned_json()`** — пошаговую генерацию через kit-tools.

---

### `tests/` — автотесты

Тесты **не вызывают LLM** (кроме моков в provider-тестах). Проверяют:

- парсинг `shablon.md` и непустые скелеты Use Case;
- план секций по brief;
- содержимое INTERNAL-пакетов (скелет, GAP policy, отсутствие kit-metadata);
- оркестратор и парсер text tool calls.

```bash
pytest
```

---

## Инструменты (tools): полный справочник

### 1. Kit-tools — ✅ основной способ генерации

Документ собирается **по частям**: один tool = один standard kit = один (или связанные) разделы shablon.

| Tool | Kit | Разделы shablon | Когда включается |
|------|-----|-----------------|------------------|
| `write_requirements` | requirements-standard-kit | `1.1`, `2` | Всегда (ядро документа) |
| `write_use_case_as_is` | use-case-standard-kit | `1.2-usecase` | Brief про «сейчас», миграцию, AS IS |
| `write_use_case_to_be` | use-case-standard-kit | `1.3-usecase` | Всегда (ядро документа) |
| `write_integration` | integration-standard-kit | `4.1.1`, `4.1.2` | REST/gRPC/Kafka/async в brief |
| `write_data_model` | data-standard-kit | `4.2.3` | Изменения БД, entity, миграции |
| `write_nfr` | nfr-standard-kit | `5.1`, `5.2-*`, `5.4`, `5.5` | Безопасность, perf, конфиг, toggles |
| `write_observability` | observability-standard-kit | `5.3.1`, `5.3.2` | Логи, метрики, мониторинг |

**Параметры** (общие для kit-tools):

| Поле | Тип | Обязательно | Описание |
|------|-----|-------------|----------|
| `feature_brief` | string | да | Описание фичи от аналитика |
| `protocol` | string | нет | `REST`, `gRPC`, `GraphQL`, `SOAP`, `Async` — для интеграций |
| `feature_name` | string | нет | Заголовок `# Название фичи` |
| `context_summary` | string | нет | Краткий контекст уже написанных секций (оркестратор заполняет сам) |
| `include_document_title` | boolean | нет | Добавить `# Название` в скелет первой секции |

**Как вызывается в коде:**

```python
from app.llm import ToolCallClient

client = ToolCallClient(provider="primary")
result = client.chat_sectioned_json(
    feature_brief="Сейчас синхронный REST... Перевести на Kafka...",
    feature_name="Асинхронные уведомления по переводам",
    protocol="Async",
)
print(result["answer"])
```

**Как вызывается через классический tool_call** (модель сама выбирает tools):

```python
result = client.chat_json("Опиши фичу: перевод уведомлений на Kafka...")
```

---

### 2. `write_feature_doc` — ✅ legacy (один пакет на весь документ)

| Поле | Тип | Описание |
|------|-----|----------|
| `feature_brief` | string | Описание фичи (обязательно) |
| `section_id` | string | `full` (по умолчанию) или `1.1`, `4.1.2`, … |
| `protocol` | string | Протокол интеграции |
| `feature_name` | string | Название для заголовка |

**Поведение:** один вызов tool возвращает большой INTERNAL-пакет со **всеми** релевантными разделами; модель должна заполнить и вернуть один Markdown.

По умолчанию **не включён** в список tools API (`include_legacy=False` в `get_openai_tools`). Используется в тестах и для сравнения с sectioned-режимом.

**Прямой вызов handler (без LLM):**

```python
from app.tools.registry import ToolHandlers
from pathlib import Path

handlers = ToolHandlers(
    methodology_dir=Path("feature-methodology-project"),
    shablon_path=Path("feature-methodology-project/shablon.md"),
)
package = handlers.write_feature_doc(
    feature_brief="...",
    protocol="Async",
    feature_name="Моя фича",
)
# package — INTERNAL-текст для модели, не для пользователя
```

---

### 3. `search_kb` — ⚠️ заглушка поиска

| Поле | Тип | Описание |
|------|-----|----------|
| `query` | string | Поисковый запрос (ключевые слова) |

**Что реализовано корректно (каркас):**

- OpenAI tool schema (`app/tools/search_kb/schema.py`);
- handler с разбором Markdown по заголовкам `#` … `######`;
- поддержка YAML front matter;
- опциональный плоский индекс `knowledge_base.txt`;
- prompt `search_kb.md` с инструкцией когда вызывать tool;
- dispatch в `registry.py`.

**Что является заглушкой:**

- **Алгоритм поиска** — пересечение токенов запроса и текста фрагмента (без embeddings, без BM25, без ранжирования по семантике);
- **Данные** — 2 демо `.md` и `knowledge_base.txt`, не реальная KB проекта;
- **Нет** индексации, обновления по webhook, Confluence-импорта в runtime.

**Поведение handler:**

```text
1. Загрузить все *.md из SUPPORT_DOCS_DIR → нарезать на DocChunk по заголовкам
2. Добавить строки из knowledge_base.txt
3. По query посчитать overlap токенов (слова > 2 символов, lower case)
4. Вернуть top-5 фрагментов с меткой [file.md » Заголовок » Подзаголовок]
```

**Пример ответа tool:**

```text
Найдено 2 фрагментов по запросу «импорт Confluence Markdown»:

1. [docintel-overview.md » DocIntel » Импорт из Confluence]
Импорт из Confluence
Выгрузка пространств через REST API...
```

**Когда модель должна вызывать:** вопросы о *существующей* документации, требованиях, API, процессах. На практике при демо-базе результат будет скудным.

---

## Установка и запуск

### Требования

- Python **3.11+**
- API-ключ OpenAI (для `run_tool_call.py`) **или** Ollama / DeepSeek (для fallback-скриптов)

### Установка

```bash
cd m3_b1
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
cp .env.example .env
# Заполните OPENAI_API_KEY (и при необходимости DEEPSEEK_API_KEY)
```

### Демо: генерация документации фичи

```bash
# OpenAI (primary) — 3–8 минут, несколько секций
python examples/run_tool_call.py
# → examples/answers/transfer-notifications-kafka_openai_YYYYMMDD_HHMMSS.md

# Ollama локально (нужен запущенный ollama + модель с tool calling)
python examples/run_tool_call_fallback.py
# → examples/answers/transfer-notifications-kafka_local_*.md

# DeepSeek API
python examples/run_tool_call_deepseek.py
# → examples/answers/transfer-notifications-kafka_deepseek_*.md
```

Brief для демо задан в `examples/demo_common.py` (`FEATURE_BRIEF`) — сценарий «перевод уведомлений с REST на Kafka».

### Тесты

```bash
pytest
pytest tests/test_tool_call.py -v   # handlers и shablon
```

---

## Переменные окружения

| Переменная | По умолчанию | Описание |
|------------|--------------|----------|
| `OPENAI_API_KEY` | — | Ключ primary-провайдера |
| `OPENAI_BASE_URL` | OpenAI | Base URL совместимого API |
| `SUPPORT_PRIMARY_MODEL` | `gpt-4o-mini` | Модель primary |
| `FALLBACK_BACKEND` | `ollama` | `ollama` или `deepseek` |
| `FALLBACK_API_KEY` | `ollama` | Ключ Ollama |
| `FALLBACK_BASE_URL` | `http://localhost:11434/v1` | URL Ollama |
| `FALLBACK_MODEL` | `llama3.2:3b` | Локальная модель |
| `DEEPSEEK_API_KEY` | — | Ключ DeepSeek |
| `DEEPSEEK_BASE_URL` | `https://api.deepseek.com/v1` | URL DeepSeek |
| `DEEPSEEK_MODEL` | `deepseek-chat` | Модель DeepSeek |
| `SUPPORT_SERVICE_NAME` | `DocIntel` | Имя в промптах |
| `SUPPORT_TIMEOUT_SECONDS` | `30` | Таймаут одного LLM-запроса (для sectioned лучше **180–300**) |
| `SUPPORT_MAX_TOOL_ROUNDS` | `5` | Лимит раундов tool_call в `chat()` |
| `SUPPORT_DOCS_DIR` | `app/data/docs` | ⚠️ Папка демо-документации для search_kb |
| `SUPPORT_KB_PATH` | `app/data/knowledge_base.txt` | ⚠️ Плоский демо-индекс |
| `SUPPORT_METHODOLOGY_DIR` | `feature-methodology-project` | Папка kits |
| `SUPPORT_SHABLON_PATH` | `feature-methodology-project/shablon.md` | Шаблон фичи |

---

## Формат выходного документа фичи

При успешной генерации вы получаете **один Markdown-файл** примерно такой структуры:

```text
# [Название фичи]

## 1. Бизнес-требования
### 1.1. Цель
### 1.2. Процесс/Сервис AS IS      ← если в brief есть миграция / «сейчас»
### 1.3. Процесс/Сервис TO BE      ← обязательно: Use Case + сценарии

## 2. Ограничения и допущения

## 4. Функциональные требования
#### 4.1.2. Асинхронное событие [EventName]   ← при Kafka

## 5. Нефункциональные требования
#### 5.3.1. Требования к логированию
#### 5.3.2. Требования к мониторингу
```

**Обязательно в §1.3 TO BE:** таблица Use Case, предусловия, постусловия, основной сценарий (с ветвлениями `ЕСЛИ/ТО/ИНАЧЕ`), минимум один альтернативный сценарий. Диаграммы — по желанию.

**GAP-политика:** всё, чего нет в brief, помечается `GAP-REQ-001`, `GAP-UC-001`, `GAP-INT-001`, … с таблицей «Gaps и допущения». Модель не должна выдумывать числа (latency, RPS, timeout) без основания.

---

## Ограничения текущей версии

1. **Поиск — заглушка.** `search_kb` технически подключён, но не заменяет корпоративный поиск по документации.
2. **Демо-данные.** `app/data/` не содержит реальных артефактов вашего проекта.
3. **Нет UI.** Только Python API и CLI-скрипты в `examples/`.
4. **Качество зависит от модели.** Слабые локальные модели могут пропускать tool calls, раздувать GAP-таблицы или упрощать use case.
5. **Длинные документы.** Sectioned-режим делает 4–7 LLM-запросов → нужен адекватный таймаут и бюджет токенов.
6. **Нет векторной БД, Confluence sync, auth** — запланировано на будущие версии.

---

## Дорожная карта (планируемые версии)

| Версия | План |
|--------|------|
| **v0.2** | Эталонные примеры документации фич в репозитории; расширенная `app/data/docs/` |
| **v0.3** | Улучшенный поиск (BM25 или embeddings); меньше «шума» в GAP-таблицах |
| **v0.4** | Импорт Markdown из Confluence / wiki; CI-проверка по quality gates kits |
| **v1.0** | Полноценный DocIntel: поиск + генерация + согласованная KB проекта |

---

## Быстрая шпаргалка: что использовать

| Задача | Что вызывать | Статус |
|--------|--------------|--------|
| Написать документ новой фичи из brief | `examples/run_tool_call.py` или `ToolCallClient.chat_sectioned_json()` | ✅ Готово |
| Получить INTERNAL-пакет без LLM | `ToolHandlers.write_section()` / `write_feature_doc()` | ✅ Готово |
| Найти фрагмент в документации проекта | `search_kb` | ⚠️ Заглушка |
| Найти пример готовой фичи в репо | — | 🔜 Будет позже |

---

## Лицензия и контекст

Проект входит в учебный набор **ai-tools-and-links** (модуль m3_b1): демонстрация паттерна **LLM tool calling** для системного анализа — отделение фактов (tools/data) от инструкций (prompts) и маршрутизация генерации через **standard kits**.
