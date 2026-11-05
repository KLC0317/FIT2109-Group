"""AI-assisted activity 3: adversarial cases suggested by an assistant.

M3 asked for safe counterexamples and boundary cases for signatures, import
aliases and shadowing (docs/ai-use.md, activity 3). Every expectation below
was confirmed by running the code with CPython on base, A, B and the merge
before it was written down (M1 checked). Suggestion IDs match the log;
rejected suggestions are listed there with the reason. None of these cases
are holdout cases.
"""

from __future__ import annotations

import pytest

from smc.rules import analyse
from smc.snapshot import Snapshot

USERS = "def get_user(user_id, include_email=False):\n    return {'id': user_id}\n"
REQUIRED = "def get_user(user_id, include_email):\n    return {'id': user_id}\n"


def analyse_pair(base: dict, a: dict, b: dict, merged: dict | None = None):
    def state(label, *layers):
        files = {}
        for layer in layers:
            files.update(layer)
        return Snapshot.from_sources(label, {k: v for k, v in files.items() if v is not None})

    full = dict(base)
    full.update(a)
    full.update(b)
    return analyse(state("base", base), state("a", base, a), state("b", base, b),
                   Snapshot.from_sources("merged", {k: v for k, v in (merged or full).items() if v is not None}))


BASE = {"app/__init__.py": "", "app/users.py": USERS}


# S02 (accepted) keyword matching a positional-only name is absorbed by **kwargs.
def test_s02_positional_only_name_absorbed_by_kwargs():
    a = {"app/users.py": "def get_user(user_id, /, **options):\n    return {'id': user_id}\n"}
    b = {"app/c.py": "from app.users import get_user\n\n\ndef f():\n    return get_user(1, user_id=2)\n"}
    assert analyse_pair(BASE, a, b).status == "SAFE"


# S03 (accepted) a default added to a middle parameter, caller passes it by keyword.
def test_s03_default_added_caller_uses_keyword():
    base = {**BASE, "app/users.py": "def get_user(user_id, fmt, include_email=False):\n    return user_id\n"}
    a = {"app/users.py": "def get_user(user_id, fmt='short', include_email=False):\n    return user_id\n"}
    b = {"app/c.py": "from app.users import get_user\n\n\ndef f():\n    return get_user(1, fmt='long')\n"}
    assert analyse_pair(base, a, b).status == "SAFE"


# S04 (modified) AI expected a finding for a function stored in a variable.
# CPython does fail after the merge, but an assignment is outside the
# supported bindings, so the documented behaviour is "not tracked". Kept as
# a limitation test so a future change is a conscious one.
def test_s04_function_stored_in_variable_is_a_documented_limitation():
    b = {"app/c.py": "import app.users as u\n\nlookup = u.get_user\n\n\ndef f():\n    return lookup(1)\n"}
    result = analyse_pair(BASE, {"app/users.py": REQUIRED}, b)
    assert result.findings == []


# S05 (accepted) the caller module binds get_user twice: ambiguous, so abstain.
def test_s05_rebound_import_is_ambiguous():
    b = {"app/c.py": "from app.users import get_user\nfrom app.other import get_user\n\n\ndef f():\n    return get_user(1)\n",
         "app/other.py": "def get_user(x):\n    return x\n"}
    result = analyse_pair(BASE, {"app/users.py": REQUIRED}, b)
    assert result.status == "INCONCLUSIVE"
    assert any("ambiguous" in u["reason"] for u in result.unsupported if u["relevant"])


# S06 (accepted) call from a function nested in a method still reaches the module function.
def test_s06_nested_function_in_method():
    b = {"app/c.py": "from app.users import get_user\n\n\nclass Page:\n    def render(self):\n"
                     "        def inner():\n            return get_user(1)\n        return inner()\n"}
    result = analyse_pair(BASE, {"app/users.py": REQUIRED}, b)
    assert [(f["rule_id"], f["scope"]) for f in result.findings] == [("R2", "Page.render.inner")]


# S07 (accepted) optional import fallback: conditional binding, abstain.
def test_s07_try_except_import_fallback():
    b = {"app/c.py": "try:\n    from app.users import get_user\nexcept ImportError:\n    get_user = None\n\n\n"
                     "def f():\n    return get_user(1)\n"}
    assert analyse_pair(BASE, {"app/users.py": REQUIRED}, b).status == "INCONCLUSIVE"


# S08 (modified) AI said removing a default is "safe for positional callers".
# Running it showed the caller that omits the argument fails, so the
# expectation was corrected to a break.
def test_s08_removing_a_default_breaks_callers_that_omit_it():
    b = {"app/c.py": "from app.users import get_user\n\n\ndef f():\n    return get_user(1)\n"}
    result = analyse_pair(BASE, {"app/users.py": REQUIRED}, b)
    (finding,) = result.findings
    assert finding["reason"] == "missing 1 required positional argument: 'include_email'"


# S11 (accepted) a method with the same name as the changed function is not confused with it.
def test_s11_method_with_the_same_name():
    b = {"app/c.py": "class Repo:\n    def get_user(self, user_id):\n        return user_id\n\n\n"
                     "def f():\n    return Repo().get_user(1)\n"}
    assert analyse_pair(BASE, {"app/users.py": REQUIRED}, b).status == "SAFE"


# S12 (accepted) 'from . import users' then users.get_user().
def test_s12_relative_module_import():
    b = {"app/c.py": "from . import users\n\n\ndef f():\n    return users.get_user(1)\n"}
    result = analyse_pair(BASE, {"app/users.py": REQUIRED}, b)
    assert [f["rule_id"] for f in result.findings] == ["R2"]


# S13 (accepted) the caller deletes its own import binding: unsupported, abstain.
def test_s13_del_of_the_imported_name():
    b = {"app/c.py": "from app.users import get_user\ndel get_user\n\n\ndef f():\n    return get_user(1)\n"}
    assert analyse_pair(BASE, {"app/users.py": REQUIRED}, b).status == "INCONCLUSIVE"


@pytest.mark.parametrize(
    ("definition", "call"),
    [
        # S15 (accepted) boundary pairs for the binder, all confirmed with CPython.
        ("def get_user(user_id, *args, include_email):\n    pass\n", "get_user(1, 2, include_email=True)"),
        ("def get_user(*, user_id):\n    pass\n", "get_user(user_id=1)"),
        ("def get_user(user_id=None, /):\n    pass\n", "get_user()"),
    ],
)
def test_s15_binder_boundaries_are_compatible(definition, call):
    b = {"app/c.py": f"from app.users import get_user\n\n\ndef f():\n    return {call}\n"}
    a = {"app/users.py": definition}
    base = {**BASE, "app/users.py": definition}
    assert analyse_pair(base, a, b).status == "SAFE"
