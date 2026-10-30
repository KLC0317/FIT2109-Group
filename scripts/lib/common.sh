# Shared Bash helpers. Source, do not execute.
# shellcheck shell=bash

die() {
    printf 'error: %s\n' "$*" >&2
    exit "${SMC_DIE_STATUS:-1}"
}

# Print the Python 3.12 interpreter to use: $SMC_PYTHON, then the project venv,
# then python3.12 / python3 / python on PATH.
smc_python() {
    local root candidate
    root=$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)
    for candidate in "${SMC_PYTHON:-}" "$root/.venv/bin/python" "$root/.venv/Scripts/python.exe" \
                     python3.12 python3 python; do
        [[ -n "$candidate" ]] || continue
        if command -v "$candidate" >/dev/null 2>&1 &&
           "$candidate" -c 'import sys; sys.exit(sys.version_info[:2] != (3, 12))' 2>/dev/null; then
            printf '%s\n' "$candidate"
            return 0
        fi
    done
    return 1
}

# Convert a path for a native (non-MSYS) program such as python.exe on Windows.
native_path() {
    if command -v cygpath >/dev/null 2>&1; then
        cygpath -m -- "$1"
    else
        printf '%s\n' "$1"
    fi
}

# Copy a directory's contents, skipping caches.
copy_tree() { # <src> <dest>
    mkdir -p "$2"
    tar -C "$1" --exclude=__pycache__ --exclude='*.pyc' -cf - . | tar -C "$2" -xmf -
}

# Quote a string as a JSON string literal.
json_str() {
    local s=$1 out='' c i
    s=${s//\\/\\\\}
    s=${s//\"/\\\"}
    s=${s//$'\n'/\\n}
    s=${s//$'\r'/\\r}
    s=${s//$'\t'/\\t}
    # Drop any remaining control characters.
    for (( i = 0; i < ${#s}; i++ )); do
        c=${s:i:1}
        [[ "$c" == [[:cntrl:]] ]] || out+=$c
    done
    printf '"%s"' "$out"
}
