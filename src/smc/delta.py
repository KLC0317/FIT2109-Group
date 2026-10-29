"""What one branch changed relative to the common ancestor."""

from __future__ import annotations

from dataclasses import dataclass, field

from smc.snapshot import Snapshot
from smc.symbols import Binding, FunctionInfo, ModuleIndex

REMOVED = "removed"  # function no longer defined in its module
MODULE_REMOVED = "module_removed"  # the whole module is gone
SIGNATURE = "signature"  # parameters changed
DECORATORS = "decorators"  # decorator list changed


@dataclass(frozen=True)
class FunctionChange:
    module: str
    name: str
    kind: str
    before: FunctionInfo
    after: FunctionInfo | None

    @property
    def path(self) -> str:
        return (self.after or self.before).path

    @property
    def lineno(self) -> int:
        return (self.after or self.before).lineno


@dataclass
class BranchDelta:
    side: str  # "a" or "b"
    functions: dict[tuple[str, str], FunctionChange] = field(default_factory=dict)
    removed_modules: dict[str, str] = field(default_factory=dict)  # module -> base path
    rebound: set[tuple[str, str]] = field(default_factory=set)  # module-level binding changed

    def changed_names(self) -> set[str]:
        names = {name for _, name in self.functions}
        names.update(module.rpartition(".")[2] for module in self.removed_modules)
        names.update(name for _, name in self.rebound)
        return names

    def touches_module(self, module: str) -> bool:
        return any(module == m or module.startswith(m + ".") for m in self.removed_modules)

    def is_empty(self) -> bool:
        return not (self.functions or self.removed_modules or self.rebound)


def _shape(binding: Binding) -> tuple:
    return (binding.kind, binding.target, binding.attr, binding.conditional)


def compare(
    side: str,
    base: Snapshot,
    base_index: dict[str, ModuleIndex],
    other: Snapshot,
    other_index: dict[str, ModuleIndex],
) -> BranchDelta:
    delta = BranchDelta(side)
    for module, before_index in base_index.items():
        after_index = other_index.get(module)
        if after_index is None:
            delta.removed_modules[module] = before_index.path
        before_functions = before_index.functions()
        after_functions = after_index.functions() if after_index else {}
        for name, before in before_functions.items():
            after = after_functions.get(name)
            if after_index is None:
                kind = MODULE_REMOVED
            elif after is None:
                kind = REMOVED
            elif after.signature != before.signature:
                kind = SIGNATURE
            elif after.decorators != before.decorators:
                kind = DECORATORS
            else:
                continue
            delta.functions[(module, name)] = FunctionChange(module, name, kind, before, after)
        if after_index is None:
            continue
        names = set(before_index.bindings) | set(after_index.bindings)
        for name in names:
            if name in before_functions and name in after_functions:
                continue
            before_shape = [_shape(b) for b in before_index.bindings.get(name, [])]
            after_shape = [_shape(b) for b in after_index.bindings.get(name, [])]
            if before_shape != after_shape and before_shape:
                delta.rebound.add((module, name))
    # Packages that only existed implicitly (namespace packages) count too.
    for package in base.packages - other.packages:
        if package not in base_index:
            delta.removed_modules.setdefault(package, package.replace(".", "/") + "/")
    return delta
