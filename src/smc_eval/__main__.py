"""Evaluation command line.

    python -m smc_eval evaluate --scenarios <dir> --out <dir> [--split dev|holdout|all] [--no-errors]
        writes <out>/results.json, <out>/cases.csv and <out>/summary.md
    python -m smc_eval timing --scenarios <dir> --out <dir> [--runs 5]
        writes <out>/timing.csv, <out>/timing.json and <out>/timing.md
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path

from smc_eval.harness import CASES, Harness, read_case, to_dict
from smc_eval.metrics import summarise

CSV_FIELDS = [
    "id", "split", "label", "rule", "tests_cover", "base_defect", "merge", "smoke_caller", "smoke_merged",
    "label_verified", "baseline_tests", "baseline_prediction", "pylint_prediction", "pylint_hits_expected_file",
    "checker_status", "checker_exit", "attribution_correct", "checker_seconds",
]


def evaluate(args) -> int:
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    harness = Harness(Path(args.scenarios), out / "work")
    case_dirs = sorted(p for p in CASES.iterdir() if (p / "case.env").exists())
    if args.split != "all":
        case_dirs = [p for p in case_dirs if read_case(p)["SPLIT"] == args.split]

    rows = []
    for case_dir in case_dirs:
        result = to_dict(harness.evaluate(case_dir))
        rows.append(result)
        print(f"{result['id']} {result['split']:7} {result['label']:8} baseline={result['baseline_prediction']:13} "
              f"pylint={result['pylint_prediction']:13} checker={result['checker_status']:13} "
              f"label_verified={result['label_verified']}", flush=True)

    errors = [] if args.no_errors else harness.evaluate_errors()
    for row in errors:
        print(f"{row['id']} error   exit={row['exit']} status={row['status']} ok={row['ok']}", flush=True)

    splits = sorted({r["split"] for r in rows})
    summary = {split: summarise([r for r in rows if r["split"] == split]) for split in splits}
    if len(splits) > 1:
        summary["all"] = summarise(rows)
    results = {"summary": summary, "cases": rows, "error_inputs": errors}
    (out / "results.json").write_text(json.dumps(results, indent=2) + "\n", encoding="utf-8")
    with (out / "cases.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=CSV_FIELDS, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
    (out / "summary.md").write_text(render(summary, rows, errors), encoding="utf-8")
    print(f"wrote {out / 'summary.md'}")
    ok = all(r["label_verified"] for r in rows) and all(e["ok"] for e in errors)
    return 0 if ok else 1


def pct(value) -> str:
    return "n/a" if value is None else f"{value:.0%}" if value <= 1 else str(value)


def render(summary: dict, rows: list[dict], errors: list[dict]) -> str:
    lines = ["# Evaluation results", ""]
    for split, s in summary.items():
        h, c = s["headline_breaks_caught"], s["checker"]
        lines += [
            f"## {split} ({s['cases']} cases: {s['labels']['break']} breaks, {s['labels']['safe']} safe, "
            f"{s['labels']['conflict']} conflicts; labels verified {s['labels_verified']}/{s['cases']})",
            "",
            "| Silent breaks caught before merge | Baseline (merge + tests) | Pylint --errors-only | Checker |",
            "|---|---|---|---|",
            f"| {h['of']} | {h['baseline']} | {h['pylint']} | {h['checker']} |",
            "",
            "| Checker measure | Value |",
            "|---|---|",
            f"| Recall TP/(TP+FN) | {pct(c['recall'])} ({c['tp']}/{c['tp'] + c['fn']}) |",
            f"| Precision TP/(TP+FP) | {pct(c['precision'])} ({c['tp']}/{c['tp'] + c['fp']}) |",
            f"| Safe-case false-positive rate | {pct(c['safe_false_positive_rate'])} |",
            f"| Text conflicts identified | {c['conflicts_identified']}/{s['labels']['conflict']} |",
            f"| INCONCLUSIVE | {c['inconclusive']} |",
            f"| Determinate coverage | {pct(c['determinate_coverage'])} |",
            f"| Strict accuracy | {pct(c['strict_accuracy'])} |",
            f"| Branch attribution correct | {c['attribution_correct']}/{c['tp']} |",
            f"| Pylint: safe cases with messages | {s['pylint']['safe_cases_with_messages']}/{s['labels']['safe']} |",
            "",
            "Confusion matrix (rows: label, columns: checker status)",
            "",
            "| | SILENT_BREAK | SAFE | TEXT_CONFLICT | INCONCLUSIVE | ERROR |",
            "|---|---|---|---|---|---|",
        ]
        for label, cols in s["confusion_matrix"].items():
            lines.append(f"| {label} | " + " | ".join(str(v) for v in cols.values()) + " |")
        if s["triage_base_defect_cases"]:
            lines += ["", "Findings to triage on base-defect fixtures", "",
                      "| Case | Label | Pylint messages | Checker findings |", "|---|---|---|---|"]
            lines += [f"| {t['id']} | {t['label']} | {t['pylint_messages']} | {t['checker_findings']} |"
                      for t in s["triage_base_defect_cases"]]
        lines.append("")
    lines += ["## Per case", "",
              "| Case | Split | Label | Rule | Tests cover | Base defect | Baseline | Pylint | Checker | Attribution |",
              "|---|---|---|---|---|---|---|---|---|---|"]
    for r in rows:
        attribution = {True: "correct", False: "WRONG", None: ""}[r["attribution_correct"]]
        lines.append(f"| {r['id']} | {r['split']} | {r['label']} | {r['rule']} | {'yes' if r['tests_cover'] else ''} | "
                     f"{'yes' if r['base_defect'] else ''} | {r['baseline_prediction']} ({r['baseline_tests']}) | "
                     f"{r['pylint_prediction']} ({len(r['pylint_messages'])}) | {r['checker_status']} | {attribution} |")
    if errors:
        lines += ["", "## Error and unsupported inputs", "", "| Input | Exit | Status | As expected |", "|---|---|---|---|"]
        lines += [f"| {e['id']} {e['description']} | {e['exit']} | {e['status']} | {'yes' if e['ok'] else 'NO'} |"
                  for e in errors]
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m smc_eval")
    commands = parser.add_subparsers(dest="command", required=True)
    ev = commands.add_parser("evaluate", help="run baseline, Pylint and the checker on the labelled pairs")
    ev.add_argument("--scenarios", required=True)
    ev.add_argument("--out", required=True)
    ev.add_argument("--split", choices=("dev", "holdout", "all"), default="all")
    ev.add_argument("--no-errors", action="store_true", help="skip the error/unsupported inputs")
    tm = commands.add_parser("timing", help="repeated checker runs with per-stage durations")
    tm.add_argument("--scenarios", required=True)
    tm.add_argument("--out", required=True)
    tm.add_argument("--runs", type=int, default=5)
    tm.add_argument("--cprofile", action="store_true",
                    help="afterwards, profile the analyser on latency100 with cProfile")
    args = parser.parse_args(argv)
    if args.command == "timing":
        return timing(args)
    return evaluate(args)


def timing(args) -> int:
    from smc_eval import timing as t

    out = Path(args.out)
    rows = t.time_cases(Path(args.scenarios), out, args.runs)
    summary = t.summarise(rows)
    (out / "timing.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    (out / "timing.md").write_text(t.render(summary), encoding="utf-8")
    print(t.render(summary))
    if args.cprofile:
        print("cProfile of the analyser on latency100 (cumulative time):")
        print(t.cprofile_analyser(Path(args.scenarios), out))
    return 0 if all(s["same_result"] for s in summary) else 1


if __name__ == "__main__":
    sys.exit(main())
