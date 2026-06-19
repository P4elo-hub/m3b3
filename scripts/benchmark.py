#!/usr/bin/env python3
"""Бенчмарк sync vs async LLM-клиента на 20 одинаковых промптах."""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.llm import SyncLLMClient, ToolCallClient

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger(__name__)

PROMPT_COUNT = 20
PROMPTS = [
    f"Объясни одним абзацем (4–6 предложений) концепцию №{index} "
    f"в программировании или computer science."
    for index in range(1, PROMPT_COUNT + 1)
]


def run_sync(prompts: list[str]) -> tuple[float, int, int]:
    client = SyncLLMClient()
    errors = 0
    started = time.perf_counter()
    try:
        for prompt in prompts:
            try:
                client.complete(prompt)
            except Exception as exc:
                errors += 1
                logger.warning("sync error: %s", exc)
    finally:
        client.close()
    elapsed = time.perf_counter() - started
    return elapsed, len(prompts) - errors, errors


async def run_async_batch(prompts: list[str], concurrency: int) -> tuple[float, int, int]:
    client = ToolCallClient(concurrency=concurrency)
    errors = 0
    started = time.perf_counter()
    try:
        results = await client.batch_chat(prompts)
        for item in results:
            if isinstance(item, Exception):
                errors += 1
    finally:
        await client.aclose()
    elapsed = time.perf_counter() - started
    return elapsed, len(prompts) - errors, errors


async def compare_strict_vs_resilient() -> None:
    """batch_chat vs batch_chat_strict при невалидной модели на 3-м запросе."""
    prompts = PROMPTS[:5]
    bad_model = "invalid-model-name-for-benchmark"
    client = ToolCallClient(concurrency=5)

    print("\n=== batch_chat (return_exceptions via gather) ===")
    models = [client.model, client.model, bad_model, client.model, client.model]
    resilient_client = ToolCallClient(concurrency=5)

    async def resilient_run() -> list[str | Exception]:
        async def _one(index: int, prompt: str) -> str | Exception:
            model = models[index]
            try:
                return await resilient_client.complete(prompt, model=model)
            except Exception as exc:
                return exc

        return list(await asyncio.gather(*(_one(i, p) for i, p in enumerate(prompts))))

    results = await resilient_run()
    for index, item in enumerate(results):
        label = "OK" if isinstance(item, str) else type(item).__name__
        print(f"  [{index}] {label}")
    ok_count = sum(1 for item in results if isinstance(item, str))
    print(f"  Успешно: {ok_count}/{len(prompts)}, остальные — Exception на своих позициях")

    print("\n=== batch_chat_strict (TaskGroup) ===")
    try:
        await client.batch_chat_strict(prompts, models=models)
        print("  Неожиданно: все запросы прошли")
    except* Exception as group:
        print(f"  ExceptionGroup: {len(group.exceptions)} исключений, все задачи отменены")
        for exc in group.exceptions:
            print(f"    - {type(exc).__name__}: {exc}")

    await resilient_client.aclose()
    await client.aclose()


def print_row(label: str, elapsed: float, ok: int, errors: int, baseline: float | None = None) -> None:
    speedup = baseline / elapsed if baseline and elapsed > 0 else None
    speedup_text = f"  speedup={speedup:.2f}x" if speedup else ""
    print(
        f"{label:40}  total={elapsed:7.2f}s  ok={ok:2d}  errors={errors:2d}{speedup_text}"
    )


async def main_async(args: argparse.Namespace) -> None:
    prompts = PROMPTS[: args.count]

    print(f"Benchmark: {len(prompts)} prompts, model from .env\n")

    sync_elapsed, sync_ok, sync_err = run_sync(prompts)
    print_row("sync sequential", sync_elapsed, sync_ok, sync_err)

    for concurrency in args.concurrency:
        elapsed, ok, err = await run_async_batch(prompts, concurrency)
        print_row(
            f"async batch_chat (concurrency={concurrency})",
            elapsed,
            ok,
            err,
            baseline=sync_elapsed,
        )

    if args.strict_demo:
        await compare_strict_vs_resilient()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Sync vs async LLM benchmark")
    parser.add_argument("--count", type=int, default=PROMPT_COUNT, help="Число промптов")
    parser.add_argument(
        "--concurrency",
        type=int,
        nargs="+",
        default=[1, 5, 10],
        help="Значения concurrency для async batch",
    )
    parser.add_argument(
        "--strict-demo",
        action="store_true",
        help="Сравнить batch_chat и batch_chat_strict с bad model на 3-м запросе",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    asyncio.run(main_async(args))


if __name__ == "__main__":
    main()
