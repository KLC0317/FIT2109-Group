#!/usr/bin/env bash
# Latency measurement: five runs per case, per-stage durations from the logs.
#
# Usage: bash scripts/profile.sh [--runs N]
#
# Builds the 100-file fixture (make-fixtures.sh --latency) and the c05, c13
# and c25 pairs, then writes out/eval/timing/timing.csv (one row per run,
# first run marked), timing.json and timing.md (median, range, same result
# on every run, dominant stage). Then, with timing finished, profiles the
# Python analyser on latency100 with cProfile (out/eval/timing/cprofile.txt).
set -euo pipefail

ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
# shellcheck source=scripts/lib/common.sh
source "$ROOT/scripts/lib/common.sh"

runs=5
[[ "${1:-}" == --runs ]] && runs=${2:?--runs needs a number}

PY=$(smc_python) || die "python 3.12 not found (run scripts/setup.sh)"
bash "$ROOT/scripts/make-fixtures.sh" --latency
bash "$ROOT/scripts/make-fixtures.sh" c05 c13 c25 | tail -n 1
if [[ -z "${SMC_BASH:-}" ]] && command -v cygpath >/dev/null 2>&1; then
    export SMC_BASH="$(cygpath -w "$BASH")"
fi
rm -rf -- "$ROOT/out/eval/timing"
PYTHONPATH="$(native_path "$ROOT/src")" "$PY" -m smc_eval timing --runs "$runs" \
    --scenarios "$(native_path "$ROOT/out/scenarios")" --out "$(native_path "$ROOT/out/eval/timing")" --cprofile
