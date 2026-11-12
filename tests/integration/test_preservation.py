"""The user's repository is read, never written.

For SILENT BREAK, SAFE, TEXT CONFLICT, INCONCLUSIVE and ERROR runs, the
working tree, index, HEAD, refs, stash, config and every object file must be
byte-for-byte identical afterwards, including uncommitted and untracked
work, and the temporary work directory must be gone.
"""

from __future__ import annotations

import json
import os
import signal
import subprocess
import sys
import time

import pytest

from conftest import CHECKER, bash_executable, fingerprint, posix, run_checker

pytestmark = pytest.mark.integration

USERS = "def get_user(user_id):\n    return {'id': user_id}\n"
USERS_REQUIRED = "def get_user(user_id, include_email):\n    return {'id': user_id}\n"
BADGE = "from app.users import get_user\n\n\ndef badge(u):\n    return get_user(u)\n"


@pytest.fixture
def repo(make_repo):
    r = make_repo()
    r.write({"app/__init__.py": "", "app/users.py": USERS, "notes.txt": "base\n"})
    r.commit("base")
    r.branch("api")
    r.write({"app/users.py": USERS_REQUIRED})
    r.commit("required include_email", "a")
    r.branch("caller", "main")
    r.write({"app/badge.py": BADGE})
    r.commit("badge", "b")
    r.branch("safe", "main")
    r.write({"app/other.py": "x = 1\n"})
    r.commit("unrelated", "b")
    r.branch("clash", "main")
    r.write({"app/users.py": USERS.replace("'id'", "'key'")})
    r.commit("clash", "b")
    r.branch("broken", "main")
    r.write({"app/broken.py": "def oops(:\n"})
    r.commit("syntax error", "b")
    r.checkout("caller")
    # Uncommitted work of every kind: unstaged, staged and untracked.
    r.write({"notes.txt": "edited but not staged\n", "scratch.py": "untracked = True\n"})
    r.write({"app/badge.py": BADGE + "# staged edit\n"})
    r.git("add", "app/badge.py")
    return r


def leftover_workdirs(out):
    tmp = out / "tmp"
    return list(tmp.glob("run.*")) if tmp.exists() else []


@pytest.mark.parametrize(
    ("refs", "expected_code", "expected_status"),
    [
        (("api", "caller"), 1, "SILENT_BREAK"),
        (("caller", "api"), 1, "SILENT_BREAK"),
        (("api", "safe"), 0, "SAFE"),
        (("api", "clash"), 2, "TEXT_CONFLICT"),
        (("api", "broken"), 3, "INCONCLUSIVE"),
        (("api", "no-such-ref"), 3, "ERROR"),
    ],
)
def test_repository_is_unchanged(repo, tmp_path, refs, expected_code, expected_status):
    before = fingerprint(repo.path)
    head_before = repo.git("rev-parse", "--symbolic-full-name", "HEAD")
    out = tmp_path / "out"
    code, report, done = run_checker(repo.path, *refs, out_dir=out)
    assert (code, report["status"]) == (expected_code, expected_status), done.stderr
    assert fingerprint(repo.path) == before
    assert repo.git("rev-parse", "--symbolic-full-name", "HEAD") == head_before
    assert leftover_workdirs(out) == []


def test_uncommitted_changes_are_reported_as_excluded(repo, tmp_path):
    _, report, _ = run_checker(repo.path, "api", "caller", out_dir=tmp_path / "out")
    assert any("uncommitted change" in note for note in report["notes"])
    # The staged edit to badge.py is not part of the analysed state.
    assert report["findings"][0]["use"] == "get_user(u)"
    assert report["findings"][0]["line"] == 5


def test_output_inside_the_working_tree_is_refused(repo, tmp_path):
    before = fingerprint(repo.path)
    code, report, done = run_checker(repo.path, "api", "caller", out_dir=repo.path / "smc-out")
    assert code == 3 and report is None
    assert "inside the working tree" in done.stderr
    assert fingerprint(repo.path) == before


def test_output_inside_the_working_tree_is_allowed_when_ignored(repo, tmp_path):
    (repo.path / ".git" / "info" / "exclude").write_text("smc-out/\n")
    code, report, _ = run_checker(repo.path, "api", "caller", out_dir=repo.path / "smc-out")
    assert code == 1 and report["status"] == "SILENT_BREAK"
    assert "smc-out" not in repo.git("status", "--porcelain")


def test_hooks_in_the_user_repository_never_run(repo, tmp_path):
    marker = tmp_path / "hook-ran"
    for hook in ("pre-merge-commit", "post-merge", "post-checkout", "prepare-commit-msg"):
        path = repo.path / ".git" / "hooks" / hook
        path.write_text("#!/bin/sh\ntouch '" + posix(marker) + "'\n")
        path.chmod(0o755)
    run_checker(repo.path, "api", "caller", out_dir=tmp_path / "out")
    run_checker(repo.path, "api", "safe", out_dir=tmp_path / "out")
    assert not marker.exists()


def test_paths_with_spaces(make_repo, tmp_path):
    r = make_repo("repo with spaces")
    r.write({"src dir/app/__init__.py": "", "src dir/app/users.py": USERS})
    r.commit("base")
    r.branch("a")
    r.write({"src dir/app/users.py": USERS_REQUIRED})
    r.commit("a", "a")
    r.branch("b", "main")
    r.write({"src dir/app/badge.py": BADGE})
    r.commit("b", "b")
    code, report, done = run_checker(r.path, "a", "b", args=("--source-root", "src dir"),
                                     out_dir=tmp_path / "out dir")
    assert code == 1, done.stderr
    assert report["findings"][0]["file"] == "src dir/app/badge.py"


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX signals")
def test_sigterm_cleans_up(repo, tmp_path):
    out = tmp_path / "out"
    before = fingerprint(repo.path)
    proc = subprocess.Popen([bash_executable(), posix(CHECKER), "--repo", posix(repo.path),
                             "--out-dir", posix(out), "--quiet", "api", "caller"],
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    deadline = time.time() + 20
    while time.time() < deadline and not leftover_workdirs(out):
        if proc.poll() is not None:
            pytest.skip("run finished before the signal could be sent")
        time.sleep(0.005)
    os.kill(proc.pid, signal.SIGTERM)
    assert proc.wait(timeout=30) == 143
    assert leftover_workdirs(out) == []
    assert fingerprint(repo.path) == before


def test_debug_log_records_each_decision(repo, tmp_path):
    log = tmp_path / "run.jsonl"
    code, report, _ = run_checker(repo.path, "api", "caller", args=("--debug", "--log", posix(log)),
                                  out_dir=tmp_path / "out")
    assert code == 1
    records = [json.loads(line) for line in log.read_text(encoding="utf-8").splitlines()]
    decisions = [r for r in records if r.get("event") == "decision"]
    assert [(d["file"], d["outcome"]) for d in decisions] == [("app/badge.py", "finding")]
    assert {r["component"] for r in records} == {"orchestrator", "analyser"}
