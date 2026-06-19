# Результаты бенчмарка sync vs async

Запуск:

```bash
python scripts/benchmark.py
python scripts/benchmark.py --strict-demo   # batch_chat vs batch_chat_strict
```

## Ожидаемые наблюдения

| Режим | Поведение |
|-------|-----------|
| **sync sequential** | 20 запросов один за другим; общее время ≈ сумма latency |
| **async concurrency=1** | Тот же параллелизм, что sync; время сопоставимо |
| **async concurrency=5** | Ускорение ~3–5× при I/O-bound и без rate limit |
| **async concurrency=10** | Ускорение **минимум 4–5×** относительно sync |

## batch_chat vs batch_chat_strict (bad model на 3-м запросе)

| Метод | При ошибке на 3-м промпте |
|-------|---------------------------|
| `batch_chat` (gather + per-item try) | Запросы 0,1,3,4 успешны; позиция 2 — `Exception` |
| `batch_chat_strict` (TaskGroup) | `ExceptionGroup`: все in-flight задачи отменены, partial results нет |

## Диагностика, если ускорения нет

1. **Rate limit (429)** — SDK retry + backoff; уменьшите `--concurrency` или увеличьте лимиты API.
2. **Забыт `await`** — coroutines не выполняются; проверьте, что benchmark вызывает `asyncio.run`.
3. **`time.sleep` в async** — блокирует event loop; в `ToolCallClient` его нет.
4. **Слишком короткий business timeout** — `LLM_BUSINESS_TIMEOUT=15` может обрывать медленные ответы.

## Шаблон для фактических замеров

| Режим | total (s) | ok | errors | speedup vs sync |
|-------|-----------|-----|--------|-----------------|
| sync sequential | | | | 1.00× |
| async c=1 | | | | |
| async c=5 | | | | |
| async c=10 | | | | |

_Заполните после прогона с реальным `OPENAI_API_KEY`._

## stream_chat TTFT

Проверка: первый `yield` раньше, чем завершение всего ответа.

```python
import time
from app.llm import ToolCallClient

async def check_ttft():
    client = ToolCallClient()
    started = time.perf_counter()
    first = last = None
    async for delta in client.stream_chat("Что такое event loop?"):
        now = time.perf_counter()
        if first is None:
            first = now - started
        last = now - started
    print(f"TTFT={first:.2f}s total={last:.2f}s")
    await client.aclose()
```

## SSE smoke test

```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000
curl -N -X POST http://localhost:8000/chat/stream \
  -H "Content-Type: application/json" \
  -d '{"prompt": "Что такое event loop?"}'
```
