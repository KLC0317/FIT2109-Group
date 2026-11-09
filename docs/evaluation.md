# Evaluation

Reproduce with `bash scripts/evaluate.sh` (all 30 pairs plus 14 error
inputs; results in `out/eval/all/`) and `bash scripts/profile.sh`
(latency; results in `out/eval/timing/`). The numbers below come from those
scripts. They were run on a Windows 11 laptop with Git Bash 5.3, Git 2.54
and Python 3.12.4.

## Method

For every labelled pair, on the same frozen branches:

| Approach | What runs | Counts as catching a break when |
|---|---|---|
| Baseline (current workflow) | `git merge --no-commit --no-ff`, then the fixture's existing unittest suite on the merged tree | the merge conflicts or the tests fail |
| Existing-tool reference | `pylint --errors-only` on the clean merged tree | a message points at the file containing the broken use |
| Checker | `scripts/silent-merge-check.sh` | status SILENT BREAK |

Ground truth is the case's smoke assertion, run on the caller branch and
on the trial merge. Neither the baseline nor the checker sees it. Labels
were written by M3 and reviewed by M1 before M2 saw any holdout result.
The holdout (18 pairs) was frozen in `scenario/holdout.lock` before any
checker run on it, and the harness verifies the lock before every run.
INCONCLUSIVE counts as a miss on a labelled break.

In half of the break fixtures the existing tests exercise the affected
caller, so the baseline is not built to fail. Three safe and three break
fixtures also contain a defect already present on the base commit
(`scenario/shared/legacy.py`).

## Results against the proposal's targets

| Target (proposal Section 5) | Result | |
|---|---|---|
| At least 5/6 holdout breaks detected | 6/6 | met |
| Zero false alarms among the 8 safe holdout cases | 0/8 | met |
| All 4 holdout text conflicts identified | 4/4 | met |
| Median under 5 s on the 100-file fixture | 5.29 s on the laptop; unit server pending | see Latency |

### Holdout (18 pairs)

| Silent breaks caught before merge | Baseline | Pylint --errors-only | Checker |
|---|---|---|---|
| 6 | 3 | 6 | 6 |

| Checker measure | Value |
|---|---|
| Recall TP/(TP+FN) | 100% (6/6) |
| Precision TP/(TP+FP) | 100% (6/6) |
| Safe-case false-positive rate | 0% (0/8) |
| Text conflicts identified | 4/4 |
| INCONCLUSIVE | 0 |
| Determinate coverage | 100% |
| Strict accuracy | 100% (18/18) |
| Branch attribution correct (rule, file, caller branch) | 6/6 |

| Label \ checker | SILENT_BREAK | SAFE | TEXT_CONFLICT | INCONCLUSIVE | ERROR |
|---|---|---|---|---|---|
| break | 6 | 0 | 0 | 0 | 0 |
| safe | 0 | 8 | 0 | 0 | 0 |
| conflict | 0 | 0 | 4 | 0 | 0 |

### Development set (12 pairs)

Breaks caught: baseline 3/6, Pylint 6/6, checker 6/6. The checker scored
100% recall and precision, 0/4 false alarms, 2/2 conflicts and 6/6
attributions. The development set was used while building the rules; only
the holdout numbers are evidence of generalisation.

### Error and unsupported inputs (14)

All 14 end with exit 3 and the expected status and reason, and none is
reported SAFE:

| Status | Inputs |
|---|---|
| ERROR | unknown ref, not a repository, source root escaping the repository, source root missing from every branch, no common ancestor |
| INCONCLUSIVE | criss-cross history, submodule, custom merge driver, syntax error, wildcard import, dynamic import of a deleted module, `*args` call, decorated changed function, re-export |

## What the comparison shows

**Baseline.** The current workflow caught exactly the breaks whose tests
happen to exercise the new caller: 6/12 overall, 3/6 on the holdout. On
every other break, Git merged cleanly and the existing tests passed.

**Pylint** flagged every break as well. As the proposal anticipated, a
general linter on a trial merge is a strong alternative. The differences
are in what a reviewer has to do with its output:

| Base-defect fixture | Label | Pylint messages | Checker findings |
|---|---|---|---|
| c03 | break | 2 | 1 |
| c07 | break | 2 | 1 |
| c12 | break | 2 | 1 |
| c19 | safe | 1 | 0 |
| c20 | safe | 1 | 0 |
| c21 | safe | 1 | 0 |

* **Existing defects.** Pylint reports the pre-existing
  `legacy.py: unexpected-keyword-arg` in all six cases, so 3 of 8 safe
  holdout pairs would have been held back. The checker lists that defect
  under `excluded` ("already incompatible at the common ancestor") and
  reports SAFE.
* **Provenance.** Pylint's message says what is wrong in the merged file.
  The checker's finding also names the branch that introduced the use, the
  branch that changed the definition, and the before/after signature.
* **Abstention.** On the 14 error inputs the checker refuses to say SAFE.
  A linter reports nothing for code it cannot resolve.
* **Where Pylint does better.** It covers far more than three rules
  (methods, attributes, undefined variables anywhere). It also needs no
  branch information, and its R1-style messages (`no-member`) catch things
  like methods that the checker leaves out of scope. With 12 + 12 + 6
  controlled cases, both tools are at ceiling on recall, so the cases
  cannot rank them on detection, only on noise.

## Latency

Five runs per case; run 1 is the first run after the fixtures were rebuilt.

| Case | First (ms) | Median (ms) | Max (ms) | Dominant stage |
|---|---|---|---|---|
| latency100 (100 files, 1 R2 break) | 5570 | 5289 | 6362 | export (1712 ms) |
| c05 (MiniApp R2 break) | 3788 | 3650 | 3788 | export (880 ms) |
| c13 (MiniApp safe) | 3607 | 3608 | 3692 | export (849 ms) |
| c25 (MiniApp conflict) | 3064 | 3062 | 3117 | validate (543 ms) |

The first measurement put latency100 at a 6.65 s median, with export
dominating every clean-merge case. Most of that time was process start-up:
one `git archive`, `tar` and `ls-tree` per state, a forked `date` per log
line, and a `cygpath` per path. Exporting only `*.py`, streaming all four
states through one `tar`, building file lists with `globstar` and using
bash builtins for timestamps brought the median to 5.29 s (c05: 5.48 s to
3.65 s). The analyser itself takes about 0.1 s of analysis plus 0.5 s of
parsing on 400 files.

The proposal's target is defined on the unit server. Process creation under
Git Bash on Windows is much slower than on Linux, so the laptop figure is an
upper bound. Re-measuring with `bash scripts/profile.sh` on the unit server
is part of the week-14 clean-archive check (docs/meetings.md).

## Threats to validity

* The fixtures are small and written by the team around the three rules.
  Real repositories will contain code outside the binding support, which
  shows up as INCONCLUSIVE rather than SAFE.
* Holdout cases were written after the rules were designed. Freezing them
  before any checker run prevents tuning to them, but not shared blind
  spots between the fixture author and the rule author.
* Smoke assertions exercise one path each. A break they do not exercise
  would be mislabelled safe; every label was confirmed by M1 on base, A, B
  and the trial merge.
