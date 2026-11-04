"""Fixture generator and the checker on the development set.

Only development cases are used here. Holdout cases are reserved for the
evaluation harness (scripts/evaluate.sh) and are never used to tune tests.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from conftest import ROOT, SCRIPTS, bash_executable, posix, run_checker

pytestmark = pytest.mark.integration

CASES = ROOT / "scenario" / "cases"
EXPECTED_STATUS = {"break": "SILENT_BREAK", "safe": "SAFE", "conflict": "TEXT_CONFLICT"}


def read_case(case_id: str) -> dict:
    values = {}
    for line in (CASES / case_id / "case.env").read_text().splitlines():
        if line and not line.startswith("#"):
            key, _, value = line.partition("=")
            values[key] = value
    return values


DEV = sorted(p.name for p in CASES.iterdir() if read_case(p.name)["SPLIT"] == "dev")


@pytest.fixture(scope="module")
def scenarios(tmp_path_factory) -> Path:
    out = tmp_path_factory.mktemp("scenarios")
    done = subprocess.run([bash_executable(), posix(SCRIPTS / "make-fixtures.sh"), "--out", posix(out),
                           "--split", "dev"], capture_output=True, text=True)
    assert done.returncode == 0, done.stderr
    return out


def heads(repo: Path) -> str:
    return subprocess.run(["git", "-C", str(repo), "for-each-ref", "--format=%(refname) %(objectname)"],
                          capture_output=True, text=True, check=True).stdout


def test_dev_set_shape():
    labels = [read_case(c)["LABEL"] for c in DEV]
    assert len(DEV) == 12
    assert (labels.count("break"), labels.count("safe"), labels.count("conflict")) == (6, 4, 2)


def test_generator_is_deterministic(scenarios, tmp_path):
    again = tmp_path / "again"
    subprocess.run([bash_executable(), posix(SCRIPTS / "make-fixtures.sh"), "--out", posix(again), "c05", "c13"],
                   capture_output=True, text=True, check=True)
    for case_id in ("c05", "c13"):
        assert heads(again / case_id) == heads(scenarios / case_id)


def test_miniapp_holds_the_three_c2_pairs(scenarios):
    branches = subprocess.run(["git", "-C", str(scenarios / "miniapp"), "branch", "--format=%(refname:short)"],
                              capture_output=True, text=True, check=True).stdout.split()
    assert sorted(branches) == sorted(["main", "r1-remove-function", "r1-old-caller", "r2-api-change",
                                       "r2-new-caller", "r3-delete-module", "r3-old-import"])


@pytest.mark.parametrize("case_id", DEV)
def test_checker_matches_development_label(scenarios, case_id, tmp_path):
    case = read_case(case_id)
    code, report, done = run_checker(scenarios / case_id, case["BRANCH_A"], case["BRANCH_B"], out_dir=tmp_path)
    assert report["status"] == EXPECTED_STATUS[case["LABEL"]], done.stdout
    if case["LABEL"] == "break":
        (finding,) = report["findings"]
        assert finding["rule_id"] == case["RULE"]
        assert finding["file"] == case["EXPECT_FILE"]
        assert finding["provenance"]["use"]["branch"] == case["EXPECT_CALLER"]
    if case["LABEL"] == "conflict":
        assert case["EXPECT_FILE"] in report["merge"]["conflicts"]
