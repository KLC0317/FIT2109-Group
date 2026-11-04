#!/usr/bin/env bash
# Run the full test suite.
#
# Usage: bash scripts/test.sh [--unit] [pytest args...]
#
#   1. bash -n on every script (and shellcheck when it is installed)
#   2. pytest: parser/rule unit tests and real Git integration tests,
#      including repository preservation after success, conflicts and errors
#
# --unit skips the integration tests. Temporary files go to out/pytest-tmp.
set -euo pipefail

ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
# shellcheck source=scripts/lib/common.sh
source "$ROOT/scripts/lib/common.sh"

PY=$(smc_python) || die "python 3.12 not found (run scripts/setup.sh)"
"$PY" -c 'import pytest' 2>/dev/null || die "pytest not installed (run scripts/setup.sh)"

pytest_args=()
if [[ "${1:-}" == --unit ]]; then
    pytest_args+=(-m "not integration")
    shift
fi

echo "== bash -n =="
status=0
for script in "$ROOT"/scripts/*.sh "$ROOT"/scripts/lib/*.sh; do
    if bash -n "$script"; then
        printf '  ok  %s\n' "${script#"$ROOT"/}"
    else
        status=1
    fi
done
if command -v shellcheck >/dev/null 2>&1; then
    echo "== shellcheck =="
    shellcheck -x -S warning "$ROOT"/scripts/*.sh "$ROOT"/scripts/lib/*.sh && echo "  ok"
else
    echo "(shellcheck not installed; skipped)"
fi
(( status == 0 )) || die "syntax errors in scripts"

echo "== pytest =="
# The integration tests call bash by name; on Windows make sure it is this
# Git Bash rather than another bash.exe earlier on PATH.
if [[ -z "${SMC_BASH:-}" ]] && command -v cygpath >/dev/null 2>&1; then
    export SMC_BASH="$(cygpath -w "$BASH")"
fi
export PYTHONDONTWRITEBYTECODE=1
cd "$ROOT"
"$PY" -m pytest -p no:cacheprovider --basetemp="$(native_path "$ROOT/out/pytest-tmp")" "${pytest_args[@]}" "$@"
