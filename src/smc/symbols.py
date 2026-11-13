"""Module-qualified symbol index: what each module binds at module level.

Only module-level functions are tracked as call targets. Every other kind of
module-level binding is still recorded, so that the resolver can tell an
absent name from one bound to something we do not analyse, and can report
names bound more than once as ambiguous.
"""

from __future__ import annotations

import ast
from dataclasses import dataclass, field

from smc.signature import Signature
from smc.snapshot import ParsedModule, Snapshot

# Decorators known to keep the wrapped function's call signature.
SIGNATURE_PRESERVING_DECORATORS = frozenset(
    {"functools.cache", "functools.lru_cache", "cache", "lru_cache"}
)


@dataclass(frozen=True)
class FunctionInfo:
    module: str
    name: str
    path: str
    lineno: int
    signature: Signature
    decorators: tuple[str, ...] = ()
    is_async: bool = False

    @property
    def qualname(self) -> str:
        return f"{self.module}.{self.name}"

    @property
    def unsupported_decorators(self) -> tuple[str, ...]:
        return tuple(d for d in self.decorators if d not in SIGNATURE_PRESERVING_DECORATORS)

    def render(self) -> str:
        return self.signature.render(self.name)


@dataclass(frozen=True)
class Binding:
    # function | class | assign | import_module | import_from | other | delete
    kind: str
    lineno: int
    conditional: bool = False  # inside if/try/for/while/with/match at module level
    target: str | None = None  # imports: absolute module bound or imported from
    attr: str | None = None  # import_from: imported name
    function: FunctionInfo | None = None
    problem: str | None = None  # e.g. relative import beyond the top-level package


@dataclass(frozen=True)
class DynamicImport:
    lineno: int
    target: str | None  # constant module name, or None if computed at runtime


@dataclass
class ModuleIndex:
    name: str
    path: str
    is_package: bool
    bindings: dict[str, list[Binding]] = field(default_factory=dict)
    wildcard_from: list[str] = field(default_factory=list)
    has_getattr: bool = False  # module-level __getattr__ (PEP 562)
    global_writes: set[str] = field(default_factory=set)
    dynamic_imports: list[DynamicImport] = field(default_factory=list)

    def bind(self, name: str, binding: Binding) -> None:
        self.bindings.setdefault(name, []).append(binding)

    @property
    def package(self) -> str:
        """Package used to resolve relative imports in this module."""
        if self.is_package:
            return self.name
        return self.name.rpartition(".")[0]

    def functions(self) -> dict[str, FunctionInfo]:
        """Names bound exactly once, unconditionally, to a function."""
        found = {}
        for name, bindings in self.bindings.items():
            if len(bindings) == 1 and not bindings[0].conditional and bindings[0].function:
                found[name] = bindings[0].function
        return found


def resolve_relative(package: str, level: int, module: str | None) -> str | None:
    """Absolute module for `from <level dots><module> import ...`, or None."""
    if level == 0:
        return module
    parts = package.split(".") if package else []
    if level - 1 >= len(parts):
        return None  # no parent package, or beyond the top-level package
    base = parts[: len(parts) - (level - 1)]
    if module:
        base.append(module)
    return ".".join(base) if base else None


def dotted(node: ast.expr) -> str:
    if isinstance(node, ast.Call):
        node = node.func
    return ast.unparse(node)


class _ModuleBinder:
    def __init__(self, index: ModuleIndex):
        self.index = index

    def walk(self, body: list[ast.stmt], conditional: bool) -> None:
        for stmt in body:
            self.statement(stmt, conditional)

    def statement(self, stmt: ast.stmt, conditional: bool) -> None:
        idx = self.index
        if isinstance(stmt, (ast.FunctionDef, ast.AsyncFunctionDef)):
            info = FunctionInfo(
                module=idx.name,
                name=stmt.name,
                path=idx.path,
                lineno=stmt.lineno,
                signature=Signature.from_ast(stmt.args),
                decorators=tuple(dotted(d) for d in stmt.decorator_list),
                is_async=isinstance(stmt, ast.AsyncFunctionDef),
            )
            idx.bind(stmt.name, Binding("function", stmt.lineno, conditional, function=info))
            if stmt.name == "__getattr__":
                idx.has_getattr = True
        elif isinstance(stmt, ast.ClassDef):
            idx.bind(stmt.name, Binding("class", stmt.lineno, conditional))
        elif isinstance(stmt, ast.Import):
            for alias in stmt.names:
                if alias.asname:
                    idx.bind(alias.asname, Binding("import_module", stmt.lineno, conditional, target=alias.name))
                else:
                    top = alias.name.split(".")[0]
                    idx.bind(top, Binding("import_module", stmt.lineno, conditional, target=top))
        elif isinstance(stmt, ast.ImportFrom):
            target = resolve_relative(idx.package, stmt.level, stmt.module)
            problem = None if target else "relative import beyond the top-level package"
            for alias in stmt.names:
                if alias.name == "*":
                    if target:
                        idx.wildcard_from.append(target)
                    continue
                idx.bind(
                    alias.asname or alias.name,
                    Binding("import_from", stmt.lineno, conditional, target=target, attr=alias.name, problem=problem),
                )
        elif isinstance(stmt, (ast.Assign, ast.AnnAssign, ast.AugAssign)):
            targets = stmt.targets if isinstance(stmt, ast.Assign) else [stmt.target]
            for target in targets:
                for name in _store_names(target):
                    idx.bind(name, Binding("assign", stmt.lineno, conditional))
        elif isinstance(stmt, ast.Delete):
            for target in stmt.targets:
                for name in _store_names(target):
                    idx.bind(name, Binding("delete", stmt.lineno, conditional))
        elif isinstance(stmt, (ast.For, ast.AsyncFor)):
            for name in _store_names(stmt.target):
                idx.bind(name, Binding("other", stmt.lineno, True))
            self.walk(stmt.body, True)
            self.walk(stmt.orelse, True)
        elif isinstance(stmt, (ast.While, ast.If)):
            self.walk(stmt.body, True)
            self.walk(stmt.orelse, True)
        elif isinstance(stmt, (ast.With, ast.AsyncWith)):
            for item in stmt.items:
                if item.optional_vars is not None:
                    for name in _store_names(item.optional_vars):
                        idx.bind(name, Binding("other", stmt.lineno, True))
            self.walk(stmt.body, True)
        elif isinstance(stmt, (ast.Try, ast.TryStar)):
            self.walk(stmt.body, True)
            for handler in stmt.handlers:
                if handler.name:
                    idx.bind(handler.name, Binding("other", handler.lineno, True))
                self.walk(handler.body, True)
            self.walk(stmt.orelse, True)
            self.walk(stmt.finalbody, True)
        elif isinstance(stmt, ast.Match):
            for case in stmt.cases:
                for node in ast.walk(case.pattern):
                    name = getattr(node, "name", None) or getattr(node, "rest", None)
                    if isinstance(name, str):
                        idx.bind(name, Binding("other", stmt.lineno, True))
                self.walk(case.body, True)
        # Walrus targets in simple module-level statements also bind names.
        if isinstance(stmt, (ast.Expr, ast.Assign, ast.AnnAssign, ast.AugAssign)):
            for node in ast.walk(stmt):
                if isinstance(node, ast.NamedExpr) and isinstance(node.target, ast.Name):
                    idx.bind(node.target.id, Binding("assign", stmt.lineno, True))


def _store_names(target: ast.expr) -> list[str]:
    if isinstance(target, ast.Name):
        return [target.id]
    if isinstance(target, (ast.Tuple, ast.List)):
        return [n for elt in target.elts for n in _store_names(elt)]
    if isinstance(target, ast.Starred):
        return _store_names(target.value)
    return []  # attribute or subscript targets do not bind module names


def _scan_whole_module(index: ModuleIndex, tree: ast.Module) -> None:
    """Global statements and dynamic imports anywhere in the module."""
    for node in ast.walk(tree):
        if isinstance(node, ast.Global):
            index.global_writes.update(node.names)
        elif isinstance(node, ast.Call):
            func = node.func
            name = func.id if isinstance(func, ast.Name) else func.attr if isinstance(func, ast.Attribute) else None
            if name in ("__import__", "import_module"):
                arg = node.args[0] if node.args else None
                target = arg.value if isinstance(arg, ast.Constant) and isinstance(arg.value, str) else None
                index.dynamic_imports.append(DynamicImport(node.lineno, target))


def index_module(module: ParsedModule) -> ModuleIndex:
    index = ModuleIndex(module.name, module.path, module.is_package)
    if module.tree is not None:
        _ModuleBinder(index).walk(module.tree.body, conditional=False)
        _scan_whole_module(index, module.tree)
        index.dynamic_imports.sort(key=lambda d: d.lineno)
    return index


def index_snapshot(snapshot: Snapshot) -> dict[str, ModuleIndex]:
    return {name: index_module(mod) for name, mod in snapshot.modules.items()}
