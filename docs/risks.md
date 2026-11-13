# Risk and issue register

> Demonstration repository: entries are simulated to show the format.

| ID | Risk / issue | Raised | Owner | Response | Status |
|---|---|---|---|---|---|
| K1 | Mutating the user's repository (the most damaging failure) | wk 11 | M1 | merge only in a temporary repository via alternates; hooks and user config off; byte-for-byte preservation tests after every kind of run | closed: tests pass for SAFE, BREAK, CONFLICT, INCONCLUSIVE and ERROR runs |
| K2 | AI-drafted cleanup deleting outside the work directory | wk 12 | M2 | glob-based draft rejected; removal only of a real `run.??????` directory inside the base; M3's adversarial path tests | closed |
| K3 | Confusing identically named or shadowed symbols | wk 11 | M2 | module-qualified resolution, Python scoping rules, abstain on ambiguity; 26 scoping tests | closed |
| K4 | Scope creep into wider Python semantics | wk 11 | all | classes, rename detection, CI and other languages deferred (tutor discussion, 29 Oct) | accepted |
| K5 | Core build slipping past week 12 | wk 11 | all | cut order agreed: 100-file fixture, cold timing, then holdout size before freezing | closed: not needed |
| K6 | Labels sharing the detector's mistakes | wk 11 | M3 | labels and smoke assertions human-only; M1 reviews labels on base, A, B and the merge before M2 sees holdout results | closed: 3 holdout fixtures fixed in review |
| K7 | An internal error reported with a result exit code | wk 13 | M1 | found by preservation tests (exit 1 on a non-Python last file); every deliberate exit via `leave()`, exit code from the report | closed (MR !12) |
| K8 | Windows-only path forms bypassing checks | wk 13 | M1 | `shell_path` before the working-tree guard; `holdout.lock` format normalised | closed |
| K9 | Latency target (5 s median, 100 files) | wk 13 | M1 | profiling-driven export changes, 6.65 s to 5.29 s on the laptop; 12 Nov session 3.79 s (range 3.61-3.92 s) for the same code | open: session-to-session variation exceeds the margin; the unit-server run decides |
| K10 | No CI runner available when the pipeline was added | wk 14 | M1 | validated `.gitlab-ci.yml` with CI lint; ran `scripts/test.sh` locally on every merge request until the `fit2109` runner tag was confirmed | closed (MR !25) |
| K11 | Mixed CRLF/LF line endings from Windows editors | wk 14 | M1 | `.gitattributes` forces LF in the repository; files renormalised | closed |
