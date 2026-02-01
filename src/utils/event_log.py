import os, json
from pathlib import Path
from datetime import datetime, timezone

def log_dir() -> Path:
    return Path(os.getenv("LOG_DIR", "data/logs"))

def append_event(evt: dict, *, filename: str = "events.jsonl") -> None:

    evt.setdefault("ts", datetime.now(timezone.utc).isoformat())
    d = log_dir()
    d.mkdir(parents=True, exist_ok=True)
    with (d / filename).open("a", encoding="utf-8") as f:
        f.write(json.dumps(evt, separators=(",", ":"), ensure_ascii=False) + "\n")
        f.flush()
