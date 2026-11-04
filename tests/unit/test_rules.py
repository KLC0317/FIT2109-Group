"""Four-state rule tests: every rule, its evidence conditions and safe counterexamples.

Each case gives the base files and what branches A and B change (a value of
None deletes the file). The merged state is base + A's changes + B's
changes, which is what Git produces when the two sides touch different files.
"""

from __future__ import annotations

import pytest

from smc.rules import analyse
from smc.snapshot import Snapshot

USERS = "def get_user(user_id):\n    return {'id': user_id}\n\n\ndef list_users():\n    return [get_user(1)]\n"
USERS_REQUIRED = "def get_user(user_id, include_email):\n    return {'id': user_id}\n\n\ndef list_users():\n    return [get_user(1, False)]\n"
USERS_OPTIONAL = USERS.replace("def get_user(user_id)", "def get_user(user_id, include_email=False)")
USERS_NO_GET = "def fetch_user(user_id):\n    return {'id': user_id}\n\n\ndef list_users():\n    return [fetch_user(1)]\n"
TEXT = "def display_name(name, upper=False):\n    return name\n\n\ndef initials(name):\n    return name[:1]\n"

BASE = {"app/__init__.py": "", "app/users.py": USERS, "app/text.py": TEXT}


def merge(*changes: dict) -> dict:
    files = dict(BASE)
    for change in changes:
        for path, text in change.items():
            if text is None:
                files.pop(path, None)
            else:
                files[path] = text
    return files


def run(a: dict, b: dict, base_extra: dict | None = None, merged: dict | None = None):
    base = merge(base_extra or {})
    snap = lambda label, files: Snapshot.from_sources(label, files)  # noqa: E731
    return analyse(
        snap("base", base),
        snap("a", merge(base_extra or {}, a)),
        snap("b", merge(base_extra or {}, b)),
        snap("merged", merged if merged is not None else merge(base_extra or {}, a, b)),
        {"a": "branch-a", "b": "branch-b"},
    )


def caller(body: str, imports: str = "from app.users import get_user\n") -> dict:
    return {"app/caller.py": imports + "\n\ndef use(u):\n    " + body + "\n"}


# ---------------------------------------------------------------- positives
BREAKS = {
    # R1 removed function
    "R1 module alias attribute": (
        {"app/users.py": USERS_NO_GET}, caller("return users.get_user(u)", "import app.users as users\n"), "R1"),
    "R1 plain import chain": (
        {"app/users.py": USERS_NO_GET}, caller("return app.users.get_user(u)", "import app.users\n"), "R1"),
    "R1 from package import module": (
        {"app/text.py": TEXT.split("\n\n\n")[0] + "\n"}, caller("return text.initials(u)", "from app import text\n"), "R1"),
    "R1 same-module call": (
        {"app/text.py": "def initials(name):\n    return name[:1]\n"},
        {"app/text.py": TEXT + "\n\ndef title(n):\n    return display_name(n, upper=True)\n"}, "R1",
        # Both sides edit text.py in different hunks; this is Git's clean merge.
        {"app/text.py": "def initials(name):\n    return name[:1]\n\n\ndef title(n):\n    return display_name(n, upper=True)\n"}),
    # R2 incompatible signature
    "R2 missing required argument": ({"app/users.py": USERS_REQUIRED}, caller("return get_user(u)"), "R2"),
    "R2 excess positional": (
        {"app/text.py": TEXT.replace("name, upper=False", "name")},
        caller("return display_name(u, True)", "from app.text import display_name\n"), "R2"),
    "R2 renamed keyword": (
        {"app/text.py": TEXT.replace("upper=False", "uppercase=False")},
        caller("return display_name(u, upper=True)", "from app.text import display_name\n"), "R2"),
    "R2 positional-only by keyword": (
        {"app/users.py": USERS.replace("def get_user(user_id)", "def get_user(user_id, /)")},
        caller("return get_user(user_id=u)"), "R2"),
    "R2 new required keyword-only": (
        {"app/users.py": USERS.replace("def get_user(user_id)", "def get_user(user_id, *, fields)").replace(
            "get_user(1)", "get_user(1, fields=())")},
        caller("return get_user(u)"), "R2"),
    "R2 through an import alias": ({"app/users.py": USERS_REQUIRED}, caller("return gu(u)", "from app.users import get_user as gu\n"), "R2"),
    "R2 through a module alias": ({"app/users.py": USERS_REQUIRED}, caller("return users.get_user(u)", "import app.users as users\n"), "R2"),
    "R2 relative import": ({"app/users.py": USERS_REQUIRED}, caller("return get_user(u)", "from .users import get_user\n"), "R2"),
    # R3 broken local import
    "R3 module deleted": (
        {"app/users.py": None, "app/directory.py": USERS}, caller("return get_user(u)"), "R3"),
    "R3 module alias of deleted module": (
        {"app/text.py": None}, caller("return t.initials(u)", "import app.text as t\n"), "R3"),
    "R3 function removed from surviving module": (
        {"app/users.py": "def get_user(user_id):\n    return {'id': user_id}\n"},
        caller("return list_users()", "from app.users import list_users\n"), "R3"),
    "R3 relative import of deleted module": ({"app/users.py": None, "app/store.py": USERS},
                                             caller("return get_user(u)", "from .users import get_user\n"), "R3"),
}


@pytest.mark.parametrize("name", list(BREAKS))
def test_break_is_found_with_provenance(name):
    a, b, rule, *merged = BREAKS[name]
    result = run(a, b, merged=merge(*merged) if merged else None)
    assert result.status == "SILENT_BREAK", (result.findings, result.excluded, result.unsupported)
    assert [f["rule_id"] for f in result.findings] == [rule]
    finding = result.findings[0]
    assert finding["provenance"]["use"]["branch"] == "b"
    assert finding["provenance"]["change"]["branch"] == "a"
    assert finding["provenance"]["use"]["ref"] == "branch-b"
    assert "Git reported no textual conflicts" in finding["message"]


@pytest.mark.parametrize("name", list(BREAKS))
def test_break_is_found_in_either_orientation(name):
    a, b, rule, *merged = BREAKS[name]
    result = run(b, a, merged=merge(*merged) if merged else None)
    assert [f["rule_id"] for f in result.findings] == [rule]
    assert result.findings[0]["provenance"]["use"]["branch"] == "a"


def test_c1_message_matches_the_proposal():
    result = run({"app/users.py": USERS_REQUIRED},
                 {"app/badge.py": '"""Badge."""\n\nfrom app.users import get_user\n\n\ndef badge_line(user_id):\n'
                                  '    user = get_user(user_id)\n    return user\n'})
    (finding,) = result.findings
    assert finding["file"] == "app/badge.py" and finding["line"] == 7
    assert finding["message"].startswith(
        "Incompatible signature at app/badge.py line 7: get_user(user_id) supplies 1 positional argument, "
        "but branch-a changed app/users.py to get_user(user_id, include_email). "
        "The call was introduced by branch-b; Git reported no textual conflicts."
    )
    assert finding["provenance"]["change"]["before"] == "get_user(user_id)"


# ---------------------------------------------------------------- safe cases
SAFE = {
    "optional parameter added": ({"app/users.py": USERS_OPTIONAL}, caller("return get_user(u)")),
    "compatible keyword call": (
        {"app/text.py": TEXT.replace("name, upper=False", "name, upper=False, suffix=''")},
        caller("return display_name(name=u, upper=True)", "from app.text import display_name\n")),
    "import alias, optional parameter": (
        {"app/text.py": TEXT.replace("def initials(name)", "def initials(name, sep='')")},
        caller("return ini(u)", "from app.text import initials as ini\n")),
    "parameter shadows removed function": (
        {"app/text.py": TEXT.split("\n\n\n")[0] + "\n"},
        {"app/caller.py": "def use(u, initials):\n    return initials(u)\n"}),
    "local shadows removed function": (
        {"app/users.py": "def get_user(user_id):\n    return {'id': user_id}\n"},
        caller("list_users = lambda: []\n    return list_users()", "")),
    "identical branches": (caller("return get_user(u)"), caller("return get_user(u)")),
    "unrelated changes": ({"app/users.py": USERS + "\n\ndef count():\n    return 1\n"}, {"app/new.py": "X = 1\n"}),
    "unrelated function removed": ({"app/text.py": TEXT.split("\n\n\n")[1]}, caller("return initials(u)", "from app.text import initials\n")),
    "positional-only called positionally": (
        {"app/users.py": USERS.replace("def get_user(user_id)", "def get_user(user_id, /)")}, caller("return get_user(u)")),
    "keyword-only optional": (
        {"app/users.py": USERS.replace("def get_user(user_id)", "def get_user(user_id, *, include_email=False)")},
        caller("return get_user(u)")),
    "caller updated on the changing branch": (
        {"app/users.py": USERS_REQUIRED, "app/roster.py": "from app.users import get_user\n\n\ndef r():\n    return get_user(1, True)\n"},
        {"app/text.py": TEXT + "\n\ndef extra():\n    return 1\n"}),
    "no branch changes at all": ({}, {}),
}


@pytest.mark.parametrize("name", list(SAFE))
def test_safe_pair(name):
    a, b = SAFE[name]
    result = run(a, b)
    assert result.status == "SAFE", (result.findings, result.unsupported)
    assert result.findings == []


# ---------------------------------------------------------------- exclusions
LEGACY = {"app/legacy.py": "from app.users import get_user\n\n\ndef old(u):\n    return get_user(u, verbose=True)\n"}


def test_existing_defect_is_excluded_not_reported():
    result = run({"app/users.py": USERS_OPTIONAL}, caller("return get_user(u)"), base_extra=LEGACY)
    assert result.status == "SAFE"
    assert [e["file"] for e in result.excluded] == ["app/legacy.py"]
    assert result.excluded[0]["excluded_because"] == "already incompatible at the common ancestor"
    assert result.coverage["existing_defects_excluded"] == 1


def test_existing_defect_does_not_hide_a_real_break():
    result = run({"app/users.py": USERS_REQUIRED}, caller("return get_user(u)"), base_extra=LEGACY)
    assert [f["file"] for f in result.findings] == ["app/caller.py"]
    assert [e["file"] for e in result.excluded] == ["app/legacy.py"]


def test_defect_on_the_other_branch_alone_is_not_a_merge_break():
    # A changes the signature but forgets one of its own callers.
    a = {"app/users.py": USERS_REQUIRED, "app/roster.py": "from app.users import get_user\n\n\ndef r():\n    return get_user(1)\n"}
    base_extra = {"app/roster.py": "from app.users import get_user\n\n\ndef r():\n    return get_user(1)\n"}
    result = run(a, {"app/new.py": "X = 1\n"}, base_extra=base_extra)
    assert result.findings == []
    assert result.excluded and "branch-a alone" in result.excluded[0]["excluded_because"]


def test_inherited_use_is_found_when_its_binding_changes():
    # The call line exists on base and is unchanged on both branches, but B
    # replaces the local helper it called with an import of A's changed function.
    base_extra = {"app/caller.py": "def get_user(u):\n    return u\n\n\ndef use(u):\n    return get_user(u)\n"}
    b = {"app/caller.py": "from app.users import get_user\n\n\ndef use(u):\n    return get_user(u)\n"}
    result = run({"app/users.py": USERS_REQUIRED}, b, base_extra=base_extra)
    (finding,) = result.findings
    assert finding["rule_id"] == "R2"
    assert finding["provenance"]["use"]["origin"] == "inherited"


# ---------------------------------------------------------------- abstention
@pytest.mark.parametrize(
    ("b", "reason"),
    [
        (caller("return get_user(*u)"), "*args"),
        (caller("return get_user(u)", "from app.users import *\n"), "wildcard"),
        ({"app/broken.py": "def x(:\n"}, None),
    ],
)
def test_relevant_unsupported_code_is_inconclusive(b, reason):
    result = run({"app/users.py": USERS_REQUIRED}, b)
    assert result.status == "INCONCLUSIVE"
    assert not result.coverage["complete"]
    if reason:
        assert any(reason in u["reason"] for u in result.unsupported if u["relevant"])
    else:
        assert result.coverage["syntax_errors"]


def test_irrelevant_unsupported_code_does_not_block_safe():
    b = caller("return json_dumps(*u)", "from json import dumps as json_dumps\n")
    b["app/plugin.py"] = "from app.text import *\n\n\ndef p():\n    return initials('x')\n"
    result = run({"app/users.py": USERS_OPTIONAL}, b)
    assert result.status == "SAFE"
    assert result.coverage["unsupported_total"] >= 1
    assert result.coverage["unsupported_relevant"] == 0


def test_findings_win_over_incomplete_coverage():
    b = caller("return get_user(u)")
    b["app/broken.py"] = "def x(:\n"
    result = run({"app/users.py": USERS_REQUIRED}, b)
    assert result.status == "SILENT_BREAK"
    assert not result.coverage["complete"]
