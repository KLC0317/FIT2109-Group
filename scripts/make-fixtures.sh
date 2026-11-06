#!/usr/bin/env bash
# Deterministic fixture generator: rebuilds every scenario repository offline.
#
# Usage: bash scripts/make-fixtures.sh [--out <dir>] [--split dev|holdout|all] [--list]
#                                      [--latency] [case-id ...]
#
# For each scenario/cases/<id>/ it creates <out>/<id>/: a Git repository whose
# main branch is the MiniApp base commit (plus scenario/shared/legacy.py when
# BASE_DEFECT=yes) and two branches created from it, BRANCH_A by Developer A
# and BRANCH_B by Developer B, each applying that side's overlay files and
# deletions. It also builds <out>/miniapp, the three Appendix C2 pairs (cases
# c01, c05, c09) in one repository. --latency builds only <out>/latency100,
# the documented 100-file synthetic fixture used for timing. Fixed identities
# and commit dates give the same commit IDs on every machine, so the archive
# needs no nested .git.
set -euo pipefail

ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
# shellcheck source=scripts/lib/common.sh
source "$ROOT/scripts/lib/common.sh"

CASES="$ROOT/scenario/cases"
MINIAPP="$ROOT/scenario/miniapp"
SHARED="$ROOT/scenario/shared"
out="$ROOT/out/scenarios"
split=all
list_only=0
latency=0
selected=()

while (( $# > 0 )); do
    case "$1" in
        --out) out=${2:?--out needs a directory}; shift 2 ;;
        --split) split=${2:?--split needs dev, holdout or all}; shift 2 ;;
        --list) list_only=1; shift ;;
        --latency) latency=1; shift ;;
        -h|--help) sed -n '2,16s/^# \{0,1\}//p' "${BASH_SOURCE[0]}"; exit 0 ;;
        -*) die "unknown option: $1" ;;
        *) selected+=("$1"); shift ;;
    esac
done
[[ "$split" =~ ^(dev|holdout|all)$ ]] || die "--split must be dev, holdout or all"

# load_case <case-dir>: read case.env into CASE_* variables without executing it.
load_case() {
    local key value
    CASE_ID='' CASE_LABEL='' CASE_RULE='' CASE_SPLIT='' CASE_BRANCH_A='' CASE_BRANCH_B=''
    CASE_TESTS_COVER='' CASE_BASE_DEFECT='' CASE_EXPECT_FILE='' CASE_EXPECT_CALLER='' CASE_DESCRIPTION=''
    while IFS='=' read -r key value || [[ -n "$key" ]]; do
        key=${key%$'\r'} value=${value%$'\r'}
        [[ -z "$key" || "$key" == \#* ]] && continue
        case "$key" in
            ID|LABEL|RULE|SPLIT|BRANCH_A|BRANCH_B|TESTS_COVER|BASE_DEFECT|EXPECT_FILE|EXPECT_CALLER|DESCRIPTION)
                printf -v "CASE_$key" '%s' "$value" ;;
            *) die "unknown key '$key' in $1/case.env" ;;
        esac
    done < "$1/case.env"
    [[ "$CASE_ID" == "$(basename "$1")" ]] || die "$1/case.env: ID does not match the directory"
    [[ "$CASE_LABEL" =~ ^(break|safe|conflict)$ ]] || die "$1/case.env: bad LABEL '$CASE_LABEL'"
    [[ "$CASE_SPLIT" =~ ^(dev|holdout)$ ]] || die "$1/case.env: bad SPLIT '$CASE_SPLIT'"
}

empty_config="$out/.empty-gitconfig"
# fgit <repo> <args...>: Git with the developer's own configuration switched off.
fgit() {
    local repo=$1; shift
    GIT_CONFIG_NOSYSTEM=1 GIT_CONFIG_GLOBAL="$empty_config" git -C "$repo" -c core.autocrlf=false "$@"
}

commit_as() { # <repo> <who: base|a|b> <date> <message>
    local name email
    case "$2" in
        base) name="Base Maintainer" email="base@example.com" ;;
        a) name="Developer A" email="developer.a@example.com" ;;
        b) name="Developer B" email="developer.b@example.com" ;;
    esac
    fgit "$1" add -A
    GIT_AUTHOR_NAME="$name" GIT_AUTHOR_EMAIL="$email" GIT_AUTHOR_DATE="$3" \
    GIT_COMMITTER_NAME="$name" GIT_COMMITTER_EMAIL="$email" GIT_COMMITTER_DATE="$3" \
        fgit "$1" commit -q --allow-empty -m "$4"
}

# apply_side <case-dir> <side> <repo>: write the overlay, then the deletions.
apply_side() {
    local case_dir=$1 side=$2 repo=$3 path
    [[ -d "$case_dir/$side" ]] && copy_tree "$case_dir/$side" "$repo"
    if [[ -f "$case_dir/$side.delete" ]]; then
        while IFS= read -r path || [[ -n "$path" ]]; do
            path=${path%$'\r'}
            [[ -n "$path" ]] && fgit "$repo" rm -q -r -- "$path"
        done < "$case_dir/$side.delete"
    fi
}

new_repo() { # <dest>: (re)create an empty repository directly inside $out
    local dest=$1
    [[ "$(dirname "$dest")" == "$out" ]] || die "refusing to build outside $out: $dest"
    rm -rf -- "$dest"
    mkdir -p "$dest"
    fgit "$dest" init -q -b main
}

base_commit() { # <repo> <with-defect yes|no>
    copy_tree "$MINIAPP" "$1"
    [[ "$2" == yes ]] && cp "$SHARED/legacy.py" "$1/profileapp/legacy.py"
    commit_as "$1" base "2026-10-05T09:00:00+08:00" "MiniApp base"
}

add_branch() { # <repo> <case-dir> <side> <branch> <date> <message>
    fgit "$1" checkout -q -b "$4" main
    apply_side "$2" "$3" "$1"
    commit_as "$1" "$3" "$5" "$6"
    fgit "$1" checkout -q main
}

build_case() { # <case-dir>
    local case_dir=$1 dest="$out/$(basename "$1")"
    new_repo "$dest"
    base_commit "$dest" "$CASE_BASE_DEFECT"
    add_branch "$dest" "$case_dir" a "$CASE_BRANCH_A" "2026-10-05T10:00:00+08:00" "$CASE_BRANCH_A"
    add_branch "$dest" "$case_dir" b "$CASE_BRANCH_B" "2026-10-05T11:00:00+08:00" "$CASE_BRANCH_B"
    printf '%-4s %-8s %-3s %-7s %-26s %-26s %s %s\n' "$CASE_ID" "$CASE_LABEL" "$CASE_RULE" "$CASE_SPLIT" \
        "$CASE_BRANCH_A" "$CASE_BRANCH_B" \
        "$(fgit "$dest" rev-parse --short=7 "$CASE_BRANCH_A")" "$(fgit "$dest" rev-parse --short=7 "$CASE_BRANCH_B")"
}

build_miniapp() { # the three Appendix C2 pairs in one repository
    local dest="$out/miniapp" id hour=10
    new_repo "$dest"
    base_commit "$dest" no
    for id in c01 c05 c09; do
        load_case "$CASES/$id"
        add_branch "$dest" "$CASES/$id" a "$CASE_BRANCH_A" "2026-10-06T$hour:00:00+08:00" "$CASE_DESCRIPTION (A)"
        add_branch "$dest" "$CASES/$id" b "$CASE_BRANCH_B" "2026-10-06T$hour:30:00+08:00" "$CASE_DESCRIPTION (B)"
        hour=$((hour + 1))
    done
    printf 'miniapp: %s\n' "$(fgit "$dest" branch --format='%(refname:short)' | tr '\n' ' ')"
}

# build_latency: 100 Python files (bigapp/__init__.py + 99 modules). Each
# module calls into the previous one. A adds a required parameter to
# bigapp.mod000.f0 and updates its own caller; B adds a call to the old
# signature in the last module, so the expected result is one R2 finding.
build_latency() {
    local dest="$out/latency100" i prev
    new_repo "$dest"
    mkdir -p "$dest/bigapp"
    echo '"""Synthetic 100-file package for latency measurement."""' > "$dest/bigapp/__init__.py"
    for (( i = 0; i < 99; i++ )); do
        printf -v prev 'mod%03d' $(( i > 0 ? i - 1 : 0 ))
        if (( i == 0 )); then
            imports='' f1_body='return x + y'
        else
            imports="from bigapp import $prev as prev" f1_body='return prev.f1(x, y) + 1'
        fi
        cat > "$(printf '%s/bigapp/mod%03d.py' "$dest" "$i")" <<PY
"""Synthetic module $i."""
$imports


def f0(x):
    return x


def f1(x, y=1):
    $f1_body


def f2(x):
    return f0(x) * 2
PY
    done
    commit_as "$dest" base "2026-10-05T09:00:00+08:00" "bigapp base"

    fgit "$dest" checkout -q -b latency-api main
    sed -i 's/^def f0(x):$/def f0(x, scale):/; s/return f0(x) \* 2$/return f0(x, 1) * 2/' "$dest/bigapp/mod000.py"
    commit_as "$dest" a "2026-10-05T10:00:00+08:00" "f0 takes a required scale"

    fgit "$dest" checkout -q -b latency-caller main
    cat >> "$dest/bigapp/mod098.py" <<'PY'


import bigapp.mod000 as first


def g(x):
    return first.f0(x)
PY
    commit_as "$dest" b "2026-10-05T11:00:00+08:00" "call f0 from mod098"
    fgit "$dest" checkout -q main
    echo "latency100: $(fgit "$dest" ls-files '*.py' | wc -l | tr -d ' ') Python files," \
        "branches latency-api latency-caller"
}

mkdir -p "$out"
out=$(cd "$out" && pwd)
: > "$out/.empty-gitconfig"
empty_config="$out/.empty-gitconfig"

if (( latency )); then
    build_latency
    exit 0
fi

if (( ${#selected[@]} == 0 )); then
    for dir in "$CASES"/*/; do selected+=("$(basename "$dir")"); done
fi

built=0
for id in "${selected[@]}"; do
    [[ -f "$CASES/$id/case.env" ]] || die "no such case: $id"
    load_case "$CASES/$id"
    [[ "$split" == all || "$split" == "$CASE_SPLIT" ]] || continue
    if (( list_only )); then
        printf '%-4s %-8s %-3s %-7s %s\n' "$CASE_ID" "$CASE_LABEL" "$CASE_RULE" "$CASE_SPLIT" "$CASE_DESCRIPTION"
    else
        build_case "$CASES/$id"
    fi
    built=$((built + 1))
done
if (( ! list_only )) && [[ "$split" != holdout ]] && [[ -d "$CASES/c01" && -d "$CASES/c05" && -d "$CASES/c09" ]]; then
    build_miniapp
fi
(( list_only )) || printf '%d case repositories under %s\n' "$built" "${out#"$ROOT"/}"
