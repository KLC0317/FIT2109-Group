"""Evaluation harness (proposal Section 5).

For every labelled branch pair it records, on the same frozen pair:

* ground truth: the case's smoke assertion on the caller branch and on the
  trial merge (independent of the checker and the baseline);
* baseline: Git trial merge, then the fixture's existing tests;
* existing-tool reference: pylint --errors-only on the clean merged tree;
* checker: scripts/silent-merge-check.sh.

Fixture code (tests, smoke assertions) runs only inside scratch clones under
the harness's work directory.
"""

from __future__ import annotations

import json
import os
import shutil
import stat
import subprocess
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CASES = ROOT / "scenario" / "cases"
CHECKER = ROOT / "scripts" / "silent-merge-check.sh"


def read_case(case_dir: Path) -> dict:
    values = {}
    for line in (case_dir / "case.env").read_text(encoding="utf-8").splitlines():
        if line and not line.startswith("#"):
            key, _, value = line.partition("=")
            values[key.strip()] = value.strip()
    return values


def bash() -> str:
    return os.environ.get("SMC_BASH") or shutil.which("bash") or "bash"


def run(cmd: list[str], cwd: Path | None = None, env: dict | None = None, timeout: int = 300):
    return subprocess.run(cmd, cwd=cwd, env=env, capture_output=True, text=True, encoding="utf-8",
                          errors="replace", timeout=timeout)


def _force_remove(path: Path) -> None:
    def onexc(func, target, _exc):
        os.chmod(target, stat.S_IWRITE)  # Git object files are read-only on Windows
        func(target)

    if path.exists():
        shutil.rmtree(path, onexc=onexc)


@dataclass
class CaseResult:
    id: str
    label: str
    rule: str
    split: str
    tests_cover: bool
    base_defect: bool
    expect_file: str
    expect_caller: str
    # ground truth
    merge: str = ""  # clean | conflict
    smoke_caller: int | None = None
    smoke_merged: int | None = None
    label_verified: bool = False
    # baseline
    baseline_tests: str = ""  # pass | fail | not run
    baseline_prediction: str = ""
    # pylint
    pylint_messages: list = field(default_factory=list)
    pylint_prediction: str = ""
    pylint_hits_expected_file: bool = False
    # checker
    checker_status: str = ""
    checker_exit: int | None = None
    checker_findings: list = field(default_factory=list)
    attribution_correct: bool | None = None
    checker_seconds: float = 0.0


class Harness:
    def __init__(self, scenarios: Path, work: Path, python: str = sys.executable):
        self.scenarios = Path(scenarios)
        self.work = Path(work)
        self.python = python
        self.env = {**os.environ, "PYTHONDONTWRITEBYTECODE": "1"}
        self.env.pop("PYTHONPATH", None)

    # -- helpers ------------------------------------------------------------------
    def git(self, repo: Path, *args: str, check: bool = True):
        done = run(["git", "-C", str(repo), "-c", "user.name=eval", "-c", "user.email=eval@localhost",
                    "-c", "core.hooksPath=", *args], env=self.env)
        if check and done.returncode != 0:
            raise RuntimeError(f"git {' '.join(args)}: {done.stderr}")
        return done

    def smoke(self, tree: Path, case_dir: Path) -> int | None:
        smoke = case_dir / "smoke.py"
        if not smoke.exists():
            return None
        done = subprocess.run([self.python, "-"], input=smoke.read_text(encoding="utf-8"), cwd=tree,
                              env=self.env, capture_output=True, text=True, timeout=120)
        return done.returncode

    def unit_tests(self, tree: Path) -> str:
        done = run([self.python, "-m", "unittest", "discover", "-s", "tests", "-t", "."], cwd=tree, env=self.env)
        return "pass" if done.returncode == 0 else "fail"

    def pylint(self, tree: Path) -> list[dict]:
        done = run([self.python, "-m", "pylint", "--errors-only", "--output-format=json",
                    "--recursive=y", "--persistent=n", "."], cwd=tree, env=self.env)
        try:
            messages = json.loads(done.stdout or "[]")
        except json.JSONDecodeError:
            raise RuntimeError(f"pylint failed: {done.stderr[-500:]}")
        return [{"file": m["path"].replace("\\", "/"), "line": m["line"], "id": m["message-id"],
                 "symbol": m["symbol"], "message": m["message"]} for m in messages]

    # -- one case -----------------------------------------------------------------
    def evaluate(self, case_dir: Path) -> CaseResult:
        case = read_case(case_dir)
        result = CaseResult(
            id=case["ID"], label=case["LABEL"], rule=case["RULE"], split=case["SPLIT"],
            tests_cover=case["TESTS_COVER"] == "yes", base_defect=case["BASE_DEFECT"] == "yes",
            expect_file=case["EXPECT_FILE"], expect_caller=case["EXPECT_CALLER"],
        )
        repo = self.scenarios / result.id
        branch_a, branch_b = case["BRANCH_A"], case["BRANCH_B"]
        caller = branch_a if result.expect_caller == "a" else branch_b
        clone = self.work / result.id
        _force_remove(clone)
        run(["git", "clone", "-q", str(repo), str(clone)], env=self.env)
        for ref in (branch_a, branch_b):
            self.git(clone, "branch", "-q", "-f", ref, f"origin/{ref}", check=False)

        # Ground truth: smoke assertion on the caller branch.
        self.git(clone, "checkout", "-q", caller)
        result.smoke_caller = self.smoke(clone, case_dir)

        # Trial merge used by the ground truth, the baseline and Pylint.
        self.git(clone, "checkout", "-q", branch_a)
        merged = self.git(clone, "merge", "--no-commit", "--no-ff", branch_b, check=False)
        unmerged = self.git(clone, "ls-files", "-u").stdout.strip()
        if unmerged or merged.returncode != 0:
            result.merge = "conflict"
            result.baseline_tests = "not run"
            result.baseline_prediction = "TEXT_CONFLICT"
            result.pylint_prediction = "not run"
        else:
            result.merge = "clean"
            result.smoke_merged = self.smoke(clone, case_dir)
            result.baseline_tests = self.unit_tests(clone)
            result.baseline_prediction = "SILENT_BREAK" if result.baseline_tests == "fail" else "SAFE"
            result.pylint_messages = self.pylint(clone)
            result.pylint_prediction = "SILENT_BREAK" if result.pylint_messages else "SAFE"
            result.pylint_hits_expected_file = any(m["file"] == result.expect_file for m in result.pylint_messages)

        if result.label == "conflict":
            result.label_verified = result.merge == "conflict"
        elif result.label == "break":
            result.label_verified = result.merge == "clean" and result.smoke_caller == 0 and result.smoke_merged != 0
        else:
            result.label_verified = result.merge == "clean" and result.smoke_merged == 0

        # The checker, on the generated repository (not the scratch clone).
        report = self.work / f"{result.id}.report.json"
        import time

        start = time.perf_counter()
        done = run([bash(), CHECKER.as_posix(), "--repo", repo.as_posix(), "--out-dir", (self.work / "checker").as_posix(),
                    "--json", report.as_posix(), "--quiet", branch_a, branch_b], env=self.env)
        result.checker_seconds = round(time.perf_counter() - start, 3)
        result.checker_exit = done.returncode
        data = json.loads(report.read_text(encoding="utf-8"))
        result.checker_status = data["status"]
        result.checker_findings = [
            {"rule": f["rule_id"], "file": f["file"], "line": f["line"],
             "caller": f["provenance"]["use"]["branch"], "message": f["message"]}
            for f in data["findings"]
        ]
        if result.label == "break" and result.checker_status == "SILENT_BREAK":
            result.attribution_correct = any(
                f["rule"] == result.rule and f["file"] == result.expect_file and f["caller"] == result.expect_caller
                for f in result.checker_findings
            )
        _force_remove(clone)
        return result

    def evaluate_errors(self) -> list[dict]:
        from smc_eval.error_inputs import build_all

        directory = self.work / "errors"
        _force_remove(directory)
        rows = []
        for case in build_all(directory):
            report = self.work / f"{case.id}.report.json"
            done = run([bash(), CHECKER.as_posix(), "--repo", case.repo.as_posix(), "--out-dir",
                        (self.work / "checker").as_posix(), "--json", report.as_posix(), "--quiet",
                        *case.args, *case.refs], env={**self.env, **case.env})
            data = json.loads(report.read_text(encoding="utf-8")) if report.exists() else {}
            rows.append({
                "id": case.id, "description": case.description, "exit": done.returncode,
                "status": data.get("status"), "expected_status": case.expected_status,
                "ok": done.returncode == 3 and data.get("status") == case.expected_status
                      and case.expected_text in json.dumps(data),
            })
        _force_remove(directory)
        return rows


def to_dict(result: CaseResult) -> dict:
    return asdict(result)
