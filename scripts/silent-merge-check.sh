#!/usr/bin/env bash
# silent-merge-check: check two committed branches of a Python project for
# incompatibilities that a clean Git merge would hide.
#
# Usage: bash scripts/silent-merge-check.sh --repo <repo> [--source-root <dir>]
#            [--out-dir <dir>] [--json <file>] [--log <file>] [--keep-temp] [--quiet]
#            <ref-a> <ref-b>
#
# Exit codes: 0 SAFE, 1 SILENT BREAK, 2 TEXT CONFLICT, 3 INCONCLUSIVE/ERROR.
#
# Only committed states are analysed. The user's repository is read, never
# written: the merge happens in a temporary repository under <out-dir>/tmp
# that borrows the user's objects read-only, with hooks and the user's
# global/system Git configuration switched off. Project code is never run.
set -euo pipefail

readonly EXIT_SAFE=0 EXIT_BREAK=1 EXIT_CONFLICT=2 EXIT_ERROR=3

ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
# shellcheck source=scripts/lib/common.sh
source "$ROOT/scripts/lib/common.sh"
# shellcheck source=scripts/lib/workdir.sh
source "$ROOT/scripts/lib/workdir.sh"

# Never let a caller's Git environment redirect us into another repository.
unset GIT_DIR GIT_WORK_TREE GIT_INDEX_FILE GIT_OBJECT_DIRECTORY \
      GIT_ALTERNATE_OBJECT_DIRECTORIES GIT_COMMON_DIR GIT_NAMESPACE

usage() {
    sed -n '2,9s/^# \{0,1\}//p' "${BASH_SOURCE[0]}"
}

repo='' source_root='.' out_dir="$ROOT/out" report='' log_file='' keep_temp=0 quiet=0
refs=()
need_value() { # <option> <remaining-arg-count>
    (( $2 >= 2 )) || { printf 'error: %s needs a value\n' "$1" >&2; exit $EXIT_ERROR; }
}
while (( $# > 0 )); do
    case "$1" in
        --repo) need_value "$1" $#; repo=$2; shift 2 ;;
        --source-root) need_value "$1" $#; source_root=$2; shift 2 ;;
        --out-dir) need_value "$1" $#; out_dir=$2; shift 2 ;;
        --json) need_value "$1" $#; report=$2; shift 2 ;;
        --log) need_value "$1" $#; log_file=$2; shift 2 ;;
        --keep-temp) keep_temp=1; shift ;;
        --quiet) quiet=1; shift ;;
        -h|--help) usage; exit 0 ;;
        --) shift; refs+=("$@"); break ;;
        -*) usage >&2; printf 'error: unknown option: %s\n' "$1" >&2; exit $EXIT_ERROR ;;
        *) refs+=("$1"); shift ;;
    esac
done

# Generated files must never land in the user's working tree: refuse output
# paths inside it unless the repository ignores them.
if [[ -n "$repo" && -d "$repo" ]] &&
   [[ "$(git -C "$repo" rev-parse --is-inside-work-tree 2>/dev/null)" == true ]]; then
    toplevel=$(cd "$(git -C "$repo" rev-parse --show-toplevel)" && pwd -P)
    for target in "$out_dir" "$report" "$log_file"; do
        [[ -n "$target" ]] || continue
        resolved=$(realpath -m -- "$target")
        probe=$resolved
        [[ "$target" != "$out_dir" ]] || probe+=/  # directory-only ignore patterns
        if [[ "$resolved" == "$toplevel" || "$resolved" == "$toplevel"/* ]] &&
           ! git -C "$repo" check-ignore -q --no-index -- "$probe" 2>/dev/null; then
            printf 'error: %s is inside the working tree of %s; choose an --out-dir/--json/--log outside it\n' \
                "$target" "$repo" >&2
            exit $EXIT_ERROR
        fi
    done
fi

run_id="$(date +%Y%m%dT%H%M%S)-$$"
mkdir -p "$out_dir/reports"
out_dir=$(cd "$out_dir" && pwd -P)
[[ -n "$report" ]] || report="$out_dir/reports/$run_id.json"
[[ -n "$log_file" ]] || log_file="$out_dir/logs/$run_id.jsonl"
mkdir -p "$(dirname "$log_file")"

# --- structured log and stage timing ----------------------------------------------
now_ms() {
    if [[ -n "${EPOCHREALTIME:-}" ]]; then
        local t=${EPOCHREALTIME/[.,]/}
        printf '%s\n' $(( 10#$t / 1000 ))
    else
        printf '%s\n' $(( $(date +%s%N) / 1000000 ))
    fi
}

# log_event <event> [extra JSON members]: append one JSON line to the run log.
log_event() {
    printf '{"ts": "%s", "run_id": "%s", "component": "orchestrator", "event": %s%s}\n' \
        "$(date -u +%Y-%m-%dT%H:%M:%S.%3NZ)" "$run_id" "$(json_str "$1")" "${2:+, $2}" >> "$log_file"
}

run_t0=$(now_ms) stage_t0=0 stage_name=''
# stage <name>: log the running stage's duration, then start <name>.
stage() {
    local now
    now=$(now_ms)
    if [[ -n "$stage_name" ]]; then
        log_event stage "\"stage\": \"$stage_name\", \"duration_ms\": $(( now - stage_t0 ))"
    fi
    stage_name=$1 stage_t0=$now
}

log_result() { # <status> <exit-code>
    stage ''
    log_event result "\"status\": \"$1\", \"exit_code\": $2, \"total_ms\": $(( $(now_ms) - run_t0 )), \"report\": $(json_str "$(native_path "$report")")"
}

log_event start "\"refs\": [$(json_str "${refs[0]-}"), $(json_str "${refs[1]-}")], \"repo\": $(json_str "$repo"), \"source_root\": $(json_str "$source_root")"
stage validate

notes=()
commit_base='' commit_a='' commit_b=''

# --- error reporting ---------------------------------------------------------
# finish <status> <message>: write a minimal report for runs that stop before
# analysis (bad input, unsupported repository features) and exit 3.
finish() {
    local status=$1 message=$2 note_json='' n
    for n in "${notes[@]+"${notes[@]}"}"; do note_json+="${note_json:+, }$(json_str "$n")"; done
    mkdir -p "$(dirname "$report")"
    cat > "$report" <<JSON
{
  "tool": "silent-merge-check",
  "status": "$status",
  "exit_code": $EXIT_ERROR,
  "run_id": "$run_id",
  "refs": {"a": $(json_str "${refs[0]-}"), "b": $(json_str "${refs[1]-}")},
  "commits": {"base": "$commit_base", "a": "$commit_a", "b": "$commit_b"},
  "error": $(json_str "$message"),
  "findings": [],
  "notes": [$note_json]
}
JSON
    log_event error "\"message\": $(json_str "$message")"
    log_result "$status" $EXIT_ERROR
    if (( quiet == 0 )); then
        printf 'silent-merge-check: %s\n' "$status"
    fi
    printf 'error: %s\n' "$message" >&2
    exit $EXIT_ERROR
}

# --- validate input ------------------------------------------------------------
(( ${#refs[@]} == 2 )) || { usage >&2; finish ERROR "expected exactly two branch references"; }
[[ -n "$repo" ]] || finish ERROR "--repo is required"
[[ -d "$repo" ]] || finish ERROR "repository not found: $repo"
git -C "$repo" rev-parse --git-dir >/dev/null 2>&1 || finish ERROR "not a Git repository: $repo"

PY=$(smc_python) || finish ERROR "Python 3.12 not found (run scripts/setup.sh or set SMC_PYTHON)"

source_root=$(smc_check_source_root "$source_root") ||
    finish ERROR "source root must be a relative path inside the repository without '..'"

commit_a=$(smc_resolve_commit "$repo" "${refs[0]}") || finish ERROR "cannot resolve '${refs[0]}' to a commit"
commit_b=$(smc_resolve_commit "$repo" "${refs[1]}") || finish ERROR "cannot resolve '${refs[1]}' to a commit"

if [[ "$(git -C "$repo" rev-parse --is-bare-repository)" == false ]]; then
    changes=$(git -C "$repo" --no-optional-locks status --porcelain=v1 -z --untracked-files=no | tr -cd '\0' | wc -c)
    if (( changes > 0 )); then
        notes+=("$changes uncommitted change(s) in the working tree were excluded; only the committed states of ${refs[0]} and ${refs[1]} are analysed")
    fi
fi

stage merge_base
mapfile -t bases < <(git -C "$repo" merge-base --all "$commit_a" "$commit_b" || true)
case ${#bases[@]} in
    0) finish ERROR "'${refs[0]}' and '${refs[1]}' have no common ancestor" ;;
    1) commit_base=${bases[0]} ;;
    *) finish INCONCLUSIVE "${#bases[@]} merge bases (criss-cross history) are out of scope" ;;
esac

# --- unsupported repository features -----------------------------------------
stage preflight
for commit in "$commit_base" "$commit_a" "$commit_b"; do
    if git -C "$repo" ls-tree -r --format='%(objectmode)' "$commit" | grep -qx 160000; then
        finish INCONCLUSIVE "submodules are out of scope (found in ${commit:0:12})"
    fi
    while IFS= read -r -d '' path; do
        [[ "$path" == .gitattributes || "$path" == */.gitattributes ]] || continue
        drivers=$(git -C "$repo" cat-file blob "$commit:$path" |
            grep -oE '(^|[[:space:]])merge=[^[:space:]]+' | sed 's/.*merge=//' |
            grep -vxE 'text|binary|union' || true)
        if [[ -n "$drivers" ]]; then
            finish INCONCLUSIVE "custom merge driver '$(head -n 1 <<<"$drivers")' in $path is not run by this tool"
        fi
    done < <(git -C "$repo" ls-tree -r -z --name-only "$commit")
done

if [[ "$source_root" != . ]]; then
    found=0
    for commit in "$commit_base" "$commit_a" "$commit_b"; do
        [[ -n "$(git -C "$repo" ls-tree --name-only "$commit" -- "$source_root")" ]] && found=1
    done
    (( found )) || finish ERROR "source root '$source_root' does not exist in either branch"
fi

# --- isolated work directory ----------------------------------------------------
stage workdir
tmp_base="$out_dir/tmp"
work=$(smc_make_workdir "$tmp_base") || finish ERROR "cannot create a work directory under $tmp_base"
cleanup() {
    if (( keep_temp == 0 )); then
        smc_remove_workdir "$work" "$tmp_base" || true
    else
        printf 'kept work directory: %s\n' "$work" >&2
    fi
}
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

objects="$(git -C "$repo" rev-parse --path-format=absolute --git-common-dir)/objects"
mkdir -p "$work/hooks"
: > "$work/gitconfig"
git init -q "$work/repo"
printf '%s\n' "$objects" > "$work/repo/.git/objects/info/alternates"

# Git in the temporary repository: no hooks, no user/system config (and so no
# user-defined merge drivers), no line-ending conversion.
tgit() {
    GIT_CONFIG_NOSYSTEM=1 GIT_CONFIG_GLOBAL="$work/gitconfig" \
        git -C "$work/repo" -c core.hooksPath="$work/hooks" -c core.autocrlf=false \
            -c user.name=silent-merge-check -c user.email=smc@localhost "$@"
}

# --- merge ----------------------------------------------------------------------
stage merge
tgit checkout -q --detach "$commit_a"
set +e
tgit merge -q --no-commit --no-ff --no-edit "$commit_b" >"$work/merge.out" 2>&1
merge_status=$?
set -e

conflicts_file="$work/conflicts.lst"
: > "$conflicts_file"
merged_tree=''
if [[ -n "$(tgit ls-files -u)" ]]; then
    merge_result=conflict
    tgit diff --name-only -z --diff-filter=U > "$conflicts_file"
elif (( merge_status != 0 )); then
    finish ERROR "git merge failed without conflicts: $(tr -d '\r' < "$work/merge.out" | tail -n 1)"
else
    merge_result=clean
    merged_tree=$(tgit write-tree)
fi

# --- export the code states ------------------------------------------------------
# export_state <label> <tree-ish>: extract the tree and write a NUL-delimited
# list of the Python files under the source root.
export_state() {
    local label=$1 oid=$2 dir="$work/snap/$1" path
    local pathspec=()
    [[ "$source_root" == . ]] || pathspec=(-- "$source_root")
    mkdir -p "$dir"
    tgit archive --format=tar "$oid" | tar -x -m -C "$dir"
    : > "$work/snap/$label.files"
    while IFS= read -r -d '' path; do
        [[ "$path" == *.py ]] && printf '%s\0' "$path" >> "$work/snap/$label.files"
    done < <(tgit ls-tree -r -z --name-only "$oid" "${pathspec[@]}")
}

state_json() { # <label>
    printf '{"dir": %s, "files": %s}' \
        "$(json_str "$(native_path "$work/snap/$1")")" "$(json_str "$(native_path "$work/snap/$1.files")")"
}

states=''
stage export
if [[ "$merge_result" == clean ]]; then
    export_state base "$commit_base"
    export_state a "$commit_a"
    export_state b "$commit_b"
    export_state merged "$merged_tree"
    states=$(printf '"base": %s, "a": %s, "b": %s, "merged": %s' \
        "$(state_json base)" "$(state_json a)" "$(state_json b)" "$(state_json merged)")
fi

# --- analyse --------------------------------------------------------------------
note_json=''
for n in "${notes[@]+"${notes[@]}"}"; do note_json+="${note_json:+, }$(json_str "$n")"; done
manifest="$work/manifest.json"
cat > "$manifest" <<JSON
{
  "version": 1,
  "run_id": "$run_id",
  "repo": $(json_str "$(native_path "$(cd "$repo" && pwd)")"),
  "source_root": $(json_str "$source_root"),
  "refs": {"a": $(json_str "${refs[0]}"), "b": $(json_str "${refs[1]}")},
  "commits": {"base": "$commit_base", "a": "$commit_a", "b": "$commit_b", "merged_tree": "$merged_tree"},
  "merge": {"result": "$merge_result", "conflicts_file": $(json_str "$(native_path "$conflicts_file")")},
  "states": {$states},
  "notes": [$note_json],
  "report": $(json_str "$(native_path "$report")"),
  "log": $(json_str "$(native_path "$log_file")")
}
JSON

stage analyse
quiet_flag=()
(( quiet == 0 )) || quiet_flag=(--quiet)
set +e
PYTHONPATH="$(native_path "$ROOT/src")" PYTHONDONTWRITEBYTECODE=1 \
    "$PY" -m smc analyse --manifest "$(native_path "$manifest")" "${quiet_flag[@]}"
status=$?
set -e

case $status in
    0) exit_code=$EXIT_SAFE ;;
    1) exit_code=$EXIT_BREAK ;;
    2) exit_code=$EXIT_CONFLICT ;;
    *) exit_code=$EXIT_ERROR ;;
esac
if (( exit_code == EXIT_ERROR )) && [[ ! -s "$report" ]]; then
    finish ERROR "analyser failed (exit $status)"
fi
result=$(grep -m 1 -o '"status": "[A-Z_]*"' "$report" | cut -d'"' -f4)
log_result "${result:-ERROR}" $exit_code
if (( quiet == 0 )); then
    printf 'report: %s\nlog:    %s\n' "${report#"$ROOT"/}" "${log_file#"$ROOT"/}"
fi
exit $exit_code
