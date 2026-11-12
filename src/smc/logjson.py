"""Structured JSON-lines logging on Python's standard logging module.

Analyser modules log with ``logging.getLogger(__name__)``. JsonLog attaches
one handler to the ``smc`` logger that appends a JSON object per record to
the run log. The Bash orchestrator appends to the same file, so one log
holds the whole run in order. Stage timings and the result are INFO
records; with --debug, the evidence behind each decision (branch deltas,
every incompatible use and why it was reported or excluded, unsupported
uses) is written as DEBUG records.
"""

from __future__ import annotations

import json
import logging
import time
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

LOGGER = "smc"


class JsonLinesFormatter(logging.Formatter):
    """One JSON object per record, in the orchestrator's record shape."""

    def __init__(self, run_id: str):
        super().__init__()
        self.run_id = run_id

    def format(self, record: logging.LogRecord) -> str:
        ts = datetime.fromtimestamp(record.created, timezone.utc).isoformat(timespec="milliseconds")
        data = {
            "ts": ts.replace("+00:00", "Z"),
            "run_id": self.run_id,
            "component": "analyser",
            "level": record.levelname.lower(),
            "logger": record.name,
            "event": getattr(record, "event", "message"),
        }
        fields = getattr(record, "fields", None)
        if fields:
            data.update(fields)
        elif data["event"] == "message":
            data["message"] = record.getMessage()
        return json.dumps(data, default=str)


def log_event(logger: logging.Logger, event: str, level: int = logging.INFO, **fields) -> None:
    """Log a structured record; the fields become JSON members."""
    if logger.isEnabledFor(level):
        logger.log(level, event, extra={"event": event, "fields": fields})


class JsonLog:
    """Run log for one analyser invocation (path None: log nothing)."""

    def __init__(self, path: Path | None, run_id: str = "", debug: bool = False):
        self.durations: dict[str, float] = {}
        self.logger = logging.getLogger(LOGGER)
        self.logger.setLevel(logging.DEBUG if debug else logging.INFO)
        self.logger.propagate = False
        self.close()
        if path is None:
            self.handler: logging.Handler = logging.NullHandler()
        else:
            path.parent.mkdir(parents=True, exist_ok=True)
            self.handler = logging.FileHandler(path, mode="a", encoding="utf-8")
            self.handler.setFormatter(JsonLinesFormatter(run_id))
        self.logger.addHandler(self.handler)

    def close(self) -> None:
        """Detach and close every handler, releasing the log file."""
        for handler in list(self.logger.handlers):
            self.logger.removeHandler(handler)
            handler.close()

    def event(self, event: str, **fields) -> None:
        log_event(self.logger, event, **fields)

    @contextmanager
    def stage(self, name: str, **fields):
        start = time.perf_counter()
        try:
            yield
        finally:
            ms = round((time.perf_counter() - start) * 1000, 3)
            self.durations[name] = ms
            self.event("stage", stage=name, duration_ms=ms, **fields)
