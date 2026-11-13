# Integration meetings

Two short integration meetings a week (Tuesday and Friday, about 20 minutes)
plus the week-12 tutor discussion. Actions are tracked here; merge requests
carry the detail.

> Demonstration repository: these notes are simulated to show the format.

## Week 11

**Tue 20 Oct.** All three re-ran the Appendix C2 reproduction from origin;
results matched. Agreed the input/output contract (two committed refs, a
source root; exit codes 0-3) and that labels and holdout stay human-only.
*Actions:* M1 prototypes the isolated merge; M2 proves AST extraction; M3
specifies fixtures.

**Fri 23 Oct.** Prototype merge (MR !2), AST extraction (MR !3) and fixture
spec (MR !4) merged. Proposal submitted.

## Week 12

**Tue 27 Oct.** AI activity 2 helper reviewed by M3; M1 signed off the
isolation contract (merge in a temporary repository via alternates, no
writes to the user's repository). *Decision:* uncommitted changes are noted
as excluded rather than refused.

**Thu 29 Oct: tutor feasibility discussion.** Showed the CLI on the C1
pair. Tutor questions: "what does SAFE promise?" and "how do you avoid
reporting a defect that was already there?" *Scope changes recorded:*
(1) SAFE wording fixed as "no supported incompatibility within completed
analysis"; (2) existing defects listed under `excluded` instead of being
dropped silently; (3) no rename detection this semester (renames appear as
R1 removals, documented). Classes, CI integration and other languages
stay out until the core tests pass.

**Fri 30 Oct.** Detection rules (MR !6), orchestration (MR !7) and dev
fixtures (MR !8) merged; all 12 development pairs correct on a trial
integration branch first. Demo (MR !9) ready for the checkpoint.

## Week 13

**Tue 3 Nov.** Holdout label review by M1 found three fixture mistakes
(c18, c27, c29); fixed, then the holdout was frozen (`scenario/holdout.lock`)
before any checker run on it. The new preservation tests are expected to
fail until the export fix lands.

**Fri 6 Nov.** Preservation tests exposed an exit-1-on-internal-failure
bug (MR !12, fixed: exit code now comes from the report). Evaluation
harness merged; holdout run: 6/6 breaks, 0/8 false alarms, 4/4 conflicts.
Timing harness showed export dominating; optimisation brought the
100-file median from 6.65 s to 5.29 s on the laptop. *Action (M1):*
re-measure on the unit server during the clean-archive check.

## Week 14

**Tue 10 Nov.** Design, evaluation and AI-use documents merged. Planned
versus actual AI delegation compared (docs/ai-use.md). *Actions:* M3 adds
the clean-archive check; all three rehearse the video (each speaks on
camera; at most 5 minutes).

**Thu 12 Nov.** Clean-archive check run (scripts/check-archive.sh): setup,
demo and full test suite from `git archive HEAD` in an empty directory.
Release tagged.

**Thu 12 Nov (evening).** Merged the week-14 follow-ups that had waited
for review: the Week 9 profiling method (ranges, same-result check,
`cProfile`; MR !24), the GitLab CI pipeline once the `fit2109` runner tag
was confirmed (MR !25), and the analyser log on Python's `logging` module
with `--debug` evidence (MR !26). Full suite green on `main` (274 passed).
*Decision:* add an Evaluate-stage AI activity (clean-archive reproduction,
M2 owner, M1 checker) with `AGENTS.md` written first. It is recorded as
unplanned in docs/ai-use.md.

**Fri 13 Nov.** Activity 4 merged (MR !27): five README fixes accepted,
two suggestions rejected. Line endings normalised. Final tag `v1.1.0` for
submission; the project archive is built with
`git archive --format=zip -o project.zip v1.1.0`.
