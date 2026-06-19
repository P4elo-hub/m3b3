"""Скрипт запуска: sectioned demo через DeepSeek API (FALLBACK_BACKEND=deepseek)."""

from __future__ import annotations

import asyncio
import sys

from fallback_demo import handle_fallback_demo_errors, run_sectioned_fallback_demo

if __name__ == "__main__":
    try:
        raise SystemExit(asyncio.run(run_sectioned_fallback_demo(backend="deepseek", answer_suffix="deepseek")))
    except BaseException as error:
        raise SystemExit(handle_fallback_demo_errors(error, backend="deepseek")) from error
