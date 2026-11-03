"""Deterministic Git repositories for tests and error inputs."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

IDENTITIES = {
    "base": ("Base Maintainer", "base@example.com"),
    "a": ("Developer A", "developer.a@example.com"),
    "b": ("Developer B", "developer.b@example.com"),
}


def isolated_env(empty_config: Path) -> dict:
    """Environment that ignores the developer's global and system Git config."""
    empty_config.parent.mkdir(parents=True, exist_ok=True)
    empty_config.touch()
    env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
    env.update({"GIT_CONFIG_GLOBAL": str(empty_config), "GIT_CONFIG_NOSYSTEM": "1",
                "PYTHONDONTWRITEBYTECODE": "1"})
    return env


class Repo:
    """A Git repository with fixed identities and commit dates."""

    def __init__(self, path: Path, env: dict):
        self.path = Path(path)
        self.env = env
        self.tick = 0
        self.path.mkdir(parents=True, exist_ok=True)
        self.git("init", "-q", "-b", "main")
        self.git("config", "core.autocrlf", "false")

    def git(self, *args: str, check: bool = True) -> str:
        done = subprocess.run(["git", "-C", str(self.path), *args], env=self.env,
                              capture_output=True, text=True, encoding="utf-8")
        if check and done.returncode != 0:
            raise RuntimeError(f"git {' '.join(args)} failed: {done.stderr}")
        return done.stdout.strip()

    def write(self, files: dict[str, str]) -> None:
        for rel, text in files.items():
            target = self.path / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(text, encoding="utf-8", newline="\n")

    def delete(self, *paths: str) -> None:
        for rel in paths:
            self.git("rm", "-q", "-r", "--", rel)

    def _identity_env(self, who: str) -> dict:
        self.tick += 1
        name, email = IDENTITIES[who]
        stamp = f"2026-10-01T{self.tick // 60:02d}:{self.tick % 60:02d}:00+08:00"
        return {**self.env, "GIT_AUTHOR_NAME": name, "GIT_AUTHOR_EMAIL": email, "GIT_AUTHOR_DATE": stamp,
                "GIT_COMMITTER_NAME": name, "GIT_COMMITTER_EMAIL": email, "GIT_COMMITTER_DATE": stamp}

    def commit(self, message: str, who: str = "base") -> str:
        self.git("add", "-A")
        return self.commit_index(message, who)

    def commit_index(self, message: str, who: str = "base") -> str:
        """Commit exactly what is staged (e.g. a gitlink added with update-index)."""
        subprocess.run(["git", "-C", str(self.path), "commit", "-q", "--allow-empty", "-m", message],
                       env=self._identity_env(who), check=True, capture_output=True)
        return self.git("rev-parse", "HEAD")

    def merge(self, ref: str, who: str = "base") -> str:
        subprocess.run(["git", "-C", str(self.path), "merge", "-q", "--no-ff", "--no-edit", ref],
                       env=self._identity_env(who), check=True, capture_output=True)
        return self.git("rev-parse", "HEAD")

    def branch(self, name: str, start: str = "main") -> None:
        self.git("checkout", "-q", "-b", name, start)

    def checkout(self, name: str) -> None:
        self.git("checkout", "-q", name)
