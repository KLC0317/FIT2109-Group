"""Report building, exit-code mapping and the JSON-lines logger."""

from __future__ import annotations

import json
import logging
import re

import pytest

from smc.logjson import JsonLog
from smc.report import EXIT_CODES, build_report, render

MANIFEST = {"run_id": "r1", "refs": {"a": "feature-a", "b": "feature-b"},
            "commits": {"base": "b" * 40, "a": "a" * 40, "b": "c" * 40}, "merge": {"result": "clean"},
            "notes": ["1 uncommitted change(s) in the working tree were excluded"]}


@pytest.mark.parametrize(("status", "code"), [("SAFE", 0), ("SILENT_BREAK", 1), ("TEXT_CONFLICT", 2),
                                              ("INCONCLUSIVE", 3), ("ERROR", 3)])
def test_exit_codes(status, code):
    assert EXIT_CODES[status] == code
    assert build_report(MANIFEST, status)["exit_code"] == code


def test_safe_is_not_described_as_proof():
    report = build_report(MANIFEST, "SAFE")
    assert "not proof of program correctness" in report["meaning"]
    assert "note: 1 uncommitted change(s)" in render(report)


def test_conflict_rendering_lists_files():
    report = build_report({**MANIFEST, "merge": {"result": "conflict"}}, "TEXT_CONFLICT",
                          conflicts=["profileapp/users.py"])
    assert "  profileapp/users.py" in render(report)


def test_log_lines_match_the_orchestrator_format(tmp_path):
    log = JsonLog(tmp_path / "run.jsonl", "r1")
    with log.stage("parse", files=3):
        pass
    log.close()
    record = json.loads((tmp_path / "run.jsonl").read_text().splitlines()[0])
    assert record["component"] == "analyser" and record["stage"] == "parse" and record["files"] == 3
    assert record["level"] == "info" and record["logger"] == "smc"
    assert re.fullmatch(r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d\.\d{3}Z", record["ts"])
    assert log.durations["parse"] >= 0


def test_module_loggers_reach_the_run_log(tmp_path):
    log = JsonLog(tmp_path / "run.jsonl", "r1")
    logging.getLogger("smc.rules").info("plain message %s", 42)
    log.close()
    record = json.loads((tmp_path / "run.jsonl").read_text().splitlines()[0])
    assert (record["logger"], record["event"], record["message"]) == ("smc.rules", "message", "plain message 42")


def test_the_log_appends_to_what_the_orchestrator_wrote(tmp_path):
    path = tmp_path / "run.jsonl"
    path.write_text('{"component": "orchestrator", "event": "start"}\n')
    log = JsonLog(path, "r1")
    log.event("result", status="SAFE")
    log.close()
    assert [json.loads(line)["event"] for line in path.read_text().splitlines()] == ["start", "result"]


def test_no_log_path_means_no_file(tmp_path):
    log = JsonLog(None)
    log.event("anything")
    log.close()
    assert list(tmp_path.iterdir()) == []
