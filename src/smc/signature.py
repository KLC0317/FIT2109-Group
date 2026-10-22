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
