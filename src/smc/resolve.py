"""Resolve uses to module-qualified targets within one code state.

Supported bindings: module-level functions called directly from the same
module, ``import module [as alias]`` followed by attribute calls, and
``from module import function [as alias]``. Everything else either resolves
to something we do not track (classes, variables, external packages) or is
reported as unsupported with a reason.
"""

from __future__ import annotations

from dataclasses import dataclass, replace

from smc.snapshot import Snapshot
from smc.symbols import FunctionInfo, ModuleIndex
from smc.uses import Use

# Statuses
FUNCTION = "function"  # a tracked module-level function
MODULE = "module"  # a local module or package
PRESENT = "present"  # imports: the name exists but is not a tracked function
UNBOUND = "unbound"  # same-module name with no binding
MISSING_ATTR = "missing_attr"  # module exists, name absent
MISSING_MODULE = "missing_module"  # local module absent
UNTRACKED = "untracked"  # shadowed, a class, a variable, a builtin ...
EXTERNAL = "external"  # outside the source root
UNSUPPORTED = "unsupported"  # cannot be resolved safely


@dataclass(frozen=True)
class Resolution:
    status: str
    module: str | None = None
    name: str | None = None
    function: FunctionInfo | None = None
    via: str = ""  # same-module | module-attribute | from-import | import
    reason: str = ""

    @property
    def symbol(self) -> str | None:
        if self.module and self.name:
            return f"{self.module}.{self.name}"
        return self.module


def top(module: str) -> str:
    return module.split(".")[0]


class Resolver:
    def __init__(self, snapshot: Snapshot, indexes: dict[str, ModuleIndex], local_tops: set[str]):
        self.snapshot = snapshot
        self.indexes = indexes
        self.local_tops = local_tops

    # -- modules --------------------------------------------------------------
    def module(self, name: str) -> Resolution:
        if top(name) not in self.local_tops:
            return Resolution(EXTERNAL, name, reason="outside the source root")
        if self.snapshot.has_module(name):
            return Resolution(MODULE, name)
        return Resolution(MISSING_MODULE, name, reason=f"no module {name!r}")

    def member(self, module: str, name: str, *, for_import: bool) -> Resolution:
        """Attribute `name` of local module `module` (from-import or module.attr)."""
        via = "from-import" if for_import else "module-attribute"
        mod = self.module(module)
        if mod.status != MODULE:
            return Resolution(mod.status, module, name, via=via, reason=mod.reason)
        submodule = f"{module}.{name}"
        index = self.indexes.get(module)  # None for namespace packages
        bindings = index.bindings.get(name, []) if index else []
        if bindings:
            if len(bindings) > 1 or bindings[0].conditional:
                if for_import and any(not b.conditional for b in bindings):
                    return Resolution(PRESENT, module, name, via=via)
                how = f"bound {len(bindings)} times" if len(bindings) > 1 else "bound conditionally"
                return Resolution(UNSUPPORTED, module, name, via=via,
                                  reason=f"ambiguous binding: {module}.{name} is {how}")
            binding = bindings[0]
            if binding.kind == "function":
                return Resolution(FUNCTION, module, name, binding.function, via=via)
            if binding.kind in ("import_module", "import_from"):
                if self.snapshot.has_module(submodule):
                    return Resolution(MODULE, submodule, via=via)
                if for_import:
                    return Resolution(PRESENT, module, name, via=via)
                return Resolution(UNSUPPORTED, module, name, via=via,
                                  reason=f"{module}.{name} is a re-export")
            if binding.kind == "delete":
                return Resolution(UNSUPPORTED, module, name, via=via, reason=f"{module}.{name} is deleted with del")
            if for_import:
                return Resolution(PRESENT, module, name, via=via)
            return Resolution(UNTRACKED, module, name, via=via, reason=f"{module}.{name} is a {binding.kind}")
        if self.snapshot.has_module(submodule):
            return Resolution(MODULE, submodule, via=via)
        if index and index.has_getattr:
            return Resolution(UNSUPPORTED, module, name, via=via, reason=f"{module} defines __getattr__")
        if index and index.wildcard_from:
            return Resolution(UNSUPPORTED, module, name, via=via,
                              reason=f"{module} re-exports with a wildcard import")
        return Resolution(MISSING_ATTR, module, name, via=via, reason=f"{module} has no {name!r}")

    # -- names ----------------------------------------------------------------
    def name_in_module(self, module: str, name: str) -> Resolution:
        index = self.indexes[module]
        if name in index.global_writes:
            return Resolution(UNSUPPORTED, module, name, via="same-module",
                              reason=f"{name!r} is assigned through a global statement")
        bindings = index.bindings.get(name, [])
        if not bindings:
            if index.wildcard_from:
                return Resolution(UNSUPPORTED, module, name, via="same-module",
                                  reason=f"{name!r} may come from a wildcard import of {', '.join(index.wildcard_from)}")
            return Resolution(UNBOUND, module, name, via="same-module", reason=f"{name!r} is not bound in {module}")
        if len(bindings) > 1 or bindings[0].conditional:
            how = f"bound {len(bindings)} times" if len(bindings) > 1 else "bound conditionally"
            return Resolution(UNSUPPORTED, module, name, via="same-module",
                              reason=f"ambiguous binding: {name!r} is {how} in {module}")
        binding = bindings[0]
        if binding.kind == "function":
            return Resolution(FUNCTION, module, name, binding.function, via="same-module")
        if binding.kind == "import_module":
            return self.module(binding.target)
        if binding.kind == "import_from":
            if binding.target is None:
                return Resolution(UNSUPPORTED, module, name, via="from-import", reason=binding.problem or "")
            if top(binding.target) not in self.local_tops:
                return Resolution(EXTERNAL, binding.target, binding.attr, via="from-import")
            return replace(self.member(binding.target, binding.attr, for_import=False), via="from-import")
        if binding.kind == "delete":
            return Resolution(UNSUPPORTED, module, name, via="same-module", reason=f"{name!r} is deleted with del")
        return Resolution(UNTRACKED, module, name, via="same-module", reason=f"{name!r} is a {binding.kind}")

    # -- uses -----------------------------------------------------------------
    def resolve(self, use: Use) -> Resolution:
        if use.kind == "import_module":
            res = self.module(use.target)
            return Resolution(res.status, res.module, via="import", reason=res.reason)
        if use.kind == "import_from":
            if use.target is None:
                return Resolution(UNSUPPORTED, via="import", reason=use.problem or "")
            if top(use.target) not in self.local_tops:
                return Resolution(EXTERNAL, use.target, use.name, via="import")
            res = self.member(use.target, use.name, for_import=True)
            return Resolution(res.status, res.module, res.name, res.function, "import", res.reason)
        return self.call(use)

    def call(self, use: Use) -> Resolution:
        if use.shadowed:
            return Resolution(UNTRACKED, reason=f"{use.chain[0]!r} is a local or parameter binding")
        res = self.name_in_module(use.module, use.chain[0])
        for attr in use.chain[1:]:
            if res.status == MODULE:
                res = self.member(res.module, attr, for_import=False)
            elif res.status in (FUNCTION, UNTRACKED, PRESENT):
                return Resolution(UNTRACKED, reason=f"attribute of a non-module object in {use.text}")
            else:
                return res  # missing, unbound, external or unsupported propagate
        if res.status == MODULE:
            return Resolution(UNTRACKED, res.module, reason="calling a module object")
        return res
