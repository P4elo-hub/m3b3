"""Скрипт запуска: sectioned demo на локальной Ollama (FALLBACK_BACKEND=ollama)."""

from __future__ import annotations

import sys

from fallback_demo import handle_fallback_demo_errors, run_sectioned_fallback_demo

if __name__ == "__main__":
    try:
        raise SystemExit(run_sectioned_fallback_demo(backend="ollama", answer_suffix="local"))
    except BaseException as error:
        raise SystemExit(handle_fallback_demo_errors(error, backend="ollama")) from error
