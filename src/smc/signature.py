"""Function signatures extracted from ast.arguments."""

from __future__ import annotations

import ast
from dataclasses import dataclass, field


@dataclass(frozen=True)
class Signature:
    posonly: tuple[str, ...]
    positional: tuple[str, ...]  # positional-or-keyword parameters
    n_defaults: int  # trailing defaults over posonly + positional
    vararg: str | None
    kwonly: tuple[str, ...]
    kwonly_required: tuple[str, ...]
    kwarg: str | None
    # Default expressions are kept for display only; they do not affect binding.
    default_text: tuple[str, ...] = field(default=(), compare=False)
    kw_default_text: tuple[tuple[str, str], ...] = field(default=(), compare=False)

    @classmethod
    def from_ast(cls, args: ast.arguments) -> Signature:
        kw_defaults = tuple(
            (arg.arg, ast.unparse(default))
            for arg, default in zip(args.kwonlyargs, args.kw_defaults)
            if default is not None
        )
        return cls(
            posonly=tuple(a.arg for a in args.posonlyargs),
            positional=tuple(a.arg for a in args.args),
            n_defaults=len(args.defaults),
            vararg=args.vararg.arg if args.vararg else None,
            kwonly=tuple(a.arg for a in args.kwonlyargs),
            kwonly_required=tuple(
                a.arg for a, d in zip(args.kwonlyargs, args.kw_defaults) if d is None
            ),
            kwarg=args.kwarg.arg if args.kwarg else None,
            default_text=tuple(ast.unparse(d) for d in args.defaults),
            kw_default_text=kw_defaults,
        )

    @property
    def all_positional(self) -> tuple[str, ...]:
        return self.posonly + self.positional

    @property
    def required_positional(self) -> tuple[str, ...]:
        names = self.all_positional
        return names[: len(names) - self.n_defaults]

    def render(self, name: str) -> str:
        """Display form, e.g. get_user(user_id, /, include_email=False, *, sep)."""
        names = self.all_positional
        first_default = len(names) - self.n_defaults
        parts: list[str] = []
        for i, param in enumerate(names):
            if i >= first_default:
                text = self.default_text[i - first_default] if self.default_text else "..."
                parts.append(f"{param}={text}")
            else:
                parts.append(param)
            if self.posonly and i == len(self.posonly) - 1:
                parts.append("/")
        if self.vararg:
            parts.append(f"*{self.vararg}")
        elif self.kwonly:
            parts.append("*")
        kw_defaults = dict(self.kw_default_text)
        for param in self.kwonly:
            if param in self.kwonly_required:
                parts.append(param)
            else:
                parts.append(f"{param}={kw_defaults.get(param, '...')}")
        if self.kwarg:
            parts.append(f"**{self.kwarg}")
        return f"{name}({', '.join(parts)})"


@dataclass(frozen=True)
class CallShape:
    """The explicit arguments of one call site."""

    n_positional: int
    keywords: tuple[str, ...]
    star_args: bool = False  # f(*args)
    star_kwargs: bool = False  # f(**kwargs)

    @classmethod
    def from_call(cls, call: ast.Call) -> CallShape:
        return cls(
            n_positional=sum(1 for a in call.args if not isinstance(a, ast.Starred)),
            keywords=tuple(k.arg for k in call.keywords if k.arg is not None),
            star_args=any(isinstance(a, ast.Starred) for a in call.args),
            star_kwargs=any(k.arg is None for k in call.keywords),
        )

    @property
    def unpacked(self) -> bool:
        return self.star_args or self.star_kwargs

    def describe(self) -> str:
        parts = []
        if self.n_positional:
            parts.append(_plural(self.n_positional, "positional argument"))
        if self.keywords:
            parts.append("keyword " + ", ".join(repr(k) for k in self.keywords))
        return " and ".join(parts) if parts else "no arguments"


def _plural(n: int, noun: str) -> str:
    return f"{n} {noun}" if n == 1 else f"{n} {noun}s"


def _names(names: list[str]) -> str:
    quoted = [repr(n) for n in names]
    if len(quoted) == 1:
        return quoted[0]
    return ", ".join(quoted[:-1]) + " and " + quoted[-1]


def bind(signature: Signature, shape: CallShape) -> list[str]:
    """Bind explicit arguments to a signature the way CPython would.

    Returns the problems found, worded like CPython's TypeError messages;
    an empty list means the call is compatible. Calls with unpacked
    *args/**kwargs must be treated as unsupported by the caller.
    """
    problems: list[str] = []
    positional = signature.all_positional
    filled: set[str] = set(positional[: shape.n_positional])

    if shape.n_positional > len(positional) and signature.vararg is None:
        # Same wording as CPython's too_many_positional().
        given = shape.n_positional
        takes = len(positional)
        if signature.n_defaults:
            sig, plural = f"from {takes - signature.n_defaults} to {takes}", True
        else:
            sig, plural = str(takes), takes != 1
        kwonly_given = sum(1 for k in shape.keywords if k in signature.kwonly)
        kwonly_sig = ""
        if kwonly_given:
            kwonly_sig = (f" positional argument{'s' if given != 1 else ''} (and {kwonly_given} "
                          f"keyword-only argument{'s' if kwonly_given != 1 else ''})")
        verb = "was" if given == 1 and not kwonly_given else "were"
        problems.append(
            f"takes {sig} positional argument{'s' if plural else ''} but {given}{kwonly_sig} {verb} given"
        )

    posonly_as_keyword = []
    for keyword in shape.keywords:
        if keyword in signature.posonly:
            if signature.kwarg is None:
                posonly_as_keyword.append(keyword)
            continue  # absorbed by **kwargs otherwise
        if keyword in signature.positional or keyword in signature.kwonly:
            if keyword in filled:
                problems.append(f"got multiple values for argument {keyword!r}")
            filled.add(keyword)
        elif signature.kwarg is None:
            problems.append(f"got an unexpected keyword argument {keyword!r}")
    if posonly_as_keyword:
        problems.append(
            "got some positional-only arguments passed as keyword arguments: "
            + ", ".join(repr(k) for k in posonly_as_keyword)
        )

    missing = [
        p for p in signature.required_positional
        if p not in filled and p not in posonly_as_keyword
    ]
    if missing:
        problems.append(
            f"missing {_plural(len(missing), 'required positional argument')}: {_names(missing)}"
        )
    missing_kw = [p for p in signature.kwonly_required if p not in filled]
    if missing_kw:
        problems.append(
            f"missing {_plural(len(missing_kw), 'required keyword-only argument')}: {_names(missing_kw)}"
        )
    return problems
