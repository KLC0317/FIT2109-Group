# Design

## Pipeline

```
silent-merge-check.sh (Bash)                          python -m smc (standard library)
-----------------------------------------------       ----------------------------------------
validate   repo, refs -> commit IDs, source root       parse    snapshot.py   ast per file, syntax errors kept
           uncommitted changes noted as excluded      index    symbols.py    module-level bindings, signatures
merge_base git merge-base --all (exactly one)          uses     uses.py       calls/imports with lexical scope
preflight  submodules, custom merge drivers           resolve  resolve.py    use -> module-qualified target
workdir    out/tmp/run.XXXXXX, objects via            delta    delta.py      base -> A, base -> B changes
           alternates, hooks/config off               rules    rules.py      R1-R3 + four-state evidence
merge      git merge --no-commit --no-ff A <- B        report   report.py     JSON report, diagnostics
           unmerged entries -> TEXT CONFLICT                   logjson.py    stage timings into the run log
export     *.py of base, A, B, merged tree
           + NUL-delimited file lists, manifest
analyse    run analyser; exit code from the report
```

Bash owns everything that touches Git and the filesystem; Python never runs
Git or the project's code. The manifest (`manifest.json` in the work
directory) is the only interface between them.

## Evidence conditions

A finding needs evidence from all four states:

1. **Compatible on the caller branch.** The use resolves there to a
   tracked function (R1, R2) or to an existing module or explicitly defined
   function (R3), and the call binds.
2. **The other branch changed it.** Relative to the common ancestor, the
   other branch removed or changed the function's signature or decorators,
   deleted the module, or rebound the name in the caller's module.
3. **Still present and broken in the merged tree.** The merged tree
   contains the use, and there the binding is absent or incompatible.
4. **Not already broken.** The same use is not already incompatible at the
   common ancestor (an existing defect) or on the other branch alone.

The check runs with A as the caller branch and again with B. Uses are
matched across states by `(module, scope, callee text, ordinal)`, so line
shifts do not matter. A use the caller branch inherited from the ancestor
and did not edit can still be a finding when what it binds to changed.
Existing defects are listed under `excluded`, not reported. Unbound names
that are unbound everywhere (builtins, typos) are ignored.

Result: findings give **SILENT BREAK**. Otherwise, syntax errors in any
state or relevant unsupported code give **INCONCLUSIVE**. Otherwise the
result is **SAFE**. Unsupported code is "relevant" when it names a symbol or
module that either branch changed.

## Rules

| Rule | Merged-tree condition | Typical cause |
|---|---|---|
| R1 removed function | `module.f(...)` or same-module `f(...)` where `f` is no longer bound | rename or removal on one branch, new call on the other |
| R2 incompatible signature | explicit arguments fail to bind to the merged signature | new required parameter, removed or renamed parameter, positional-only or keyword-only change |
| R3 broken local import | `import m` / `from m import f` where `m` is gone, or `f` is no longer bound in `m` | module moved or deleted, function moved to another module |

Calls through a `from` import whose target disappeared are reported once,
as R3 on the import, not again as R1 on each call.

The binder (`signature.bind`) follows CPython's rules for explicit
arguments: excess positional arguments, unexpected and duplicate keywords,
positional-only parameters passed by keyword (absorbed by `**kwargs` when
present), and missing required positional and keyword-only parameters. Its
messages use CPython's TypeError wording. `tests/unit/test_signature.py`
runs every case through CPython itself as the oracle.

## Binding support

Supported: module-level functions; same-module direct calls;
`import m [as alias]` with attribute calls, including `import a.b` then
`a.b.f()`; `from m import f [as alias]`; relative imports;
`from package import submodule`.

Lexical scoping follows Python. Parameters of every kind, assignments
anywhere in a function, `for`/`with`/`except` targets, local imports and
nested `def`s shadow a module-level function. Class bodies are visible only
to calls directly inside them. Comprehensions and lambdas have their own
scopes. `global` and `nonlocal` are honoured.

Reported as unsupported, with a reason: names bound more than once or
conditionally (including try/except import fallbacks), `global` rebinding of
the name, re-exports, wildcard imports, module `__getattr__`,
`importlib.import_module`/`__import__`, calls with `*args`/`**kwargs`, and
decorators other than `functools.cache`/`lru_cache`.

Out of scope: methods and inheritance, rename detection (a rename shows up
as a removal), runtime data errors, automatic fixes, multiple merge bases
and submodules.

## Repository protection

* Only committed states are analysed. `git status` runs with
  `--no-optional-locks`, so even the index's stat cache is not rewritten.
* The temporary repository reads the user's object store through
  `objects/info/alternates`; it writes nothing to the user's repository.
  Hooks are pointed at an empty directory. `GIT_CONFIG_GLOBAL` and
  `GIT_CONFIG_NOSYSTEM` keep the user's configuration, and with it any
  merge drivers, out. `core.autocrlf` is off.
* `GIT_DIR`, `GIT_WORK_TREE` and similar variables are unset on start.
* Work directories come from `mktemp -d` under the project's `out/tmp`, and
  cleanup (`scripts/lib/workdir.sh`) removes only a real `run.XXXXXX`
  directory directly inside that base.
* Paths go through NUL-delimited lists, and every expansion is quoted.
* Every deliberate exit goes through `leave()`. An exit caused by `set -e`
  becomes an ERROR report, so an internal failure can never look like
  exit 1 (SILENT BREAK). The final exit code is taken from the analyser's
  report, and a mismatch with the analyser's own exit status is an ERROR.

## Logging and profiling

Every run appends JSON lines to `out/logs/<run>.jsonl`. The orchestrator
logs `start`, one `stage` record per stage with `duration_ms`, and
`result`; the analyser adds `parse`, `analyse` and `report`.
`python -m smc_eval timing` turns repeated runs into a CSV and names the
dominant stage. That is how export was found to dominate and was then cut
down (see docs/evaluation.md).
