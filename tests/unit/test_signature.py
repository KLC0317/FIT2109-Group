"""Signature binder checked against CPython itself.

Every case defines a real function and calls it; bind() must report a
problem exactly when CPython raises TypeError, with the same wording.
"""

from __future__ import annotations

import ast

import pytest

from smc.signature import CallShape, Signature, bind

CASES = [
    # (definition, call)
    ("def f(user_id): pass", "f(1)"),
    ("def f(user_id, include_email): pass", "f(1)"),
    ("def f(user_id, include_email): pass", "f(1, True)"),
    ("def f(user_id, include_email): pass", "f(1, include_email=True)"),
    ("def f(user_id, include_email=False): pass", "f(1)"),
    ("def f(name): pass", "f('a', True)"),
    ("def f(name, upper=False): pass", "f('a', upper=True)"),
    ("def f(name, uppercase=False): pass", "f('a', upper=True)"),
    ("def f(a, b=1): pass", "f(1, a=2)"),
    ("def f(a, b=1): pass", "f(b=2)"),
    ("def f(a, b=1): pass", "f(b=2, a=1)"),
    ("def f(user_id, /): pass", "f(1)"),
    ("def f(user_id, /): pass", "f(user_id=1)"),
    ("def f(user_id, /, **kw): pass", "f(1, user_id=2)"),
    ("def f(a, /, b, *, c): pass", "f(1, 2, c=3)"),
    ("def f(a, /, b, *, c): pass", "f(1, 2)"),
    ("def f(a, /, b, *, c): pass", "f(1, 2, 3)"),
    ("def f(a, *, sep): pass", "f(1, sep='-')"),
    ("def f(a, *, sep=''): pass", "f(1)"),
    ("def f(a, *, sep=''): pass", "f(1, '-')"),
    ("def f(a, *args): pass", "f(1, 2, 3)"),
    ("def f(a, *args, key): pass", "f(1, 2, 3)"),
    ("def f(a, **kwargs): pass", "f(1, anything=2)"),
    ("def f(a, **kwargs): pass", "f(a=1, b=2)"),
    ("def f(): pass", "f()"),
    ("def f(): pass", "f(1)"),
    ("def f(): pass", "f(x=1)"),
    ("def f(a, b, c): pass", "f(1)"),
    ("def f(a, b, /, c=3, *, d, e=5): pass", "f(1, 2, d=4)"),
    ("def f(a, b, /, c=3, *, d, e=5): pass", "f(1, 2, 3, 4, d=4)"),
    ("def f(a, b, /, c=3, *, d, e=5): pass", "f(1, b=2, d=4)"),
    ("def f(a=1, /, b=2): pass", "f(b=3)"),
]


def cpython_error(definition: str, call: str) -> str | None:
    namespace: dict = {}
    exec(definition, namespace)
    try:
        eval(call, namespace)
    except TypeError as exc:
        return str(exc)
    return None


def shape_of(call: str) -> CallShape:
    return CallShape.from_call(ast.parse(call, mode="eval").body)


def signature_of(definition: str) -> Signature:
    return Signature.from_ast(ast.parse(definition).body[0].args)


@pytest.mark.parametrize(("definition", "call"), CASES)
def test_bind_agrees_with_cpython(definition, call):
    expected = cpython_error(definition, call)
    problems = bind(signature_of(definition), shape_of(call))
    assert bool(problems) == (expected is not None), (problems, expected)
    if expected:
        # CPython reports one problem at a time; ours must include it.
        assert any(p in expected for p in problems), (problems, expected)


@pytest.mark.parametrize(
    ("call", "star_args", "star_kwargs"),
    [("f(*xs)", True, False), ("f(**kw)", False, True), ("f(1, *xs, k=2, **kw)", True, True)],
)
def test_unpacked_arguments_are_flagged(call, star_args, star_kwargs):
    shape = shape_of(call)
    assert (shape.star_args, shape.star_kwargs, shape.unpacked) == (star_args, star_kwargs, True)


@pytest.mark.parametrize(
    ("definition", "rendered"),
    [
        ("def get_user(user_id): pass", "get_user(user_id)"),
        ("def get_user(user_id, include_email): pass", "get_user(user_id, include_email)"),
        ("def f(a, /, b=2, *args, c, d=4, **kw): pass", "f(a, /, b=2, *args, c, d=4, **kw)"),
        ("def f(a, *, sep=''): pass", "f(a, *, sep='')"),
    ],
)
def test_render(definition, rendered):
    assert signature_of(definition).render(definition.split()[1].split("(")[0]) == rendered


def test_default_values_do_not_change_identity():
    assert signature_of("def f(a=1): pass") == signature_of("def f(a=2): pass")
    assert signature_of("def f(a=1): pass") != signature_of("def f(a): pass")
