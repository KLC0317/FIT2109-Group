#!/usr/bin/env bash
# Clean-archive check: setup, demo and tests from a fresh export of HEAD.
#
# Usage: bash scripts/check-archive.sh [--setup] [<commit>]
#
# Extracts `git archive <commit>` (default HEAD) into out/archive-check/,
# confirms the archive contains no nested .git directories and no generated
# files, then runs demo.sh and test.sh inside the extracted copy. --setup
# also runs setup.sh there (needs network access or a pip cache); without
# it the copy reuses this project's .venv through SMC_PYTHON.
set -euo pipefail

ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
# shellcheck source=scripts/lib/common.sh
source "$ROOT/scripts/lib/common.sh"
# shellcheck source=scripts/lib/workdir.sh
source "$ROOT/scripts/lib/workdir.sh"

run_setup=0
[[ "${1:-}" == --setup ]] && { run_setup=1; shift; }
commit=${1:-HEAD}
git -C "$ROOT" rev-parse --verify --quiet "$commit^{commit}" >/dev/null || die "unknown commit: $commit"

base="$ROOT/out/archive-check"
work=$(smc_make_workdir "$base")
trap 'smc_remove_workdir "$work" "$base"' EXIT
copy="$work/project"
mkdir -p "$copy"
git -C "$ROOT" archive --format=tar "$commit" | tar -x -m -C "$copy"
echo "== archive of $(git -C "$ROOT" rev-parse --short "$commit") in ${copy#"$ROOT"/} =="

nested=$(find "$copy" -name .git -print)
[[ -z "$nested" ]] || die "archive contains nested .git: $nested"
for unwanted in out .venv __pycache__; do
    [[ -z "$(find "$copy" -name "$unwanted" -print -quit)" ]] || die "archive contains $unwanted"
done
echo "no nested .git, no generated files"

if (( run_setup )); then
    bash "$copy/scripts/setup.sh"
else
    SMC_PYTHON=$(smc_python) || die "python 3.12 not found (run scripts/setup.sh first)"
    export SMC_PYTHON
    echo "reusing $SMC_PYTHON"
fi

echo "== demo =="
bash "$copy/scripts/demo.sh" | sed -n '/== Summary ==/,$p'
echo "== tests =="
bash "$copy/scripts/test.sh" -q | tail -n 3
echo "clean-archive check passed"
