#!/usr/bin/env bash
# Freeze or verify the holdout fixtures.
#
# Usage: bash scripts/freeze-holdout.sh [--check]
#
# Writes scenario/holdout.lock: a sha256 line for every file of every case
# whose case.env says SPLIT=holdout. With --check, exits 1 if any holdout
# file was added, removed or edited after the freeze. The evaluation harness
# runs the check before it touches the holdout.
set -euo pipefail

ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
lock="$ROOT/scenario/holdout.lock"

current() {
    (
        cd "$ROOT"
        grep -l '^SPLIT=holdout' scenario/cases/*/case.env | xargs -n1 dirname |
            xargs -I{} find {} -type f -not -path '*/__pycache__/*' -print0 |
            LC_ALL=C sort -z | xargs -0 sha256sum | sed 's|^\([0-9a-f]*\) [ *]|\1  |'
    )
}

if [[ "${1:-}" == --check ]]; then
    [[ -f "$lock" ]] || { echo "no holdout.lock: the holdout has not been frozen" >&2; exit 1; }
    if diff <(grep -v '^#' "$lock") <(current) >/dev/null; then
        echo "holdout unchanged since freeze ($(grep -vc '^#' "$lock") files)"
    else
        echo "holdout changed since freeze:" >&2
        diff <(grep -v '^#' "$lock") <(current) >&2 || true
        exit 1
    fi
else
    {
        echo "# Holdout frozen before any checker run on it. Do not edit; see docs/scenario.md."
        current
    } > "$lock"
    echo "froze $(grep -vc '^#' "$lock") holdout files into ${lock#"$ROOT"/}"
fi
