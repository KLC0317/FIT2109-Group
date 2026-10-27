"""Shared fixtures: Bash runner, deterministic Git repositories, repository fingerprints."""

from __future__ import annotations

import hashlib
import os
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
CHECKER = SCRIPTS / "silent-merge-check.sh"

IDENTITIES = {
    "base": ("Base Maintainer", "base@example.com"),
    "a": ("Developer A", "developer.a@example.com"),
    "b": ("Developer B", "developer.b@example.com"),
}


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


class Repo:
    """A Git repository with deterministic identities and dates."""

    def __init__(self, path: Path, env: dict):
        self.path = Path(path)
        self.env = env
        self.tick = 0
        self.path.mkdir(parents=True, exist_ok=True)
        self.git("init", "-q", "-b", "main")
        self.git("config", "core.autocrlf", "false")

    def git(self, *args: str, check: bool = True) -> str:
        done = subprocess.run(
            ["git", "-C", str(self.path), *args],
            env=self.env, capture_output=True, text=True, encoding="utf-8",
        )
        if check and done.returncode != 0:
            raise AssertionError(f"git {' '.join(args)} failed: {done.stderr}")
        return done.stdout.strip()

    def write(self, files: dict[str, str]) -> None:
        for rel, text in files.items():
            target = self.path / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(text, encoding="utf-8", newline="\n")

    def delete(self, *paths: str) -> None:
        for rel in paths:
            self.git("rm", "-q", "-r", "--", rel)

    def commit(self, message: str, who: str = "base") -> str:
        self.tick += 1
        name, email = IDENTITIES[who]
        stamp = f"2026-10-01T00:{self.tick:02d}:00+08:00"
        self.git("add", "-A")
        subprocess.run(
            ["git", "-C", str(self.path), "commit", "-q", "--allow-empty", "-m", message],
            env={**self.env, "GIT_AUTHOR_NAME": name, "GIT_AUTHOR_EMAIL": email, "GIT_AUTHOR_DATE": stamp,
                 "GIT_COMMITTER_NAME": name, "GIT_COMMITTER_EMAIL": email, "GIT_COMMITTER_DATE": stamp},
            check=True, capture_output=True,
        )
        return self.git("rev-parse", "HEAD")

    def branch(self, name: str, start: str = "main") -> None:
        self.git("checkout", "-q", "-b", name, start)

    def checkout(self, name: str) -> None:
        self.git("checkout", "-q", name)


@pytest.fixture
def git_env(tmp_path_factory) -> dict:
    """Environment that ignores the developer's global and system Git config."""
    home = tmp_path_factory.mktemp("gitconfig")
    empty = home / "empty.gitconfig"
    empty.write_text("")
    env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
    env.update({"GIT_CONFIG_GLOBAL": str(empty), "GIT_CONFIG_NOSYSTEM": "1", "PYTHONDONTWRITEBYTECODE": "1"})
    return env


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
