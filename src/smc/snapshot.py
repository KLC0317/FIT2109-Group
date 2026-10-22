"""One exported code state (base, A, B or the merged tree), parsed with ast."""

from __future__ import annotations

import ast
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath


@dataclass
class ParsedModule:
    name: str  # dotted name relative to the source root, e.g. "profileapp.users"
    path: str  # repository-relative POSIX path, e.g. "profileapp/users.py"
    is_package: bool  # True for __init__.py
    tree: ast.Module | None
    error: str | None = None


@dataclass
class Snapshot:
    label: str
    commit: str | None
    source_root: str
    modules: dict[str, ParsedModule] = field(default_factory=dict)
    # Every package implied by a module path, including namespace packages.
    packages: set[str] = field(default_factory=set)
    syntax_errors: list[tuple[str, str]] = field(default_factory=list)

    def has_module(self, name: str) -> bool:
        return name in self.modules or name in self.packages

    def add(self, path: str, source: bytes | str) -> None:
        named = module_name(path, self.source_root)
        if named is None:
            return
        name, is_package = named
        try:
            tree = ast.parse(source, filename=path)
            error = None
        except (SyntaxError, ValueError) as exc:
            tree = None
            line = getattr(exc, "lineno", None)
            error = f"{exc.__class__.__name__}: {getattr(exc, 'msg', exc)}" + (
                f" (line {line})" if line else ""
            )
            self.syntax_errors.append((path, error))
        self.modules[name] = ParsedModule(name, path, is_package, tree, error)
        parts = name.split(".")
        upto = len(parts) if is_package else len(parts) - 1
        for i in range(1, upto + 1):
            self.packages.add(".".join(parts[:i]))

    @classmethod
    def from_sources(
        cls,
        label: str,
        sources: dict[str, str],
        source_root: str = ".",
        commit: str | None = None,
    ) -> Snapshot:
        """Build a snapshot from {path: source}; used by the unit tests."""
        snap = cls(label, commit, normalise_root(source_root))
        for path in sorted(sources):
            snap.add(path, sources[path])
        return snap

    @classmethod
    def load(
        cls,
        label: str,
        directory: Path,
        paths: list[str],
        source_root: str = ".",
        commit: str | None = None,
    ) -> Snapshot:
        """Parse the listed repository-relative files from an exported tree."""
        snap = cls(label, commit, normalise_root(source_root))
        for path in sorted(paths):
            snap.add(path, (directory / path).read_bytes())
        return snap


def normalise_root(source_root: str) -> str:
    root = PurePosixPath(source_root.replace("\\", "/")).as_posix().strip("/")
    return root or "."


def module_name(path: str, source_root: str = ".") -> tuple[str, bool] | None:
    """Map a repository path to (dotted module name, is_package).

    Returns None for files outside the source root, non-Python files and
    paths that are not importable names.
    """
    root = normalise_root(source_root)
    p = PurePosixPath(path)
    if p.suffix != ".py":
        return None
    if root != ".":
        try:
            p = p.relative_to(root)
        except ValueError:
            return None
    parts = list(p.with_suffix("").parts)
    is_package = parts[-1] == "__init__"
    if is_package:
        parts = parts[:-1]
    if not parts or not all(part.isidentifier() for part in parts):
        return None
    return ".".join(parts), is_package
