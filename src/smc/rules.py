"""The three detection rules and the four-state evidence check.

A finding needs evidence from the common ancestor, both branches and the
clean merge:

1. the use is compatible on the branch that contains it (the caller branch);
2. the other branch changed the definition or import the use relies on;
3. the merged tree still contains the use, and there the binding is absent
   or incompatible;
4. the same incompatibility is not already present at the common ancestor
   or on the other branch alone.

Both orientations are checked (A as caller, then B as caller). A use the
caller branch inherited from the ancestor and did not edit can still be a
finding when its binding changed. Existing defects and removed symbols that
nothing uses are excluded.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from smc import delta as d
from smc.logjson import log_event
from smc.resolve import (
    FUNCTION,
    MISSING_ATTR,
    MISSING_MODULE,
    MODULE,
    PRESENT,
    UNBOUND,
    UNSUPPORTED,
    UNTRACKED,
    EXTERNAL,
    Resolution,
    Resolver,
)
from smc.signature import bind
from smc.snapshot import Snapshot
from smc.symbols import ModuleIndex, index_snapshot
from smc.uses import Use, collect_uses

logger = logging.getLogger(__name__)

RULES = {
    "R1": "removed-function",
    "R2": "incompatible-signature",
    "R3": "broken-local-import",
}
RULE_TITLES = {
    "R1": "Removed function",
    "R2": "Incompatible signature",
    "R3": "Broken local import",
}
SIDES = ("a", "b")
OTHER = {"a": "b", "b": "a"}


@dataclass(frozen=True)
class Problem:
    rule: str
    reason: str
    resolution: Resolution


@dataclass(frozen=True)
class Check:
    resolution: Resolution
    problem: Problem | None = None
    unsupported: str | None = None


@dataclass
class State:
    label: str
    snapshot: Snapshot
    indexes: dict[str, ModuleIndex] = field(default_factory=dict)
    uses: dict[tuple, Use] = field(default_factory=dict)
    resolver: Resolver | None = None


@dataclass
class Result:
    status: str  # SAFE | SILENT_BREAK | INCONCLUSIVE
    findings: list[dict]
    coverage: dict
    excluded: list[dict]
    unsupported: list[dict]


def check(state: State, use: Use) -> Check:
    """Classify one use inside one code state."""
    res = state.resolver.resolve(use)
    if use.kind == "call":
        if res.status == FUNCTION:
            fn = res.function
            if use.shape.unpacked:
                return Check(res, unsupported=f"call to {fn.qualname} unpacks *args/**kwargs")
            if fn.unsupported_decorators:
                return Check(res, unsupported=f"{fn.qualname} has decorator(s) "
                                              f"{', '.join(fn.unsupported_decorators)} that may change its signature")
            problems = bind(fn.signature, use.shape)
            if problems:
                return Check(res, Problem("R2", "; ".join(problems), res))
            return Check(res)
        if res.status in (UNBOUND, MISSING_ATTR) and res.via in ("same-module", "module-attribute"):
            return Check(res, Problem("R1", res.reason, res))
        if res.status == UNSUPPORTED:
            return Check(res, unsupported=res.reason)
        return Check(res)
    if res.status in (MISSING_MODULE, MISSING_ATTR):
        return Check(res, Problem("R3", res.reason, res))
    if res.status == UNSUPPORTED:
        return Check(res, unsupported=res.reason)
    return Check(res)


def compatible_on_caller(rule: str, merged: Problem, caller: Check) -> bool:
    """Condition 1: the caller branch resolves the use to something valid."""
    if caller.problem or caller.unsupported:
        return False
    status = caller.resolution.status
    if rule in ("R1", "R2"):
        return status == FUNCTION
    if merged.resolution.status == MISSING_MODULE:
        return status in (MODULE, FUNCTION, PRESENT)
    # The module survives but the name is gone: only explicitly defined
    # functions and submodules are in scope.
    return status in (MODULE, FUNCTION)


class Analysis:
    def __init__(
        self,
        base: Snapshot,
        a: Snapshot,
        b: Snapshot,
        merged: Snapshot,
        refs: dict[str, str] | None = None,
    ):
        self.refs = {"a": "A", "b": "B", **(refs or {})}
        snapshots = {"base": base, "a": a, "b": b, "merged": merged}
        self.local_tops = {
            name.split(".")[0] for snap in snapshots.values() for name in snap.modules
        }
        self.states = {label: self._state(label, snap) for label, snap in snapshots.items()}
        base_state = self.states["base"]
        self.deltas = {
            side: d.compare(side, base, base_state.indexes, snapshots[side], self.states[side].indexes)
            for side in SIDES
        }
        self.changed_names = self.deltas["a"].changed_names() | self.deltas["b"].changed_names()
        for side, delta in self.deltas.items():
            log_event(logger, "delta", logging.DEBUG, branch=self.refs[side],
                      functions=sorted(f"{m}.{n}: {c.kind}" for (m, n), c in delta.functions.items()),
                      removed_modules=sorted(delta.removed_modules),
                      rebound=sorted(f"{m}.{n}" for m, n in delta.rebound))

    def _state(self, label: str, snapshot: Snapshot) -> State:
        state = State(label, snapshot, index_snapshot(snapshot))
        for module in snapshot.modules.values():
            if module.tree is None:
                continue
            for use in collect_uses(module.name, module.path, module.is_package, module.tree):
                state.uses[use.key] = use
        state.resolver = Resolver(snapshot, state.indexes, self.local_tops)
        return state

    # -- evidence -------------------------------------------------------------
    def _change(self, side: str, rule: str, use: Use, caller: Check, merged: Problem) -> dict | None:
        """Condition 2: what the other branch changed, or None."""
        delta = self.deltas[side]
        if rule in ("R1", "R2"):
            target = caller.resolution
            change = delta.functions.get((target.module, target.name))
            if change:
                return _function_change(change)
            if target.module and delta.touches_module(target.module):
                return _module_change(delta, target.module)
            if (use.module, use.chain[0]) in delta.rebound:
                return {"kind": "rebound", "symbol": f"{use.module}.{use.chain[0]}", "file": use.path,
                        "line": None, "before": None, "after": None}
            return None
        res = merged.resolution
        if res.status == MISSING_MODULE:
            return _module_change(delta, res.module) if delta.touches_module(res.module) else None
        change = delta.functions.get((res.module, res.name))
        if change:
            return _function_change(change)
        if (res.module, res.name) in delta.rebound:
            return {"kind": "rebound", "symbol": f"{res.module}.{res.name}", "file": None,
                    "line": None, "before": None, "after": None}
        return None

    def run(self) -> Result:
        merged = self.states["merged"]
        findings: list[dict] = []
        excluded: list[dict] = []
        unsupported: list[dict] = []
        counts = {"examined": 0, "tracked": 0, "shadowed": 0, "external": 0, "untracked": 0}

        for key, use in merged.uses.items():
            counts["examined"] += 1
            result = check(merged, use)
            status = result.resolution.status
            if use.kind == "call" and use.shadowed:
                counts["shadowed"] += 1
            elif status == EXTERNAL:
                counts["external"] += 1
            elif status in (FUNCTION, MODULE, PRESENT, MISSING_ATTR, MISSING_MODULE):
                counts["tracked"] += 1
            elif status in (UNTRACKED, UNBOUND):
                counts["untracked"] += 1

            if result.unsupported:
                unsupported.append(self._unsupported(use, result))
                log_event(logger, "unsupported", logging.DEBUG, file=use.path, line=use.lineno,
                          use=use.source or use.text, reason=result.unsupported,
                          relevant=unsupported[-1]["relevant"])
                continue
            if result.problem is None:
                continue
            finding, why_not = self._attribute(key, use, result.problem)
            if finding or why_not:  # names unbound everywhere (builtins) are not evidence
                log_event(logger, "decision", logging.DEBUG, file=use.path, line=use.lineno,
                          use=use.source or use.text, rule=result.problem.rule, reason=result.problem.reason,
                          outcome="finding" if finding else "excluded", because=why_not or "",
                          caller=finding["provenance"]["use"]["ref"] if finding else "",
                          change=finding["provenance"]["change"]["ref"] if finding else "")
            if finding:
                findings.append(finding)
            elif why_not:
                excluded.append({
                    "rule_id": result.problem.rule,
                    "file": use.path,
                    "line": use.lineno,
                    "use": use.source or use.text,
                    "reason": result.problem.reason,
                    "excluded_because": why_not,
                })

        unsupported.extend(self._dynamic_imports())
        syntax_errors = [
            {"state": label, "file": path, "error": error}
            for label, state in self.states.items()
            for path, error in state.snapshot.syntax_errors
        ]
        relevant = [u for u in unsupported if u["relevant"]]
        complete = not syntax_errors and not relevant
        if findings:
            status = "SILENT_BREAK"
        elif not complete:
            status = "INCONCLUSIVE"
        else:
            status = "SAFE"
        coverage = {
            "rules": list(RULES),
            "modules": {label: len(s.snapshot.modules) for label, s in self.states.items()},
            "uses_examined": counts["examined"],
            "uses_tracked": counts["tracked"],
            "uses_shadowed": counts["shadowed"],
            "uses_external": counts["external"],
            "uses_untracked": counts["untracked"],
            "unsupported_total": len(unsupported),
            "unsupported_relevant": len(relevant),
            "existing_defects_excluded": sum(1 for e in excluded if e["excluded_because"].startswith("already")),
            "branch_changes": {
                side: {
                    "functions": len(self.deltas[side].functions),
                    "removed_modules": len(self.deltas[side].removed_modules),
                    "rebound_names": len(self.deltas[side].rebound),
                }
                for side in SIDES
            },
            "syntax_errors": syntax_errors,
            "complete": complete,
        }
        findings.sort(key=lambda f: (f["file"], f["line"], f["rule_id"]))
        return Result(status, findings, coverage, excluded, unsupported)

    def _attribute(self, key: tuple, use: Use, merged: Problem) -> tuple[dict | None, str | None]:
        rule = merged.rule
        reasons = []
        for side in SIDES:
            caller_use = self.states[side].uses.get(key)
            if caller_use is None:
                continue
            caller = check(self.states[side], caller_use)
            if not compatible_on_caller(rule, merged, caller):
                continue
            other = OTHER[side]
            change = self._change(other, rule, use, caller, merged)
            if change is None:
                reasons.append(f"{self.refs[other]} did not change the definition or import it relies on")
                continue
            base_use = self.states["base"].uses.get(key)
            if base_use is not None and check(self.states["base"], base_use).problem:
                return None, "already incompatible at the common ancestor"
            other_use = self.states[other].uses.get(key)
            if other_use is not None and check(self.states[other], other_use).problem:
                return None, f"already incompatible on {self.refs[other]} alone"
            return self._finding(use, merged, side, caller_use, caller, change, base_use is not None), None

        # Not compatible on either branch: decide whether it is worth listing.
        base_use = self.states["base"].uses.get(key)
        if base_use is not None and check(self.states["base"], base_use).problem:
            if rule == "R2" or merged.resolution.status != UNBOUND:
                return None, "already incompatible at the common ancestor"
            return None, None  # an unbound name everywhere, e.g. a builtin
        if reasons:
            return None, reasons[0]
        if merged.resolution.status == UNBOUND:
            return None, None  # builtins and names this tool does not model
        return None, "incompatible on both branches before the merge"

    def _finding(self, use: Use, merged: Problem, side: str, caller_use: Use, caller: Check,
                 change: dict, inherited: bool) -> dict:
        rule = merged.rule
        other = OTHER[side]
        caller_ref, change_ref = self.refs[side], self.refs[other]
        origin = "inherited" if inherited else "introduced"
        symbol = change.get("symbol") or caller.resolution.symbol
        provenance = (
            f"The {'call' if use.kind == 'call' else 'import'} was introduced by {caller_ref}"
            if not inherited
            else f"The {'call' if use.kind == 'call' else 'import'} comes from the common ancestor and "
                 f"{caller_ref} kept it while changing what it binds to"
        )
        where = f"{use.path} line {use.lineno}"
        if rule == "R2":
            message = (
                f"Incompatible signature at {where}: {use.source} supplies {use.shape.describe()}, "
                f"but {change_ref} changed {change['file']} to {change['after']}. "
                f"{provenance}; Git reported no textual conflicts."
            )
        elif rule == "R1":
            message = (
                f"Removed function at {where}: {use.source} calls {symbol}, "
                f"which {change_ref} {_removal_phrase(change)}. "
                f"{provenance}; Git reported no textual conflicts."
            )
        else:
            target = merged.resolution
            needed = f"module {target.module}" if target.status == MISSING_MODULE else f"{target.name} from {target.module}"
            message = (
                f"Broken local import at {where}: {use.text} needs {needed}, "
                f"which {change_ref} {_removal_phrase(change)}. "
                f"{provenance}; Git reported no textual conflicts."
            )
        return {
            "rule_id": rule,
            "rule": RULES[rule],
            "title": RULE_TITLES[rule],
            "file": use.path,
            "line": use.lineno,
            "scope": use.scope,
            "use": use.source or use.text,
            "module": use.module,
            "symbol": symbol,
            "reason": merged.reason,
            "provenance": {
                "use": {"branch": side, "ref": caller_ref, "origin": origin,
                        "file": caller_use.path, "line": caller_use.lineno},
                "change": {"branch": other, "ref": change_ref, **change},
            },
            "message": message,
        }

    def _unsupported(self, use: Use, result: Check) -> dict:
        res = result.resolution
        names = set(use.chain) if use.kind == "call" else {use.name or "", (use.target or "").rpartition(".")[2]}
        relevant = bool(names & self.changed_names)
        if res.module and res.name:
            relevant = relevant or any((res.module, res.name) in self.deltas[s].functions for s in SIDES)
        return {
            "file": use.path,
            "line": use.lineno,
            "use": use.source or use.text,
            "reason": result.unsupported,
            "relevant": relevant,
        }

    def _dynamic_imports(self) -> list[dict]:
        removed = set(self.deltas["a"].removed_modules) | set(self.deltas["b"].removed_modules)
        found = []
        for index in self.states["merged"].indexes.values():
            for dyn in index.dynamic_imports:
                if dyn.target is None:
                    relevant = bool(removed)
                    reason = "dynamic import with a computed module name"
                else:
                    relevant = any(dyn.target == m or dyn.target.startswith(m + ".") for m in removed)
                    reason = f"dynamic import of {dyn.target!r}"
                found.append({"file": index.path, "line": dyn.lineno, "use": "import_module/__import__",
                              "reason": reason, "relevant": relevant})
        return found


def _function_change(change: d.FunctionChange) -> dict:
    return {
        "kind": change.kind,
        "symbol": f"{change.module}.{change.name}",
        "file": change.path,
        "line": change.after.lineno if change.after else None,
        "before": change.before.render(),
        "after": change.after.render() if change.after else None,
    }


def _module_change(delta: d.BranchDelta, module: str) -> dict:
    for removed, path in delta.removed_modules.items():
        if module == removed or module.startswith(removed + "."):
            return {"kind": d.MODULE_REMOVED, "symbol": removed, "file": path, "line": None,
                    "before": path, "after": None}
    raise KeyError(module)


def _removal_phrase(change: dict) -> str:
    if change["kind"] == d.MODULE_REMOVED:
        return f"deleted ({change['file']})"
    if change["kind"] == d.REMOVED:
        return f"removed from {change['file']}"
    if change["kind"] == "rebound":
        return "rebound to something else"
    return f"changed in {change['file']}"


def analyse(base: Snapshot, a: Snapshot, b: Snapshot, merged: Snapshot,
            refs: dict[str, str] | None = None) -> Result:
    return Analysis(base, a, b, merged, refs).run()
