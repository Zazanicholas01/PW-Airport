from __future__ import annotations

import logging
import os
from pathlib import Path

from src.domain.status_constants import LOGGERS


def _level_from_env(name: str, default: str) -> int:
    level_name = os.getenv(name, default).upper()
    return int(getattr(logging, level_name, logging.DEBUG))


def configure_logging() -> None:
    debug_level = _level_from_env("PW_DEBUG_LOG_LEVEL", "DEBUG")
    runtime_level = _level_from_env("PW_RUNTIME_LOG_LEVEL", "INFO")
    third_party_level = _level_from_env("PW_THIRD_PARTY_LOG_LEVEL", "WARNING")

    root = logging.getLogger()
    root.setLevel(debug_level)
    root.handlers.clear()

    console = logging.StreamHandler()
    console.setLevel(debug_level)
    console.setFormatter(logging.Formatter("%(asctime)s %(levelname)s [%(name)s] %(message)s"))
    root.addHandler(console)

    runtime = logging.getLogger(LOGGERS.RUNTIME)
    runtime.setLevel(runtime_level)
    runtime.propagate = False
    runtime.handlers.clear()

    runtime_console = logging.StreamHandler()
    runtime_console.setLevel(runtime_level)
    runtime_console.setFormatter(logging.Formatter("%(asctime)s RUNTIME %(message)s"))
    runtime.addHandler(runtime_console)

    log_dir = Path(os.getenv("LOG_DIR", "data/logs"))
    log_dir.mkdir(parents=True, exist_ok=True)
    runtime_file = logging.FileHandler(log_dir / "runtime.log", encoding="utf-8")
    runtime_file.setLevel(runtime_level)
    runtime_file.setFormatter(logging.Formatter("%(asctime)s RUNTIME %(message)s"))
    runtime.addHandler(runtime_file)

    for logger_name in ("asyncio", "websockets", "websockets.server", "websockets.client"):
        logging.getLogger(logger_name).setLevel(third_party_level)
