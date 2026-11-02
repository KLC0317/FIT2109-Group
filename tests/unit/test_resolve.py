"""Resolving uses to targets inside one code state."""

from __future__ import annotations

import pytest

from smc.resolve import Resolver
from smc.snapshot import Snapshot
from smc.symbols import index_snapshot
from smc.uses import collect_uses

LIBRARY = {
    "profileapp/__init__.py": "from profileapp.users import get_user\n",
    "profileapp/users.py": "def get_user(user_id):\n    pass\n\nclass UnknownUser(Exception): pass\nLIMIT = 3\n",
    "profileapp/textfmt.py": "def initials(name):\n    pass\n",
    "profileapp/maybe.py": "try:\n    def fast(): pass\nexcept Exception:\n    fast = None\n",
    "profileapp/lazy.py": "def __getattr__(name):\n    pass\n",
    "profileapp/star.py": "from profileapp.textfmt import *\n",
}


def resolve(caller_source: str, *, extra: dict | None = None):
    sources = {**LIBRARY, **(extra or {}), "profileapp/caller.py": caller_source}
    snap = Snapshot.from_sources("s", sources)
    indexes = index_snapshot(snap)
    resolver = Resolver(snap, indexes, {"profileapp"})
    module = snap.modules["profileapp.caller"]
    uses = collect_uses(module.name, module.path, False, module.tree)
    return [(u.text, resolver.resolve(u)) for u in uses if u.kind == "call"]


def last(caller_source: str, **kw):
    return resolve(caller_source, **kw)[-1][1]


@pytest.mark.parametrize(
    ("caller", "status", "symbol", "via"),
    [
        ("from profileapp.users import get_user\nget_user(1)", "function", "profileapp.users.get_user", "from-import"),
        ("from profileapp.users import get_user as g\ng(1)", "function", "profileapp.users.get_user", "from-import"),
        ("from .users import get_user\nget_user(1)", "function", "profileapp.users.get_user", "from-import"),
        ("import profileapp.users as users\nusers.get_user(1)", "function", "profileapp.users.get_user", "module-attribute"),
        ("import profileapp.users\nprofileapp.users.get_user(1)", "function", "profileapp.users.get_user", "module-attribute"),
        ("from profileapp import textfmt\ntextfmt.initials('a')", "function", "profileapp.textfmt.initials", "module-attribute"),
        ("def helper(): pass\nhelper()", "function", "profileapp.caller.helper", "same-module"),
        ("import profileapp.users as users\nusers.gone(1)", "missing_attr", "profileapp.users.gone", "module-attribute"),
        ("missing()", "unbound", "profileapp.caller.missing", "same-module"),
        ("import profileapp.nothere as n\nn.f()", "missing_module", "profileapp.nothere", ""),
    ],
)
def test_supported_bindings(caller, status, symbol, via):
    res = last(caller)
    assert res.status == status
    assert res.symbol == symbol
    if via:
        assert res.via == via


@pytest.mark.parametrize(
    ("caller", "reason_part"),
    [
        ("from profileapp import get_user\nget_user(1)", "re-export"),
        ("from profileapp.maybe import fast\nfast()", "ambiguous binding"),
        ("import profileapp.lazy as lazy\nlazy.anything()", "__getattr__"),
        ("from profileapp.star import *\ninitials('a')", "wildcard import"),
        ("import profileapp.star as star\nstar.initials('a')", "wildcard import"),
        ("if True:\n    def h(): pass\nh()", "ambiguous binding"),
        ("def h(): pass\nh = None\nh()", "bound 2 times"),
        ("def g():\n    global h\n    h = 1\nh()", "global statement"),
    ],
)
def test_unsupported_bindings_say_why(caller, reason_part):
    res = last(caller)
    assert res.status == "unsupported"
    assert reason_part in res.reason


@pytest.mark.parametrize(
    ("caller", "status"),
    [
        ("from profileapp.users import UnknownUser\nUnknownUser()", "untracked"),
        ("from profileapp.users import LIMIT\nLIMIT()", "untracked"),
        ("import os\nos.getcwd()", "external"),
        ("from json import dumps\ndumps(1)", "external"),
        ("def g(get_user):\n    get_user(1)", "untracked"),
        ("print(1)", "unbound"),
    ],
)
def test_things_we_do_not_track(caller, status):
    assert last(caller).status == status


def test_import_uses_accept_any_existing_name():
    snap = Snapshot.from_sources("s", {**LIBRARY, "profileapp/caller.py": (
        "from profileapp.users import LIMIT, UnknownUser, get_user, gone\n"
        "from profileapp import get_user as reexported\n"
        "from profileapp.ghost import thing\n"
        "import profileapp.textfmt\n"
    )})
    resolver = Resolver(snap, index_snapshot(snap), {"profileapp"})
    module = snap.modules["profileapp.caller"]
    statuses = [(u.name or u.target, resolver.resolve(u).status)
                for u in collect_uses(module.name, module.path, False, module.tree)]
    assert statuses == [
        ("LIMIT", "present"), ("UnknownUser", "present"), ("get_user", "function"), ("gone", "missing_attr"),
        ("get_user", "present"), ("thing", "missing_module"), ("profileapp.textfmt", "module"),
    ]
