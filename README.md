# Silent Merge Break Detector

Checks two Python branches **before** they are merged for incompatibilities
that Git merges cleanly but that break at runtime:

| Rule | What it catches |
|---|---|
| R1 removed function | one branch removes or renames a function the other branch calls |
| R2 incompatible signature | one branch changes a function's parameters; the other branch's call no longer binds |
| R3 broken local import | one branch deletes or moves a module or function the other branch imports |

Each finding is backed by evidence from all four code states: the common
ancestor, both branches and the clean trial merge. It says which branch
introduced the use and which branch made the change.

FIT2109 group project, team MY-T06-03 ("You're Absolutely Right!").

## Quick start

Requirements: Bash, Git 2.38 or newer, Python 3.12. No Docker, no network
access after setup, no fixed ports and no privileged operations. Everything
generated stays under `out/`.

```bash
bash scripts/setup.sh      # .venv with pinned pytest and pylint
bash scripts/demo.sh       # baseline versus checker on the MiniApp scenario
bash scripts/test.sh       # bash -n, unit tests and Git integration tests
```

`setup.sh` ends with:

```
bash:   5.x
git:    2.4x
python: Python 3.12.x (.../.venv/bin/python)
pytest: pytest 8.2.0
pylint: pylint 4.1.2
setup complete
```

`demo.sh` rebuilds the scenario repositories and ends with:

```
== Summary ==
pair                                         expected  baseline           checker
r1-remove-function + r1-old-caller           break     merge looks fine   SILENT BREAK (exit 1)
r2-api-change + r2-new-caller                break     merge looks fine   SILENT BREAK (exit 1)
r3-delete-module + r3-old-import             break     merge looks fine   SILENT BREAK (exit 1)
safe-optional-email + safe-badge             safe      merge looks fine   SAFE (exit 0)
conflict-team-field + conflict-email-field   conflict  conflict reported  TEXT CONFLICT (exit 2)
```

`test.sh` ends with `269 passed, 2 skipped`. One test needs POSIX signals
and one needs permission to create symlinks; on Linux both run.

## Using the checker

```bash
bash scripts/silent-merge-check.sh --repo <repo> [--source-root <dir>] <ref-a> <ref-b>
```

| Option | Meaning |
|---|---|
| `--repo` | the Git repository to check (it is only read) |
| `--source-root` | directory that holds the Python packages, relative to the repository (default `.`) |
| `--out-dir` | where reports, logs and the temporary merge go (default `out/`) |
| `--json`, `--log` | explicit report and log paths |
| `--quiet` | no diagnostics on stdout; the exit code and report still say everything |
| `--keep-temp` | keep the temporary merge directory for inspection |

Exit codes: **0** SAFE, **1** SILENT BREAK, **2** TEXT CONFLICT, **3**
INCONCLUSIVE/ERROR. SAFE means no supported incompatibility was found within
completed analysis; it is not proof that the program is correct. Unresolved
bindings relevant to the branches' changes, and syntax errors, prevent a
SAFE result.

Example on the Appendix C1 pair:

```
$ bash scripts/silent-merge-check.sh --repo out/scenarios/miniapp r2-api-change r2-new-caller
silent-merge-check: SILENT BREAK
  A     r2-api-change  82b719e...
  B     r2-new-caller  6c43cae...
  base  ...

[R2] Incompatible signature  profileapp/badge.py:7
  use:     get_user(user_id)  (introduced by r2-new-caller)
  reason:  missing 1 required positional argument: 'include_email'
  change:  r2-api-change signature profileapp/users.py:10
           get_user(user_id)  ->  get_user(user_id, include_email)
  Incompatible signature at profileapp/badge.py line 7: get_user(user_id) supplies 1 positional
  argument, but r2-api-change changed profileapp/users.py to get_user(user_id, include_email).
  The call was introduced by r2-new-caller; Git reported no textual conflicts.
```

The JSON report (`out/reports/<run>.json`) holds the commit IDs, rule ID,
module and symbol, merged file and line, branch provenance, reason,
exclusions, unsupported uses and analysis coverage. The JSON-lines log
(`out/logs/<run>.jsonl`) records every stage with its duration.

### Repository safety

The checker never writes to the repository it checks and never runs its
code. Refs are resolved to commit IDs, and uncommitted changes are reported
as excluded. The merge happens in a temporary repository under
`<out-dir>/tmp`, which reads the user's objects through `alternates`, with
hooks and the user's global/system Git configuration switched off.
Submodules, custom merge drivers and criss-cross histories stop the run as
INCONCLUSIVE. `--out-dir` may not point inside the checked working tree
unless that path is ignored there. Cleanup only removes the `run.XXXXXX`
directory it created. `tests/integration/test_preservation.py` checks every
file of the working tree and `.git`, byte for byte, before and after each
kind of run.

## Other scripts

| Script | Purpose |
|---|---|
| `scripts/reproduce.sh` | Appendix C1: builds the two-developer scenario and writes `out/reproduce/evidence_summary.json` |
| `scripts/make-fixtures.sh` | rebuilds all 30 labelled branch pairs, `miniapp` and (`--latency`) the 100-file fixture under `out/scenarios/` |
| `scripts/freeze-holdout.sh` | writes or checks `scenario/holdout.lock` |
| `scripts/evaluate.sh` | baseline, Pylint and the checker on the labelled pairs plus 14 error inputs (`out/eval/`) |
| `scripts/profile.sh` | five timed runs per case, per-stage durations (`out/eval/timing/`) |
| `scripts/check-archive.sh` | setup (with `--setup`), demo and full tests from a fresh `git archive` of HEAD |

## Layout

```
src/smc/          checker analyser: snapshot, symbols, uses, resolve, signature,
                  delta, rules, report, logjson (standard library only)
src/smc_eval/     evaluation harness, error inputs, timing harness
scripts/          Bash entry points; scripts/lib holds shared helpers
tests/unit/       binder (checked against CPython), symbols, scoping, resolution,
                  four-state rules, AI-suggested adversarial cases
tests/integration Git integration: error inputs, preservation, fixtures, helper
scenario/         MiniApp, 30 labelled branch-pair fixtures, holdout lock
docs/             scenario, design, evaluation, AI use, meetings, risks
```

## Continuous integration

`.gitlab-ci.yml` runs `scripts/setup.sh` and `scripts/test.sh` in a
`python:3.12` container on the unit's shared runner (tag `fit2109`) for every
push and merge request. The pytest results are kept as a JUnit artifact, so
a failing test shows up in the merge request. A merge request is only
merged when its pipeline is green.

## Documentation

* [docs/scenario.md](docs/scenario.md): user, pain point, MiniApp, fixture catalogue, label review
* [docs/design.md](docs/design.md): architecture, evidence conditions, rules, binding support, safety
* [docs/evaluation.md](docs/evaluation.md): method and results against the proposal's targets
* [docs/ai-use.md](docs/ai-use.md): AI delegation plan and evidence log
* [docs/meetings.md](docs/meetings.md), [docs/risks.md](docs/risks.md): coordination records

## Team

| Member | Primary responsibility |
|---|---|
| M1 | Bash and Git orchestration, repository-preservation tests, profiling |
| M2 | AST analysis and detection rules |
| M3 | Scenario, fixtures, tests, evaluation harness, reproducibility docs |

Work goes on task branches, each merged through a small merge request that
another member reviews; `main` stays runnable.
