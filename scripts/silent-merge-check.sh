#!/usr/bin/env bash
# silent-merge-check: check two committed branches of a Python project for
# incompatibilities that a clean Git merge would hide.
#
# Usage: bash scripts/silent-merge-check.sh --repo <repo> [--source-root <dir>]
#            [--out-dir <dir>] [--json <file>] [--log <file>] [--keep-temp] [--quiet] [--debug]
#            <ref-a> <ref-b>
#
# Exit codes: 0 SAFE, 1 SILENT BREAK, 2 TEXT CONFLICT, 3 INCONCLUSIVE/ERROR.
#
# Only committed states are analysed. The user's repository is read, never
# written: the merge happens in a temporary repository under <out-dir>/tmp
# that borrows the user's objects read-only, with hooks and the user's
# global/system Git configuration switched off. Project code is never run.
set -Eeuo pipefail

readonly EXIT_SAFE=0 EXIT_BREAK=1 EXIT_CONFLICT=2 EXIT_ERROR=3

# Exit codes 1 and 2 are results. An unplanned exit (set -e stopping on a
# failed command) must never be mistaken for one, so every deliberate exit
# goes through leave() and the EXIT trap turns anything else into ERROR.
deliberate=0 failed_at=''
leave() { deliberate=1; exit "$1"; }
trap 'failed_at="line $LINENO: $BASH_COMMAND"' ERR

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

repo='' source_root='.' out_dir="$ROOT/out" report='' log_file='' keep_temp=0 quiet=0 debug=false
refs=()
need_value() { # <option> <remaining-arg-count>
    (( $2 >= 2 )) || { printf 'error: %s needs a value\n' "$1" >&2; leave $EXIT_ERROR; }
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
        --debug) debug=true; shift ;;
        -h|--help) usage; leave 0 ;;
        --) shift; refs+=("$@"); break ;;
        -*) usage >&2; printf 'error: unknown option: %s\n' "$1" >&2; leave $EXIT_ERROR ;;
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
        resolved=$(realpath -m -- "$(shell_path "$target")")
        probe=$resolved
        [[ "$target" != "$out_dir" ]] || probe+=/  # directory-only ignore patterns
        if [[ "$resolved" == "$toplevel" || "$resolved" == "$toplevel"/* ]] &&
           ! git -C "$repo" check-ignore -q --no-index -- "$probe" 2>/dev/null; then
            printf 'error: %s is inside the working tree of %s; choose an --out-dir/--json/--log outside it\n' \
                "$target" "$repo" >&2
            leave $EXIT_ERROR
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
# Timing and timestamps use bash builtins only (EPOCHREALTIME, printf %()T):
# profiling showed a forked `date` per log line was a measurable share of a run.
# now_ms <var>: milliseconds since the epoch into <var>.
now_ms() {
    local us=${EPOCHREALTIME/[.,]/}
    printf -v "$1" '%s' $(( 10#$us / 1000 ))
}

# log_event <event> [extra JSON members]: append one JSON line to the run log.
log_event() {
    local us=${EPOCHREALTIME/[.,]/} ts
    TZ=UTC0 printf -v ts '%(%Y-%m-%dT%H:%M:%S)T' "${us:0:${#us}-6}"
    printf '{"ts": "%s.%sZ", "run_id": "%s", "component": "orchestrator", "event": "%s"%s}\n' \
        "$ts" "${us:${#us}-6:3}" "$run_id" "$1" "${2:+, $2}" >> "$log_file"
}

now_ms run_t0
stage_t0=0 stage_name=''
# stage <name>: log the running stage's duration, then start <name>.
stage() {
    local now
    now_ms now
    if [[ -n "$stage_name" ]]; then
        log_event stage "\"stage\": \"$stage_name\", \"duration_ms\": $(( now - stage_t0 ))"
    fi
    stage_name=$1 stage_t0=$now
}

log_result() { # <status> <exit-code>
    local now
    stage ''
    now_ms now
    log_event result "\"status\": \"$1\", \"exit_code\": $2, \"total_ms\": $(( now - run_t0 )), \"report\": $(json_str "$(native_path "$report")")"
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
    leave $EXIT_ERROR
}

work='' tmp_base="$out_dir/tmp"
cleanup() {
    [[ -n "$work" ]] || return 0
    if (( keep_temp == 0 )); then
        smc_remove_workdir "$work" "$tmp_base" || true
    else
        printf 'kept work directory: %s\n' "$work" >&2
    fi
}

on_exit() {
    local status=$?
    set +e
    trap - EXIT
    cleanup
    if (( deliberate == 0 )); then
        finish ERROR "unexpected failure (exit $status)${failed_at:+ at $failed_at}"
        exit $EXIT_ERROR
    fi
    exit "$status"
}
trap on_exit EXIT
trap 'deliberate=1; exit 130' INT
trap 'deliberate=1; exit 143' TERM

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
# One ls-tree pass per commit finds gitlinks (submodules), .gitattributes
# files and whether the source root exists.
root_found=0
for commit in "$commit_base" "$commit_a" "$commit_b"; do
    while IFS= read -r -d '' entry; do
        mode=${entry%% *} path=${entry#* }
        if [[ "$mode" == 160000 ]]; then
            finish INCONCLUSIVE "submodules are out of scope (found in ${commit:0:12})"
        fi
        if [[ "$source_root" == . || "$path" == "$source_root"/* ]]; then
            root_found=1
        fi
        [[ "$path" == .gitattributes || "$path" == */.gitattributes ]] || continue
        drivers=$(git -C "$repo" cat-file blob "$commit:$path" |
            grep -oE '(^|[[:space:]])merge=[^[:space:]]+' | sed 's/.*merge=//' |
            grep -vxE 'text|binary|union' || true)
        if [[ -n "$drivers" ]]; then
            finish INCONCLUSIVE "custom merge driver '$(head -n 1 <<<"$drivers")' in $path is not run by this tool"
        fi
    done < <(git -C "$repo" ls-tree -r -z --format='%(objectmode) %(path)' "$commit")
done
(( root_found )) || finish ERROR "source root '$source_root' does not exist in either branch"

# --- isolated work directory ----------------------------------------------------
stage workdir
work=$(smc_make_workdir "$tmp_base") || finish ERROR "cannot create a work directory under $tmp_base"

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
# export_states <label>=<tree-ish>...: extract only the Python files under the
# source root of every state into snap/<label>/, then write snap/<label>.files,
# a NUL-delimited list of those files. Profiling showed process start-up
# dominated this stage, so all states stream through one tar (-i reads the
# concatenated archives) and the lists come from globbing, not git ls-tree.
export_states() {
    local glob=':(glob)**/*.py' pair label path
    [[ "$source_root" == . ]] || glob=":(glob)$source_root/**/*.py"
    mkdir -p "$work/snap"
    for pair in "$@"; do mkdir -p "$work/snap/${pair%%=*}"; done
    (
        for pair in "$@"; do
            label=${pair%%=*}
            # A state with no Python files makes the pathspec match nothing;
            # that is an empty snapshot, any other archive failure is fatal.
            if ! tgit archive --format=tar --prefix="$label/" "${pair#*=}" -- "$glob" 2>"$work/archive-$label.err"; then
                grep -q 'did not match any files' "$work/archive-$label.err" || exit 1
            fi
        done
    ) | tar -x -i -m -C "$work/snap"
    shopt -s globstar nullglob dotglob
    local files=()
    for pair in "$@"; do
        label=${pair%%=*}
        files=()
        # The archive holds only files matching *.py, so no per-file stat is
        # needed (a directory named *.py would make the analyser fail: ERROR).
        for path in "$work/snap/$label"/**/*.py; do
            files+=("${path#"$work/snap/$label/"}")
        done
        if (( ${#files[@]} )); then
            printf '%s\0' "${files[@]}" > "$work/snap/$label.files"
        else
            : > "$work/snap/$label.files"
        fi
    done
    shopt -u globstar nullglob dotglob
}

states=''
stage export
if [[ "$merge_result" == clean ]]; then
    export_states base="$commit_base" a="$commit_a" b="$commit_b" merged="$merged_tree"
    # One path conversion for all states (each cygpath call is a process).
    snap=$(json_str "$(native_path "$work/snap")")
    snap=${snap%\"}
    for label in base a b merged; do
        states+="${states:+, }\"$label\": {\"dir\": $snap/$label\", \"files\": $snap/$label.files\"}"
    done
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
  "log": $(json_str "$(native_path "$log_file")"),
  "debug": $debug
}
JSON

stage analyse
quiet_flag=()
(( quiet == 0 )) || quiet_flag=(--quiet)
rm -f -- "$report"
set +e
PYTHONPATH="$(native_path "$ROOT/src")" PYTHONDONTWRITEBYTECODE=1 \
    "$PY" -m smc analyse --manifest "$(native_path "$manifest")" "${quiet_flag[@]}"
status=$?
set -e

# The report decides the result; the analyser's exit code must agree with it.
result=$(grep -m 1 -o '"status": "[A-Z_]*"' "$report" 2>/dev/null | cut -d'"' -f4 || true)
case "$result" in
    SAFE) exit_code=$EXIT_SAFE ;;
    SILENT_BREAK) exit_code=$EXIT_BREAK ;;
    TEXT_CONFLICT) exit_code=$EXIT_CONFLICT ;;
    INCONCLUSIVE|ERROR) exit_code=$EXIT_ERROR ;;
    *) finish ERROR "analyser failed (exit $status) without writing a report" ;;
esac
(( status == exit_code )) || finish ERROR "analyser exit $status does not match its report ($result)"
log_result "$result" $exit_code
if (( quiet == 0 )); then
    printf 'report: %s\nlog:    %s\n' "${report#"$ROOT"/}" "${log_file#"$ROOT"/}"
fi
leave $exit_code
