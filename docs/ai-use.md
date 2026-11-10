# AI use

This file records how AI tools are used in the project, as planned in the
proposal (Appendix A), and the evidence for each use. Proposal drafting
(ChatGPT, for clarity, grammar and formatting) is acknowledged in the
proposal itself and is not one of the three activities below.

> **Demonstration repository.** The log rows below show the evidence
> standard filled in for this simulated project. They are illustrative
> examples, not records of real assistant sessions. In the team's real
> repository, each row must be the actual prompt, output and check.

## Plan

Each member drafted and owns one activity and checks another member's. The
three activities cover the Discover, Build and Verify stages. Tools are
University-supported assistants (Gemini or Copilot).

| Activity | Stage | Owner | Independent checker | Allowed | Not allowed |
|---|---|---|---|---|---|
| 1. Study existing tools | Discover, weeks 11-12 | M1 | M2 | compare existing approaches against the three reproduced failures; challenge scope and baseline | inventing team observations, choosing the problem, deciding feasibility |
| 2. Bounded Bash error-handling helper | Build, week 12 | M2 | M3 (M1 signs off isolation) | draft one helper: ref validation, safe filenames, cleanup of the project-local work directory | the merge engine, isolation design, exit-code meaning, touching the live repository |
| 3. Adversarial test suggestions | Verify, weeks 12-13 | M3 | M1 | propose safe counterexamples and boundary cases for signatures, aliases, shadowing | setting ground truth, labelling fixtures, seeing holdout cases, fabricating results |

**Never delegated:** the three detection rules (the core logic), fixture
labels and smoke assertions, holdout cases, and evaluation results. Errors
there would be hard to detect and would undermine the evidence the project
rests on.

**Evidence standard for every entry:** date, stage/task, owner, checker,
tool, exact instruction, concise output, verification evidence, decision
(Accepted / Modified / Rejected) and residual risk. Original and edited
outputs are kept distinguishable: the AI draft is quoted or summarised
under "Output", and the team's changes under "Decision".

## Activity 1 (Discover): study existing tools

| Field | Entry |
|---|---|
| Date | 2026-10-21 |
| Stage / task | Discover: compare existing approaches before the tutor discussion |
| Owner / checker | M1 / M2 |
| Tool | Gemini (University account) |
| Instruction | "We reproduced three failures where two Python branches both pass their tests and Git merges cleanly, but the merged program crashes: a removed function, a new required argument, a deleted module. Compare these approaches for catching them before merge: Git-only review, targeted tests, running a linter on a trial merge, GitLab merged results pipelines. For each give benefits, limitations, and the documentation source for every claim. List questions a narrow pre-merge checker must answer to be worth building." |
| Output (summary) | A four-row comparison table and seven questions. Claims: (a) Git only reports textual conflicts; (b) tests catch these only when they exercise the new caller; (c) Pylint error checks would flag all three on a merged tree; (d) merged results pipelines test the merge commit "on all GitLab tiers"; (e) a linter cannot tell which branch caused a message. Questions included "how will existing defects be separated from new ones?" and "what happens when bindings cannot be resolved?" |
| Verification | M2 opened every cited page. (a) matched git-merge docs. (b) matched our C2 runs, where the existing tests passed on all three merged trees. (c) was run, not trusted: pylint 4.1.2 `--errors-only` on the three C2 merged trees reported E1101, E1120 and E0401 (recorded in proposal Appendix C2). (d) contradicted the GitLab docs, which require Premium or Ultimate. (e) is true of the default output. |
| Decision | **Modified.** Kept the table, corrected (d) to "Premium/Ultimate only", and added the explicit statement that sufficiently targeted tests and linters can catch these failures. Pylint became the existing-tool reference. Two of the seven questions (existing defects, unresolved bindings) became design requirements: exclusions and INCONCLUSIVE. Scope and the observed failures were unchanged. |
| Residual risk | Our controlled cases may not represent all projects; the evaluation reports this. |

## Activity 2 (Build): bounded Bash error-handling helper

| Field | Entry |
|---|---|
| Date | 2026-10-26 |
| Stage / task | Build: helper for ref validation, safe filenames and work-directory cleanup (`scripts/lib/workdir.sh`) |
| Owner / checker | M2 / M3; M1 signed off the isolation contract |
| Tool | GitHub Copilot Chat (University licence) |
| Instruction | "Write Bash functions (bash 5, set -euo pipefail) for a tool that must never modify the user's repository: 1) resolve a user-supplied ref to a full commit ID safely; 2) normalise a repository-relative source root and reject anything that could escape the repository; 3) create a private temporary directory under a given project-local base; 4) remove that directory and nothing else, even if variables are empty or wrong. Explain the assumptions and every error path." |
| Output (original) | Four functions with comments. `resolve_ref` used `git rev-parse "$2"` with no `--verify` or `--end-of-options`. `check_root` used a regex rejecting `..`, but with an unquoted expansion. `make_tmp` used `mktemp -d "$base/smc.XXXX"`. `cleanup` ran `rm -rf "$TMP_BASE"/smc.*`, a glob over the whole base, guarded only by `[[ -n $TMP_BASE ]]`. |
| Verification | M3 reviewed every filesystem and Git mutation, ran `bash -n`, and tested with spaces in paths, refs that look like options (`--all`, `-x`), whitespace in refs, unknown refs, `..`, absolute paths and drive letters, a symlinked work directory, and removal of the base itself or a directory outside it (`tests/integration/test_workdir.py`: 27 passed, 1 skipped where symlinks are not permitted). M3 compared the user's HEAD, index and every file before and after (`tests/integration/test_preservation.py`). |
| Decision | **Modified.** M2's edits (diff in commit "Add ref, source-root and work-directory helpers"): `--verify --quiet --end-of-options "$ref^{commit}"`, plus refusal of refs starting with `-` or containing whitespace; root normalisation rewritten component by component; template `run.XXXXXX` with `chmod 700`; cleanup rewritten to remove one named directory only after checking it is a real (non-symlink) `run.??????` directory whose physical parent is the expected base. The glob-based `rm -rf` was rejected outright. A test later found a source-root bug in the team's own `tr` call; it was fixed before merge. |
| Residual risk | Signal timing: SIGTERM cleanup is tested on POSIX only, and a signal between `mktemp` and recording the path could leave an empty `run.*` directory under `out/tmp`, never anything outside it. |

## Activity 3 (Verify): adversarial test suggestions

| Field | Entry |
|---|---|
| Date | 2026-11-04 to 2026-11-05 |
| Stage / task | Verify: boundary and counterexample cases after the rule contract was fixed |
| Owner / checker | M3 / M1 |
| Tool | Gemini (University account) |
| Instruction | "Here is the contract for a checker that compares a common ancestor, two branches and their merge [rules R1-R3, supported bindings, unsupported list pasted from docs/design.md]. Propose 15 test cases that are likely to expose false positives or false negatives: safe counterexamples and boundary cases for function signatures, import aliases and variable shadowing. For each give the branch edits, the expected checker outcome, the Python feature involved and why it stresses a rule." No fixture, label or holdout case was included. |
| Output (summary) | 15 suggestions, S01 to S15 (table below). |
| Verification | M1 ran every suggestion with CPython on base, A, B and the merged code before any expectation was written down, and compared the AI's expected outcome with the behaviour actually observed. |
| Decision | 9 accepted, 2 modified, 4 rejected; accepted and modified cases are in `tests/unit/test_adversarial.py`. |
| Residual risk | Suggestions may share the authors' blind spots; they target the documented contract, so gaps in the contract itself are not exercised. |

| ID | Suggestion | AI expected | Observed with CPython / checker | Decision |
|---|---|---|---|---|
| S01 | call through `functools.partial(get_user, 1)` | break detected | merged code fails, but indirect calls are outside the binding support | Rejected: out of scope (documented limitation) |
| S02 | `get_user(1, user_id=2)` where `user_id` is positional-only and `**options` exists | safe | binds in CPython; checker SAFE | Accepted |
| S03 | default added to a middle parameter, caller passes it by keyword | safe | binds; checker SAFE | Accepted |
| S04 | `lookup = u.get_user` then `lookup(1)` after a signature change | break detected | merged code fails; assignment bindings are not tracked, so no finding | Modified: kept as a limitation test asserting "not tracked" |
| S05 | caller imports two different `get_user` | INCONCLUSIVE (ambiguous) | ambiguous binding; checker INCONCLUSIVE | Accepted |
| S06 | call from a function nested in a method | break detected | fails after merge; checker R2 with scope `Page.render.inner` | Accepted |
| S07 | `try: from app.users import get_user` / `except ImportError: get_user = None` | INCONCLUSIVE | conditional binding; INCONCLUSIVE | Accepted |
| S08 | removing a default "is safe for positional callers" | safe | caller omitting the argument raises TypeError after merge; checker R2 | Modified: AI's expectation was wrong; corrected to a break |
| S09 | lambda default argument capturing the function | break detected | the call goes through a parameter, which is shadowed and untracked | Rejected: out of scope |
| S10 | keyword-only parameter "can be passed positionally" | safe | TypeError already on the caller branch, so not a merge break | Rejected: incorrect premise |
| S11 | method with the same name as the changed function | no finding | SAFE | Accepted |
| S12 | `from . import users` then `users.get_user()` | break detected | R2 | Accepted |
| S13 | `del get_user` after importing it | unclear | unsupported (`del`); INCONCLUSIVE | Accepted |
| S14 | duplicate of S03 with different names | safe | (not run) | Rejected: duplicate |
| S15 | three binder boundaries: `*args` before keyword-only, keyword-only only, positional-only with default | safe | all bind in CPython; SAFE | Accepted |

## Planned versus actual delegation

| Activity | Planned | Actual | Difference |
|---|---|---|---|
| 1 | Gemini or Copilot; comparison table checked by M2 | Gemini; one material claim (merged results pipelines tier) was wrong and corrected | none in scope; the output raised two design requirements we had not written down |
| 2 | draft a helper only; M3 checks; M1 signs off | Copilot draft heavily edited; the AI's cleanup approach rejected | the edit was larger than expected: only the function boundaries survived from the draft |
| 3 | suggestions only; labels and holdout human-only | as planned; 2 of 15 expected outcomes were wrong | confirms the control: no AI expectation reached a test without being run |

No AI tool was used for the detection rules, fixture labels, smoke
assertions, holdout cases or evaluation results.
