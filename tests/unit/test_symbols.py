"""Module naming, relative imports and the module-level symbol index."""

from __future__ import annotations

import pytest

from smc.snapshot import Snapshot, module_name
from smc.symbols import index_module, resolve_relative


@pytest.mark.parametrize(
    ("path", "root", "expected"),
    [
        ("profileapp/users.py", ".", ("profileapp.users", False)),
        ("profileapp/__init__.py", ".", ("profileapp", True)),
        ("main.py", ".", ("main", False)),
        ("src/pkg/mod.py", "src", ("pkg.mod", False)),
        ("src/pkg/__init__.py", "src/", ("pkg", True)),
        ("other/pkg/mod.py", "src", None),
        ("README.md", ".", None),
        ("my-scripts/tool.py", ".", None),
        ("__init__.py", ".", None),
    ],
)
def test_module_name(path, root, expected):
    assert module_name(path, root) == expected


@pytest.mark.parametrize(
    ("package", "level", "module", "expected"),
    [
        ("profileapp", 0, "profileapp.users", "profileapp.users"),
        ("profileapp", 1, "users", "profileapp.users"),
        ("profileapp", 1, None, "profileapp"),
        ("profileapp.sub", 2, "users", "profileapp.users"),
        ("profileapp", 2, "users", None),
        ("profileapp", 3, "users", None),
        ("", 1, "x", None),
    ],
)
def test_resolve_relative(package, level, module, expected):
    assert resolve_relative(package, level, module) == expected


def index(source: str, path: str = "pkg/mod.py"):
    snap = Snapshot.from_sources("s", {path: source})
    return index_module(next(iter(snap.modules.values())))


def test_functions_and_signatures_are_indexed():
    idx = index("def get_user(user_id, include_email=False):\n    pass\n\nasync def fetch(x, /): pass\n")
    functions = idx.functions()
    assert functions["get_user"].render() == "get_user(user_id, include_email=False)"
    assert functions["get_user"].lineno == 1
    assert functions["fetch"].is_async


def test_every_binding_kind_is_recorded():
    idx = index(
        "import os\n"
        "import profileapp.users\n"
        "import profileapp.textfmt as tf\n"
        "from .users import get_user as gu\n"
        "class C: pass\n"
        "X = 1\n"
        "a, (b, c) = 1, (2, 3)\n"
        "del X\n"
    )
    kinds = {name: [b.kind for b in bindings] for name, bindings in idx.bindings.items()}
    assert kinds == {
        "os": ["import_module"], "profileapp": ["import_module"], "tf": ["import_module"],
        "gu": ["import_from"], "C": ["class"], "X": ["assign", "delete"],
        "a": ["assign"], "b": ["assign"], "c": ["assign"],
    }
    assert idx.bindings["tf"][0].target == "profileapp.textfmt"
    assert idx.bindings["profileapp"][0].target == "profileapp"
    assert (idx.bindings["gu"][0].target, idx.bindings["gu"][0].attr) == ("pkg.users", "get_user")


def test_conditional_and_repeated_definitions_are_not_trackable_functions():
    idx = index(
        "try:\n    from fast import helper\nexcept ImportError:\n    def helper(x): pass\n"
        "def twice(): pass\ndef twice(a): pass\n"
        "def once(): pass\n"
    )
    assert set(idx.functions()) == {"once"}
    assert all(b.conditional for b in idx.bindings["helper"])
    assert len(idx.bindings["twice"]) == 2


def test_dynamic_features_are_noted():
    idx = index(
        "from os.path import *\n"
        "import importlib\n"
        "def __getattr__(name): pass\n"
        "def load(n):\n    global cache\n    cache = importlib.import_module(n)\n"
        "plugin = __import__('pkg.plugin')\n"
    )
    assert idx.wildcard_from == ["os.path"]
    assert idx.has_getattr
    assert idx.global_writes == {"cache"}
    assert [(d.lineno, d.target) for d in idx.dynamic_imports] == [(6, None), (7, "pkg.plugin")]


def test_relative_import_beyond_top_level_is_flagged():
    idx = index("from ...far import thing\n", path="pkg/mod.py")
    assert idx.bindings["thing"][0].problem == "relative import beyond the top-level package"


def test_package_relative_imports_resolve_from_the_package_itself():
    idx = index("from .users import get_user\n", path="profileapp/__init__.py")
    assert idx.bindings["get_user"][0].target == "profileapp.users"


def test_syntax_errors_are_recorded_not_raised():
    snap = Snapshot.from_sources("s", {"pkg/bad.py": "def broken(:\n", "pkg/good.py": "x = 1\n"})
    assert [path for path, _ in snap.syntax_errors] == ["pkg/bad.py"]
    assert snap.modules["pkg.bad"].tree is None
    assert snap.has_module("pkg") and snap.has_module("pkg.good")
