"""Structured JSON-lines logging shared with the Bash orchestrator.

Each line is one JSON object. Bash and Python append to the same file, so a
run's log shows every stage with its duration in order.
"""

from __future__ import annotations

import json
import time
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path


class JsonLog:
    def __init__(self, path: Path | None, run_id: str = "", component: str = "analyser"):
        self.path = path
        self.run_id = run_id
        self.component = component
        self.durations: dict[str, float] = {}

    def event(self, event: str, **fields) -> None:
        if self.path is None:
            return
        record = {
            "ts": datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z"),
            "run_id": self.run_id,
            "component": self.component,
            "event": event,
            **fields,
        }
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, sort_keys=False) + "\n")

    @contextmanager
    def stage(self, name: str, **fields):
        start = time.perf_counter()
        try:
            yield
        finally:
            ms = round((time.perf_counter() - start) * 1000, 3)
            self.durations[name] = ms
            self.event("stage", stage=name, duration_ms=ms, **fields)
