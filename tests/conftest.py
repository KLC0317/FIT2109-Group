"""Shared fixtures: Bash runner, deterministic Git repositories, repository fingerprints."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

from smc_eval.gitrepo import Repo, isolated_env

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
CHECKER = SCRIPTS / "silent-merge-check.sh"


def bash_executable() -> str:
    found = os.environ.get("SMC_BASH") or shutil.which("bash")
    if not found:
        pytest.skip("bash not available")
    return found


def posix(path: Path) -> str:
    """Path form that Git Bash and Linux bash both accept."""
    return Path(path).as_posix()


def run_bash(script: str, *args: str, cwd: Path | None = None, env: dict | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(
        [bash_executable(), "-c", script, "bash", *args],
        cwd=cwd, env=env, capture_output=True, text=True, encoding="utf-8",
    )


@pytest.fixture
def git_env(tmp_path_factory) -> dict:
    """Environment that ignores the developer's global and system Git config."""
    return isolated_env(tmp_path_factory.mktemp("gitconfig") / "empty.gitconfig")


@pytest.fixture
def make_repo(tmp_path, git_env):
    def factory(name: str = "repo") -> Repo:
        return Repo(tmp_path / name, git_env)
    return factory


def fingerprint(path: Path) -> dict[str, str]:
    """Hash of every file in the working tree and the .git directory."""
    result = {}
    for item in sorted(Path(path).rglob("*")):
        if item.is_file():
            result[item.relative_to(path).as_posix()] = hashlib.sha256(item.read_bytes()).hexdigest()
    return result


def run_checker(repo: Path, *refs: str, args: tuple = (), out_dir: Path, env: dict | None = None):
    """Run silent-merge-check.sh; return (exit code, report dict, completed process)."""
    report = Path(out_dir) / "report.json"
    done = subprocess.run(
        [bash_executable(), posix(CHECKER), "--repo", posix(repo), "--out-dir", posix(out_dir),
         "--json", posix(report), *args, *refs],
        capture_output=True, text=True, encoding="utf-8", env={**os.environ, **(env or {})},
    )
    data = json.loads(report.read_text(encoding="utf-8")) if report.exists() else None
    return done.returncode, data, done
