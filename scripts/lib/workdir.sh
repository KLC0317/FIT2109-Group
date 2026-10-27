# Reference validation and isolated work-directory helpers. Source, do not execute.
#
# AI-assisted activity 2 (docs/ai-use.md): first draft requested from a
# University-supported assistant by M2, edited by M2 against M1's isolation
# design, verified by M3 (tests/integration/test_workdir.py).
# shellcheck shell=bash

# smc_resolve_commit <repo> <ref>
# Print the full commit ID for <ref>. Rejects empty refs, refs that look like
# options and refs containing whitespace or control characters.
smc_resolve_commit() {
    local repo=$1 ref=$2
    [[ -n "$ref" && "$ref" != -* ]] || return 1
    [[ "$ref" != *[[:space:][:cntrl:]]* ]] || return 1
    git -C "$repo" rev-parse --verify --quiet --end-of-options "$ref^{commit}"
}

# smc_check_source_root <path>
# Print the normalised repository-relative source root ("." for the root).
# Rejects absolute paths, drive letters and any ".." component.
smc_check_source_root() {
    local path
    path=$(printf '%s' "$1" | tr '\\' /)
    [[ -n "$path" ]] || return 1
    [[ "$path" != /* && "$path" != [A-Za-z]:* ]] || return 1
    local part out=()
    local IFS=/
    for part in $path; do
        case "$part" in
            ''|.) ;;
            ..) return 1 ;;
            *) out+=("$part") ;;
        esac
    done
    if (( ${#out[@]} == 0 )); then
        printf '.\n'
    else
        printf '%s\n' "${out[*]}"
    fi
}

# smc_make_workdir <base>
# Create <base> if needed and a fresh private directory <base>/run.XXXXXX.
smc_make_workdir() {
    local base=$1 dir
    [[ -n "$base" ]] || return 1
    mkdir -p -- "$base" || return 1
    base=$(cd -- "$base" && pwd -P) || return 1
    dir=$(mktemp -d "$base/run.XXXXXX") || return 1
    chmod 700 -- "$dir" 2>/dev/null || true
    printf '%s\n' "$dir"
}

# smc_remove_workdir <dir> <base>
# Remove <dir> only if it is a real directory named run.XXXXXX directly inside
# <base>. Anything else is refused, so a bad variable can never widen the
# deletion.
smc_remove_workdir() {
    local dir=$1 base=$2 parent name
    [[ -n "$dir" && -n "$base" ]] || return 1
    [[ -e "$dir" || -L "$dir" ]] || return 0
    if [[ -L "$dir" || ! -d "$dir" ]]; then
        printf 'refusing to remove %s: not a directory\n' "$dir" >&2
        return 1
    fi
    base=$(cd -- "$base" 2>/dev/null && pwd -P) || return 1
    parent=$(cd -- "$(dirname -- "$dir")" && pwd -P) || return 1
    name=$(basename -- "$dir")
    if [[ "$parent" != "$base" || "$name" != run.?????? ]]; then
        printf 'refusing to remove %s: outside %s\n' "$dir" "$base" >&2
        return 1
    fi
    rm -rf -- "${parent:?}/${name:?}"
}
