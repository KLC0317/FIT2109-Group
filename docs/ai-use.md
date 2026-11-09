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

