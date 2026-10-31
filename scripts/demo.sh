#!/usr/bin/env bash
# Demonstration: the current workflow versus silent-merge-check on MiniApp.
#
# Usage: bash scripts/demo.sh [--verbose]
#
# Rebuilds the scenario repositories (scripts/make-fixtures.sh), then for the
# three Appendix C2 pairs in out/scenarios/miniapp, a safe pair (c13) and a
# text conflict (c25):
#   baseline  git trial merge in a scratch clone, then the existing tests
#   checker   scripts/silent-merge-check.sh on the same two branches
# Nothing is merged into any branch; scratch clones live under out/demo.
set -euo pipefail

ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
# shellcheck source=scripts/lib/common.sh
source "$ROOT/scripts/lib/common.sh"
# shellcheck source=scripts/lib/workdir.sh
source "$ROOT/scripts/lib/workdir.sh"

verbose=0
[[ "${1:-}" == --verbose ]] && verbose=1

PY=$(smc_python) || die "python 3.12 not found (run scripts/setup.sh)"
export PYTHONDONTWRITEBYTECODE=1
scenarios="$ROOT/out/scenarios"
demo_base="$ROOT/out/demo"

echo "== Building scenario repositories =="
bash "$ROOT/scripts/make-fixtures.sh" c01 c05 c09 c13 c25 | sed 's/^/  /'

work=$(smc_make_workdir "$demo_base")
trap 'smc_remove_workdir "$work" "$demo_base"' EXIT

# baseline <repo> <ref-a> <ref-b>: prints "<merge> <tests>".
baseline() {
    local clone="$work/baseline-$RANDOM"
    git clone -q "$1" "$clone"
    git -C "$clone" checkout -q "$2"
    if ! git -C "$clone" -c user.name=demo -c user.email=demo@localhost \
            merge -q --no-commit --no-ff "origin/$3" >/dev/null 2>&1; then
        printf 'conflict -'
        return
    fi
    if (cd "$clone" && "$PY" -m unittest discover -s tests -t . -q >/dev/null 2>&1); then
        printf 'clean pass'
    else
        printf 'clean FAIL'
    fi
}

pairs=(
    "miniapp r1-remove-function r1-old-caller break"
    "miniapp r2-api-change r2-new-caller break"
    "miniapp r3-delete-module r3-old-import break"
    "c13 safe-optional-email safe-badge safe"
    "c25 conflict-team-field conflict-email-field conflict"
)

summary=()
for pair in "${pairs[@]}"; do
    read -r repo ref_a ref_b expected <<<"$pair"
    echo
    echo "== $ref_a + $ref_b (expected: $expected) =="
    read -r merge tests <<<"$(baseline "$scenarios/$repo" "$ref_a" "$ref_b")"
    case "$merge/$tests" in
        conflict/-) verdict="conflict reported" ;;
        clean/FAIL) verdict="tests fail" ;;
        *) verdict="merge looks fine" ;;
    esac
    echo "baseline: git merge $merge, existing tests ${tests/-/not run} -> $verdict"
    set +e
    if (( verbose )); then
        bash "$ROOT/scripts/silent-merge-check.sh" --repo "$scenarios/$repo" "$ref_a" "$ref_b"
    else
        bash "$ROOT/scripts/silent-merge-check.sh" --repo "$scenarios/$repo" "$ref_a" "$ref_b" |
            grep -E '^silent-merge-check:|^\[R[123]\]|^  reason:|^report:'
    fi
    status=${PIPESTATUS[0]}
    set -e
    case $status in
        0) checker=SAFE ;; 1) checker="SILENT BREAK" ;; 2) checker="TEXT CONFLICT" ;; *) checker=INCONCLUSIVE ;;
    esac
    summary+=("$(printf '%-44s %-9s %-18s %s' "$ref_a + $ref_b" "$expected" "$verdict" "$checker (exit $status)")")
done

echo
echo "== Summary =="
printf '%-44s %-9s %-18s %s\n' "pair" "expected" "baseline" "checker"
printf '%s\n' "${summary[@]}"
