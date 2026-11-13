"""Collect uses (calls and imports) together with their lexical scope.

A call's callee is recorded as a name chain: ``get_user(...)`` is
("get_user",) and ``users.get_user(...)`` is ("users", "get_user"). The
first name is looked up through the enclosing scopes the way Python does it:
function, lambda and comprehension scopes are searched innermost first,
class bodies only when the call is directly inside them, then the module.
A name bound in a function scope (parameter, assignment, nested def, import,
except/with/for target) shadows the module binding, so the use is marked
``shadowed`` and is not tracked.
"""

from __future__ import annotations

import ast
from collections import Counter
from dataclasses import dataclass, field

from smc.signature import CallShape
from smc.symbols import resolve_relative


@dataclass(frozen=True)
class Use:
    kind: str  # call | import_module | import_from
    module: str
    path: str
    lineno: int
    scope: str  # "<module>", "badge_line", "Report.render", ...
    text: str  # callee or import statement text; part of the key
    chain: tuple[str, ...] = ()  # call: callee name chain
    shape: CallShape | None = None  # call: explicit arguments
    shadowed: bool = False  # call: first name bound in an enclosing local scope
    target: str | None = None  # imports: absolute module
    name: str | None = None  # import_from: imported name
    problem: str | None = None  # e.g. unresolvable relative import
    source: str = ""  # call: the whole call expression, shown in diagnostics
    key: tuple = field(default=(), compare=False)


@dataclass
class _Scope:
    kind: str  # module | function | lambda | class | comprehension
    name: str
    bound: set[str] = field(default_factory=set)
    globals: set[str] = field(default_factory=set)
    nonlocals: set[str] = field(default_factory=set)


class _BoundNames(ast.NodeVisitor):
    """Names a block binds in its own scope, without entering nested scopes."""

    def __init__(self) -> None:
        self.bound: set[str] = set()
        self.globals: set[str] = set()
        self.nonlocals: set[str] = set()

    def visit_Name(self, node: ast.Name) -> None:
        if isinstance(node.ctx, (ast.Store, ast.Del)):
            self.bound.add(node.id)

    def visit_FunctionDef(self, node: ast.FunctionDef | ast.AsyncFunctionDef) -> None:
        self.bound.add(node.name)
        for expr in node.decorator_list + node.args.defaults + [d for d in node.args.kw_defaults if d]:
            self.visit(expr)

    visit_AsyncFunctionDef = visit_FunctionDef

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        self.bound.add(node.name)
        for expr in node.decorator_list + node.bases + [k.value for k in node.keywords]:
            self.visit(expr)

    def visit_Lambda(self, node: ast.Lambda) -> None:
        for expr in node.args.defaults + [d for d in node.args.kw_defaults if d]:
            self.visit(expr)

    def _comprehension(self, node: ast.expr) -> None:
        # Only the first iterable is evaluated in the enclosing scope; walrus
        # targets inside a comprehension also bind in the enclosing scope.
        self.visit(node.generators[0].iter)
        for sub in ast.walk(node):
            if isinstance(sub, ast.NamedExpr) and isinstance(sub.target, ast.Name):
                self.bound.add(sub.target.id)

    visit_ListComp = visit_SetComp = visit_GeneratorExp = visit_DictComp = _comprehension

    def visit_Import(self, node: ast.Import) -> None:
        for alias in node.names:
            self.bound.add(alias.asname or alias.name.split(".")[0])

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        for alias in node.names:
            if alias.name != "*":
                self.bound.add(alias.asname or alias.name)

    def visit_ExceptHandler(self, node: ast.ExceptHandler) -> None:
        if node.name:
            self.bound.add(node.name)
        self.generic_visit(node)

    def visit_MatchAs(self, node: ast.MatchAs) -> None:
        if node.name:
            self.bound.add(node.name)
        self.generic_visit(node)

    def visit_MatchStar(self, node: ast.MatchStar) -> None:
        if node.name:
            self.bound.add(node.name)

    def visit_MatchMapping(self, node: ast.MatchMapping) -> None:
        if node.rest:
            self.bound.add(node.rest)
        self.generic_visit(node)

    def visit_Global(self, node: ast.Global) -> None:
        self.globals.update(node.names)

    def visit_Nonlocal(self, node: ast.Nonlocal) -> None:
        self.nonlocals.update(node.names)


def _params(args: ast.arguments) -> set[str]:
    every = args.posonlyargs + args.args + args.kwonlyargs
    names = {a.arg for a in every}
    if args.vararg:
        names.add(args.vararg.arg)
    if args.kwarg:
        names.add(args.kwarg.arg)
    return names


def _block_scope(kind: str, name: str, body: list[ast.AST], params: set[str] = frozenset()) -> _Scope:
    finder = _BoundNames()
    for node in body:
        finder.visit(node)
    bound = (finder.bound | set(params)) - finder.globals - finder.nonlocals
    return _Scope(kind, name, bound, finder.globals, finder.nonlocals)


def call_chain(func: ast.expr) -> tuple[str, ...] | None:
    parts: list[str] = []
    while isinstance(func, ast.Attribute):
        parts.append(func.attr)
        func = func.value
    if not isinstance(func, ast.Name):
        return None  # e.g. factory()(), items[0](), (lambda: x)()
    parts.append(func.id)
    return tuple(reversed(parts))


class UseCollector(ast.NodeVisitor):
    def __init__(self, module: str, path: str, is_package: bool):
        self.module = module
        self.path = path
        self.package = module if is_package else module.rpartition(".")[0]
        self.stack: list[_Scope] = []
        self.uses: list[Use] = []

    # -- scope handling ---------------------------------------------------
    def _scope_name(self) -> str:
        names = [s.name for s in self.stack if s.kind in ("function", "class")]
        return ".".join(names) if names else "<module>"

    def is_shadowed(self, name: str) -> bool:
        innermost = len(self.stack) - 1
        for depth in range(innermost, -1, -1):
            scope = self.stack[depth]
            if scope.kind == "module":
                return False
            if scope.kind == "class" and depth != innermost:
                continue  # class bodies are not visible from nested scopes
            if name in scope.globals:
                return False
            if name in scope.nonlocals:
                continue
            if name in scope.bound:
                return True
        return False

    def collect(self, tree: ast.Module) -> list[Use]:
        self.stack = [_Scope("module", "<module>")]
        for stmt in tree.body:
            self.visit(stmt)
        counts: Counter = Counter()
        keyed = []
        for use in self.uses:
            base = (use.module, use.scope, use.kind, use.text)
            keyed.append(_with_key(use, base + (counts[base],)))
            counts[base] += 1
        return keyed

    def _enter(self, scope: _Scope, body: list[ast.AST]) -> None:
        self.stack.append(scope)
        for node in body:
            self.visit(node)
        self.stack.pop()

    def visit_FunctionDef(self, node: ast.FunctionDef | ast.AsyncFunctionDef) -> None:
        for expr in node.decorator_list + node.args.defaults + [d for d in node.args.kw_defaults if d]:
            self.visit(expr)
        self._enter(_block_scope("function", node.name, node.body, _params(node.args)), node.body)

    visit_AsyncFunctionDef = visit_FunctionDef

    def visit_Lambda(self, node: ast.Lambda) -> None:
        for expr in node.args.defaults + [d for d in node.args.kw_defaults if d]:
            self.visit(expr)
        self._enter(_Scope("lambda", "<lambda>", _params(node.args)), [node.body])

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        for expr in node.decorator_list + node.bases + [k.value for k in node.keywords]:
            self.visit(expr)
        self._enter(_block_scope("class", node.name, node.body), node.body)

    def _comprehension(self, node: ast.expr) -> None:
        generators = node.generators
        self.visit(generators[0].iter)
        targets: set[str] = set()
        for gen in generators:
            targets.update(n.id for n in ast.walk(gen.target) if isinstance(n, ast.Name))
        inner: list[ast.AST] = []
        for i, gen in enumerate(generators):
            if i:
                inner.append(gen.iter)
            inner.extend(gen.ifs)
        inner.extend([node.key, node.value] if isinstance(node, ast.DictComp) else [node.elt])
        self._enter(_Scope("comprehension", "<comprehension>", targets), inner)

    visit_ListComp = visit_SetComp = visit_GeneratorExp = visit_DictComp = _comprehension

    # -- uses ---------------------------------------------------------------
    def visit_Call(self, node: ast.Call) -> None:
        chain = call_chain(node.func)
        if chain is not None:
            self.uses.append(
                Use(
                    kind="call",
                    module=self.module,
                    path=self.path,
                    lineno=node.lineno,
                    scope=self._scope_name(),
                    text=ast.unparse(node.func),
                    chain=chain,
                    shape=CallShape.from_call(node),
                    shadowed=self.is_shadowed(chain[0]),
                    source=_clip(ast.unparse(node)),
                )
            )
        self.generic_visit(node)

    def visit_Import(self, node: ast.Import) -> None:
        for alias in node.names:
            self.uses.append(
                Use(
                    kind="import_module",
                    module=self.module,
                    path=self.path,
                    lineno=node.lineno,
                    scope=self._scope_name(),
                    text=f"import {alias.name}" + (f" as {alias.asname}" if alias.asname else ""),
                    target=alias.name,
                )
            )

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        target = resolve_relative(self.package, node.level, node.module)
        source = "." * node.level + (node.module or "")
        for alias in node.names:
            if alias.name == "*":
                continue  # wildcard imports are reported through the symbol index
            self.uses.append(
                Use(
                    kind="import_from",
                    module=self.module,
                    path=self.path,
                    lineno=node.lineno,
                    scope=self._scope_name(),
                    text=f"from {source} import {alias.name}"
                    + (f" as {alias.asname}" if alias.asname else ""),
                    target=target,
                    name=alias.name,
                    problem=None if target else "relative import beyond the top-level package",
                )
            )


def _clip(text: str, limit: int = 120) -> str:
    return text if len(text) <= limit else text[: limit - 3] + "..."


def _with_key(use: Use, key: tuple) -> Use:
    object.__setattr__(use, "key", key)
    return use


def collect_uses(module: str, path: str, is_package: bool, tree: ast.Module) -> list[Use]:
    return UseCollector(module, path, is_package).collect(tree)
