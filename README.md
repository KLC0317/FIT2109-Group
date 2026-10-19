# Silent Merge Break Detector

Checks two Python branches for incompatibilities that Git merges cleanly but
that break at runtime: a removed function, an incompatible call signature or a
broken local import.

FIT2109 group project, team MY-T06-03 ("You're Absolutely Right!").

Work in progress. Layout follows the unit specification:

```
src/        Python analyser (standard library only)
tests/      pytest unit and Git integration tests
scenario/   MiniApp sample application and labelled branch-pair fixtures
scripts/    Bash entry points (checker, setup, demo, tests, fixtures)
docs/       scenario, design, evaluation and AI-use records
```
