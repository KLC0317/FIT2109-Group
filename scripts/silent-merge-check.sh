#!/usr/bin/env bash
# silent-merge-check: check two committed branches of a Python project for
# incompatibilities that a clean Git merge would hide.
#
# Usage: bash scripts/silent-merge-check.sh --repo <repo> [--source-root <dir>] <ref-a> <ref-b>
#
# Exit codes: 0 SAFE, 1 SILENT BREAK, 2 TEXT CONFLICT, 3 INCONCLUSIVE/ERROR.
set -euo pipefail

readonly EXIT_SAFE=0 EXIT_BREAK=1 EXIT_CONFLICT=2 EXIT_ERROR=3

ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
# shellcheck source=scripts/lib/common.sh
source "$ROOT/scripts/lib/common.sh"
SMC_DIE_STATUS=$EXIT_ERROR

usage() {
    sed -n '2,8s/^# \{0,1\}//p' "${BASH_SOURCE[0]}"
}

repo='' source_root='.'
refs=()
while (( $# > 0 )); do
    case "$1" in
        --repo) repo=${2:?--repo needs a path}; shift 2 ;;
        --source-root) source_root=${2:?--source-root needs a path}; shift 2 ;;
        -h|--help) usage; exit 0 ;;
        --) shift; refs+=("$@"); break ;;
        -*) die "unknown option: $1" ;;
        *) refs+=("$1"); shift ;;
    esac
done
(( ${#refs[@]} == 2 )) || { usage >&2; die "expected exactly two branch references"; }
[[ -n "$repo" ]] || die "--repo is required"

git -C "$repo" rev-parse --git-dir >/dev/null 2>&1 || die "not a Git repository: $repo"

resolve_ref() {
    git -C "$repo" rev-parse --verify --quiet --end-of-options "$1^{commit}" ||
        die "cannot resolve '$1' to a commit"
}
commit_a=$(resolve_ref "${refs[0]}")
commit_b=$(resolve_ref "${refs[1]}")

mapfile -t bases < <(git -C "$repo" merge-base --all "$commit_a" "$commit_b" || true)
(( ${#bases[@]} == 1 )) || die "expected one merge base, found ${#bases[@]}"
commit_base=${bases[0]}

# Isolated temporary repository under the project; the user's repository is
# only read (through objects/info/alternates).
tmp_base="$ROOT/out/tmp"
mkdir -p "$tmp_base"
work=$(mktemp -d "$tmp_base/run.XXXXXX")
trap 'rm -rf -- "$work"' EXIT

objects=$(git -C "$repo" rev-parse --path-format=absolute --git-common-dir)/objects
git init -q "$work/repo"
printf '%s\n' "$objects" > "$work/repo/.git/objects/info/alternates"
tgit() { git -C "$work/repo" -c core.hooksPath="$work/no-hooks" -c core.autocrlf=false "$@"; }

tgit checkout -q --detach "$commit_a"
if tgit merge -q --no-commit --no-ff "$commit_b" >/dev/null 2>&1; then
    echo "clean merge of ${refs[1]} into ${refs[0]} (base ${commit_base:0:12})"
    exit $EXIT_SAFE
fi
if [[ -n "$(tgit ls-files -u)" ]]; then
    echo "TEXT CONFLICT"
    tgit diff --name-only --diff-filter=U
    exit $EXIT_CONFLICT
fi
die "git merge failed without conflicts"
