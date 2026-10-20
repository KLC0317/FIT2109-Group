#!/usr/bin/env bash
# Appendix C1: scripted two-developer scenario.
#
# Builds the MiniApp profile service in a new disposable directory under
# out/reproduce/, creates r2-api-change (Developer A) and r2-new-caller
# (Developer B) from the same base commit with separate commit identities,
# then records each stage's command, exit code and first line of output in
# evidence_summary.json. The merge is attempted with --no-commit and aborted.
#
# Usage: bash scripts/reproduce.sh [--keep]
set -euo pipefail

ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
# shellcheck source=scripts/lib/common.sh
source "$ROOT/scripts/lib/common.sh"

keep=0
[[ "${1:-}" == "--keep" ]] && keep=1

PY=$(smc_python) || die "python 3.12 not found"
export PYTHONDONTWRITEBYTECODE=1

out_base="$ROOT/out/reproduce"
mkdir -p "$out_base"
work=$(mktemp -d "$out_base/run.XXXXXX")
repo="$work/profile-service"

cleanup() {
    if (( keep == 0 )) && [[ -d "$work" && "$work" == "$out_base"/run.* ]]; then
        rm -rf -- "$work"
    fi
}
trap cleanup EXIT

# Fixed identities and dates make the commit hashes reproducible.
commit_as() { # <name> <email> <date> <message>
    GIT_AUTHOR_NAME="$1" GIT_AUTHOR_EMAIL="$2" GIT_AUTHOR_DATE="$3" \
    GIT_COMMITTER_NAME="$1" GIT_COMMITTER_EMAIL="$2" GIT_COMMITTER_DATE="$3" \
        git -C "$repo" commit -q -m "$4"
}

# --- base -------------------------------------------------------------------
git init -q -b main "$repo"
git -C "$repo" config core.autocrlf false
copy_tree "$ROOT/scenario/miniapp" "$repo"
git -C "$repo" add -A
commit_as "Base Maintainer" "base@example.com" "2026-10-07T00:00:00+08:00" "MiniApp base"

# --- Developer A: include_email becomes a required parameter ----------------
git -C "$repo" checkout -q -b r2-api-change
cat > "$repo/profileapp/users.py" <<'PY'
"""User lookup."""

from profileapp.data import USERS


class UnknownUser(LookupError):
    """Raised when a user id is not in the data set."""


def get_user(user_id, include_email):
    try:
        record = USERS[user_id]
    except KeyError:
        raise UnknownUser(user_id) from None
    user = {"id": record["id"], "name": record["name"]}
    if include_email:
        user["email"] = record["email"]
    return user


def list_users():
    return [get_user(user_id, include_email=False) for user_id in sorted(USERS)]
PY
sed -i 's/user = get_user(user_id)$/user = get_user(user_id, include_email=False)/' "$repo/profileapp/roster.py"
sed -i 's/user = get_user(args.id)$/user = get_user(args.id, include_email=False)/' "$repo/profileapp/cli.py"
sed -i 's/get_user(1)\["name"\]/get_user(1, include_email=False)["name"]/; s/get_user(99)$/get_user(99, include_email=False)/' \
    "$repo/tests/test_users.py"
cat >> "$repo/tests/test_users.py" <<'PY'


class IncludeEmailTests(unittest.TestCase):
    def test_include_email(self):
        self.assertEqual(get_user(1, include_email=True)["email"], "alice@example.com")
PY
git -C "$repo" add -A
commit_as "Developer A" "developer.a@example.com" "2026-10-07T00:10:00+08:00" \
    "Make include_email a required parameter of get_user"

# --- Developer B: new caller written against the base API ------------------
git -C "$repo" checkout -q main
git -C "$repo" checkout -q -b r2-new-caller
cat > "$repo/profileapp/badge.py" <<'PY'
"""Badge text for the profile page."""

from profileapp.users import get_user


def badge_line(user_id):
    user = get_user(user_id)
    return f"{user['id']}: {user['name']}"
PY
git -C "$repo" add -A
commit_as "Developer B" "developer.b@example.com" "2026-10-07T00:20:00+08:00" \
    "Add badge_line for the profile page"

# --- stages -----------------------------------------------------------------
badge_cmd='from profileapp.badge import badge_line; print(badge_line(1))'
stages_json=()
failures=0

record() { # <stage> <expected-exit> <command...>
    local stage="$1" expected="$2"; shift 2
    local out rc
    set +e
    out=$(cd "$repo" && "$@" 2>&1)
    rc=$?
    set -e
    local observed
    observed=$(printf '%s\n' "$out" | tr -d '\r' | grep -v '^Traceback\|^  ' | tail -n 1)
    local ok=true
    if [[ "$rc" != "$expected" ]]; then ok=false; failures=$((failures + 1)); fi
    printf '  %-28s exit %s (expected %s)  %s\n' "$stage" "$rc" "$expected" "$observed"
    stages_json+=("{\"stage\": $(json_str "$stage"), \"command\": $(json_str "${*//"$PY"/python}"), \"exit\": $rc, \"expected_exit\": $expected, \"ok\": $ok, \"observed\": $(json_str "$observed")}")
}

echo "C1 scenario in $repo"
git -C "$repo" checkout -q r2-api-change
record "A: r2-api-change show" 0 "$PY" main.py show --id 1
record "A: r2-api-change tests" 0 "$PY" -m unittest discover -s tests -t . -q
git -C "$repo" checkout -q r2-new-caller
record "B: r2-new-caller badge" 0 "$PY" -c "$badge_cmd"
record "B: r2-new-caller tests" 0 "$PY" -m unittest discover -s tests -t . -q
git -C "$repo" checkout -q r2-api-change
record "merge into r2-api-change" 0 git merge --no-commit --no-ff r2-new-caller
unmerged=$(git -C "$repo" ls-files -u | wc -l | tr -d ' ')
record "merged show" 0 "$PY" main.py show --id 1
record "merged tests" 0 "$PY" -m unittest discover -s tests -t . -q
record "merged badge" 1 "$PY" -c "$badge_cmd"
git -C "$repo" merge --abort

if (( unmerged != 0 )); then failures=$((failures + 1)); fi

summary="$out_base/evidence_summary.json"
{
    printf '{\n'
    printf '  "scenario": "C1 two-developer silent break",\n'
    printf '  "generated_at": %s,\n' "$(json_str "$(date '+%Y-%m-%dT%H:%M:%S%z')")"
    printf '  "git_version": %s,\n' "$(json_str "$(git --version | tr -d '\r')")"
    printf '  "python_version": %s,\n' "$(json_str "$("$PY" --version 2>&1 | tr -d '\r')")"
    printf '  "commits": {"base": "%s", "r2-api-change": "%s", "r2-new-caller": "%s"},\n' \
        "$(git -C "$repo" rev-parse main)" "$(git -C "$repo" rev-parse r2-api-change)" \
        "$(git -C "$repo" rev-parse r2-new-caller)"
    printf '  "unmerged_entries": %s,\n' "$unmerged"
    printf '  "stages": [\n    %s\n  ],\n' "$(IFS=$'\n'; printf '%s' "${stages_json[*]}" | sed '$!s/$/,/' | sed '2,$s/^/    /')"
    printf '  "all_checks_passed": %s\n' "$([[ $failures -eq 0 ]] && echo true || echo false)"
    printf '}\n'
} > "$summary"

echo "evidence: ${summary#"$ROOT"/}"
if (( failures == 0 )); then
    echo "All scripted checks passed: both branches work, Git merges cleanly, badge_line(1) fails after the merge."
else
    echo "$failures scripted check(s) did not match the expected outcome." >&2
    exit 1
fi
