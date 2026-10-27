"""Independent verification of the AI-assisted Bash helper (docs/ai-use.md, activity 2).

M3 checks every filesystem/Git mutation in scripts/lib/workdir.sh: refs,
source roots, work-directory creation with awkward paths, and that removal
can never reach outside the directory it created.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from conftest import SCRIPTS, posix, run_bash

HELPER = posix(SCRIPTS / "lib" / "workdir.sh")


def helper(call: str, *args: str):
    return run_bash(f'source "{HELPER}"; {call}', *args)


def test_helper_parses():
    assert run_bash(f'bash -n "{HELPER}"').returncode == 0


@pytest.mark.parametrize(
    ("given", "expected"),
    [
        (".", "."),
        ("./", "."),
        ("src", "src"),
        ("./src/", "src"),
        ("a/./b", "a/b"),
        ("a\\b", "a/b"),
        ("with space/dir", "with space/dir"),
    ],
)
def test_source_root_is_normalised(given, expected):
    done = helper('smc_check_source_root "$1"', given)
    assert done.returncode == 0
    assert done.stdout.strip() == expected


@pytest.mark.parametrize("given", ["", "..", "../x", "a/../b", "/abs", "C:/x", "c:\\x"])
def test_source_root_rejects_escapes(given):
    assert helper('smc_check_source_root "$1"', given).returncode != 0


def test_resolve_commit(make_repo):
    repo = make_repo()
    repo.write({"a.py": "x = 1\n"})
    head = repo.commit("base")
    repo.git("tag", "v1")
    done = helper('smc_resolve_commit "$1" "$2"', posix(repo.path), "v1")
    assert done.returncode == 0 and done.stdout.strip() == head


@pytest.mark.parametrize("ref", ["", "-x", "--all", "main extra", "main\tx", "no-such-branch"])
def test_resolve_commit_rejects_bad_refs(make_repo, ref):
    repo = make_repo()
    repo.commit("base")
    assert helper('smc_resolve_commit "$1" "$2"', posix(repo.path), ref).returncode != 0


def test_make_and_remove_workdir_with_spaces(tmp_path):
    base = tmp_path / "work base"
    made = helper('smc_make_workdir "$1"', posix(base))
    assert made.returncode == 0
    workdir = made.stdout.strip()
    created = list(base.iterdir())
    assert len(created) == 1 and created[0].name.startswith("run.")
    (created[0] / "nested dir").mkdir()
    (created[0] / "nested dir" / "file name.txt").write_text("x")
    removed = helper('smc_remove_workdir "$1" "$2"', workdir, posix(base))
    assert removed.returncode == 0
    assert list(base.iterdir()) == []


def test_remove_refuses_directory_outside_base(tmp_path):
    base = tmp_path / "base"
    base.mkdir()
    outside = tmp_path / "run.ABCDEF"
    outside.mkdir()
    (outside / "keep.txt").write_text("keep")
    done = helper('smc_remove_workdir "$1" "$2"', posix(outside), posix(base))
    assert done.returncode != 0
    assert (outside / "keep.txt").exists()


def test_remove_refuses_the_base_itself_and_unexpected_names(tmp_path):
    base = tmp_path / "base"
    other = base / "not-a-run"
    other.mkdir(parents=True)
    assert helper('smc_remove_workdir "$1" "$2"', posix(base), posix(base)).returncode != 0
    assert helper('smc_remove_workdir "$1" "$2"', posix(other), posix(base)).returncode != 0
    assert other.exists()


def test_remove_refuses_empty_arguments(tmp_path):
    assert helper('smc_remove_workdir "" "$1"', posix(tmp_path)).returncode != 0
    assert helper('smc_remove_workdir "$1" ""', posix(tmp_path)).returncode != 0
    assert tmp_path.exists()


def test_remove_does_not_follow_symlinks(tmp_path):
    base = tmp_path / "base"
    base.mkdir()
    victim = tmp_path / "victim"
    victim.mkdir()
    (victim / "keep.txt").write_text("keep")
    link = base / "run.LINKED"
    try:
        os.symlink(victim, link, target_is_directory=True)
    except (OSError, NotImplementedError):
        pytest.skip("symlinks not available on this platform/account")
    assert helper('smc_remove_workdir "$1" "$2"', posix(link), posix(base)).returncode != 0
    assert (victim / "keep.txt").exists()


def test_missing_workdir_is_not_an_error(tmp_path):
    done = helper('smc_remove_workdir "$1" "$2"', posix(tmp_path / "run.GONE00"), posix(tmp_path))
    assert done.returncode == 0
    assert Path(tmp_path).exists()
