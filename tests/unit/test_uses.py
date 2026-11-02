"""Lexical scoping of call sites: which names shadow module-level functions."""

from __future__ import annotations

import ast
import textwrap

import pytest

from smc.uses import collect_uses


def calls(source: str, module: str = "pkg.mod"):
    tree = ast.parse(textwrap.dedent(source))
    return [u for u in collect_uses(module, "pkg/mod.py", False, tree) if u.kind == "call"]


def shadowed(source: str, name: str = "f") -> list[bool]:
    return [u.shadowed for u in calls(source) if u.chain[0] == name]


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        ("f()", [False]),
        ("def g():\n    f()", [False]),
        ("def g(f):\n    f()", [True]),
        ("def g(*f):\n    f()", [True]),
        ("def g(**f):\n    f()", [True]),
        ("def g(*, f=None):\n    f()", [True]),
        ("def g():\n    f = print\n    f()", [True]),
        ("def g():\n    f()\n    f = print", [True]),  # local for the whole function body
        ("def g():\n    for f in []:\n        f()", [True]),
        ("def g():\n    with open('x') as f:\n        f()", [True]),
        ("def g():\n    try:\n        pass\n    except Exception as f:\n        f()", [True]),
        ("def g():\n    import f\n    f()", [True]),
        ("def g():\n    from x import f\n    f()", [True]),
        ("def g():\n    def f(): pass\n    f()", [True]),
        ("def g():\n    global f\n    f = 1\n    f()", [False]),
        ("def g(f):\n    def h():\n        f()", [True]),
        ("def g():\n    f = 1\n    def h():\n        nonlocal f\n        f()", [True]),
        ("class C:\n    def f(self): pass\n    f()", [True]),
        ("class C:\n    def f(self): pass\n    def m(self):\n        f()", [False]),
        ("g = lambda f: f()", [True]),
        ("g = lambda x: f()", [False]),
        ("[f() for f in []]", [True]),
        ("[f() for x in []]", [False]),
        ("[x for x in f()]", [False]),
        ("def g(f):\n    return [f() for x in []]", [True]),
        ("def g():\n    if (f := print):\n        f()", [True]),
    ],
)
def test_shadowing(source, expected):
    assert shadowed(source) == expected


def test_call_chains_and_shapes():
    (call,) = calls("profileapp.users.get_user(1, include_email=True)")
    assert call.chain == ("profileapp", "users", "get_user")
    assert call.text == "profileapp.users.get_user"
    assert call.source == "profileapp.users.get_user(1, include_email=True)"
    assert (call.shape.n_positional, call.shape.keywords) == (1, ("include_email",))


def test_calls_without_a_name_chain_are_ignored():
    assert [u.chain for u in calls("factory()()\nitems[0]()\n(lambda: 1)()")] == [("factory",)]


def test_scope_names_and_keys_are_stable_across_line_shifts():
    first = calls("def badge_line(u):\n    return get_user(u)\n")
    second = calls("\n\n# moved down\n\ndef badge_line(u):\n    return get_user(u)\n")
    assert first[0].scope == "badge_line"
    assert first[0].key == second[0].key
    assert first[0].lineno != second[0].lineno


def test_repeated_calls_get_ordinals():
    keys = [u.key for u in calls("def g():\n    f(1)\n    f(2)\n")]
    assert [k[-1] for k in keys] == [0, 1]


def test_import_uses():
    tree = ast.parse("import a.b as ab\nfrom .users import get_user as gu\nfrom . import textfmt\n")
    uses = collect_uses("profileapp.badge", "profileapp/badge.py", False, tree)
    assert [(u.kind, u.target, u.name) for u in uses] == [
        ("import_module", "a.b", None),
        ("import_from", "profileapp.users", "get_user"),
        ("import_from", "profileapp", "textfmt"),
    ]
