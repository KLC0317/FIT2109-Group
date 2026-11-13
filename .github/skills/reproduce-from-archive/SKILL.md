---
name: reproduce-from-archive
description: Reproduce this project from a clean git archive by following only README.md, and report every place where a newcomer would get stuck or see different output. Use before a release or after README, setup or script changes.
---

# Reproduce from a clean archive

Act as a marker who knows nothing except the repository's files.

1. Export the committed state to an empty directory under `out/`:
   `git archive --format=tar HEAD | tar -x -C <empty dir>`. Work only there.
   Never modify the original repository.
2. Follow README.md literally, in order, in a fresh shell. Do not use
   knowledge of the code to fill gaps. If a step is ambiguous, record that
   instead of guessing.
3. For every command record: the command, exit status, wall time, and
   whether the output matches what the README says to expect.
4. Report each mismatch with evidence: the README line, what you ran,
   what you saw. Classify it as blocking (cannot continue), misleading
   (continues, but the README is wrong) or missing (the README is silent).
5. Counterexample check: repeat setup in a shell where `python3` is not
   Python 3.12, or where `.venv` is not activated. The project must either
   work or fail with a message that says what to do.
6. Do not fix anything. Propose README edits as a list; a team member
   decides and makes them.
