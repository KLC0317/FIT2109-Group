# Project instructions for coding agents

Read by AI coding assistants used in this repository (see docs/ai-use.md).
These instructions do not grant any permission; the team member running
the assistant decides what it may do.

## What this project is

`scripts/silent-merge-check.sh` (Bash) and `src/smc/` (Python 3.12,
standard library only) check two committed Git branches of a Python
project for silent merge breaks: removed functions (R1), incompatible
signatures (R2) and broken local imports (R3). Exit codes: 0 SAFE,
1 SILENT BREAK, 2 TEXT CONFLICT, 3 INCONCLUSIVE/ERROR.

## Commands

- Setup: `bash scripts/setup.sh`
- Tests: `bash scripts/test.sh` (all must pass before a change is proposed)
- Demo: `bash scripts/demo.sh`

## Rules

- Do not edit `src/smc/rules.py`, `src/smc/signature.py`, `src/smc/resolve.py`
  or `src/smc/uses.py`: the detection rules are human-written and are not
  delegated to AI.
- Do not read, edit or summarise anything under `scenario/cases/` whose
  `case.env` says `SPLIT=holdout`, or `scenario/holdout.lock`.
- Do not change smoke assertions (`scenario/cases/*/smoke.py`), labels
  (`case.env`) or expected values in tests to make something pass.
- No new dependencies: `src/smc/` uses only the standard library;
  `requirements.txt` changes are a team decision.
- Never run Git commands that write to a repository other than a scratch
  copy, and never push.
- Write generated files under `out/` only.
- When unsure whether a result is SAFE, prefer reporting the uncertainty;
  the tool's own rule is that unresolved relevant code is INCONCLUSIVE.
