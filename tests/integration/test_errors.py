"""Error and unsupported inputs: every one ends with exit 3, never SAFE."""

from __future__ import annotations

import json
import subprocess

import pytest

from conftest import CHECKER, bash_executable, posix, run_checker
from smc_eval.error_inputs import build_all

pytestmark = pytest.mark.integration

IDS = [f"e{n:02d}" for n in range(1, 15)]


@pytest.fixture(scope="module")
def error_inputs(tmp_path_factory):
    return {e.id: e for e in build_all(tmp_path_factory.mktemp("errors"))}


def test_there_are_at_least_eight(error_inputs):
    assert sorted(error_inputs) == IDS


@pytest.mark.parametrize("eid", IDS)
def test_error_input_is_never_safe(error_inputs, eid, tmp_path):
    case = error_inputs[eid]
    code, report, done = run_checker(case.repo, *case.refs, args=tuple(case.args),
                                     out_dir=tmp_path / "out", env=case.env)
    assert code == 3, done.stderr
    assert report is not None, "a report is written even when the run stops early"
    assert report["status"] == case.expected_status
    assert case.expected_text in json.dumps(report), report
    assert not report["findings"]


@pytest.mark.parametrize(
    ("argv", "message"),
    [
        ([], "expected exactly two branch references"),
        (["a", "b"], "--repo is required"),
        (["--repo"], "--repo needs a value"),
        (["--repo", ".", "only-one-ref"], "expected exactly two branch references"),
        (["--bogus"], "unknown option"),
    ],
)
def test_usage_errors_exit_3(argv, message, tmp_path):
    done = subprocess.run([bash_executable(), posix(CHECKER), "--out-dir", posix(tmp_path), *argv],
                          capture_output=True, text=True)
    assert done.returncode == 3
    assert message in done.stderr


def test_help_exits_0():
    done = subprocess.run([bash_executable(), posix(CHECKER), "--help"], capture_output=True, text=True)
    assert done.returncode == 0
    assert "Exit codes: 0 SAFE, 1 SILENT BREAK, 2 TEXT CONFLICT, 3 INCONCLUSIVE/ERROR." in done.stdout
