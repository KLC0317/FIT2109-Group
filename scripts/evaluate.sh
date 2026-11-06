#!/usr/bin/env bash
# Evaluation: baseline, Pylint and the checker on the labelled branch pairs.
#
# Usage: bash scripts/evaluate.sh [--split dev|holdout|all] [--no-errors]
#
# Rebuilds the fixture repositories, verifies the holdout freeze, then runs
# the harness (python -m smc_eval). Results go to out/eval/<split>/:
# results.json, cases.csv and summary.md. Exit 1 if any label or error
# input does not behave as recorded.
set -euo pipefail

ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
# shellcheck source=scripts/lib/common.sh
source "$ROOT/scripts/lib/common.sh"

split=all
extra=()
while (( $# > 0 )); do
    case "$1" in
        --split) split=${2:?--split needs dev, holdout or all}; shift 2 ;;
        --no-errors) extra+=(--no-errors); shift ;;
        *) die "unknown option: $1" ;;
    esac
done

PY=$(smc_python) || die "python 3.12 not found (run scripts/setup.sh)"
"$PY" -c 'import pylint' 2>/dev/null || die "pylint not installed (run scripts/setup.sh)"

if [[ "$split" != dev ]]; then
    bash "$ROOT/scripts/freeze-holdout.sh" --check
fi
echo "== building fixtures =="
bash "$ROOT/scripts/make-fixtures.sh" --split "$split" | tail -n 1

if [[ -z "${SMC_BASH:-}" ]] && command -v cygpath >/dev/null 2>&1; then
    export SMC_BASH="$(cygpath -w "$BASH")"
fi
echo "== evaluating ($split) =="
PYTHONPATH="$(native_path "$ROOT/src")" "$PY" -m smc_eval evaluate \
    --scenarios "$(native_path "$ROOT/out/scenarios")" --out "$(native_path "$ROOT/out/eval/$split")" \
    --split "$split" "${extra[@]+"${extra[@]}"}"
