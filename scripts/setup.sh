#!/usr/bin/env bash
# One-time setup: project-local virtual environment with pinned packages.
#
# Usage: bash scripts/setup.sh
#
# Creates .venv with Python 3.12 and installs requirements.txt (pytest and
# pylint; the checker itself needs only the standard library). Prints the
# Git, Bash and Python versions it found. Run from anywhere; nothing is
# installed outside the project directory.
set -euo pipefail

ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
# shellcheck source=scripts/lib/common.sh
source "$ROOT/scripts/lib/common.sh"

command -v git >/dev/null || die "git not found"
git_version=$(git --version | tr -d '\r')
git_minor=$(sed -E 's/^git version ([0-9]+)\.([0-9]+).*/\1 \2/' <<<"$git_version")
read -r major minor <<<"$git_minor"
(( major > 2 || (major == 2 && minor >= 38) )) || die "Git 2.38 or newer is required ($git_version)"

base_python=''
for candidate in "${SMC_PYTHON:-}" python3.12 python3 python; do
    [[ -n "$candidate" ]] || continue
    if command -v "$candidate" >/dev/null 2>&1 &&
       "$candidate" -c 'import sys; sys.exit(sys.version_info[:2] != (3, 12))' 2>/dev/null; then
        base_python=$candidate
        break
    fi
done
[[ -n "$base_python" ]] || die "Python 3.12 not found (set SMC_PYTHON to its path)"

if [[ ! -d "$ROOT/.venv" ]]; then
    echo "creating .venv with $base_python"
    "$base_python" -m venv "$ROOT/.venv"
fi
PY=$(smc_python) || die "the virtual environment in .venv is not Python 3.12; delete it and re-run"
"$PY" -m pip install --quiet --disable-pip-version-check -r "$(native_path "$ROOT/requirements.txt")"

echo "bash:   ${BASH_VERSION}"
echo "git:    ${git_version#git version }"
echo "python: $("$PY" --version 2>&1 | tr -d '\r') ($PY)"
echo "pytest: $("$PY" -m pytest --version 2>&1 | tr -d '\r' | head -n 1)"
echo "pylint: $("$PY" -m pylint --version 2>&1 | tr -d '\r' | head -n 1)"
echo "setup complete"
