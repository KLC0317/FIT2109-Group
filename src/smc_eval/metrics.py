"""Measures from proposal Section 5, computed over CaseResult dictionaries."""

from __future__ import annotations

STATUSES = ("SILENT_BREAK", "SAFE", "TEXT_CONFLICT", "INCONCLUSIVE", "ERROR")
LABEL_STATUS = {"break": "SILENT_BREAK", "safe": "SAFE", "conflict": "TEXT_CONFLICT"}


def ratio(num: int, den: int) -> float | None:
    return round(num / den, 3) if den else None


def summarise(rows: list[dict]) -> dict:
    breaks = [r for r in rows if r["label"] == "break"]
    safes = [r for r in rows if r["label"] == "safe"]
    conflicts = [r for r in rows if r["label"] == "conflict"]

    # INCONCLUSIVE counts as a miss on a labelled positive.
    tp = sum(1 for r in breaks if r["checker_status"] == "SILENT_BREAK")
    fn = len(breaks) - tp
    fp = sum(1 for r in rows if r["label"] != "break" and r["checker_status"] == "SILENT_BREAK")
    fp_safe = sum(1 for r in safes if r["checker_status"] == "SILENT_BREAK")
    determinate = sum(1 for r in rows if r["checker_status"] in ("SILENT_BREAK", "SAFE", "TEXT_CONFLICT"))
    correct = sum(1 for r in rows if r["checker_status"] == LABEL_STATUS[r["label"]])

    confusion = {label: {s: 0 for s in STATUSES} for label in LABEL_STATUS}
    for r in rows:
        confusion[r["label"]][r["checker_status"]] += 1

    def caught(predicate) -> int:
        return sum(1 for r in breaks if predicate(r))

    base_defect = [r for r in rows if r["base_defect"]]
    return {
        "cases": len(rows),
        "labels": {"break": len(breaks), "safe": len(safes), "conflict": len(conflicts)},
        "labels_verified": sum(1 for r in rows if r["label_verified"]),
        "headline_breaks_caught": {
            "baseline": caught(lambda r: r["baseline_tests"] == "fail"),
            "pylint": caught(lambda r: r["pylint_hits_expected_file"]),
            "checker": tp,
            "of": len(breaks),
        },
        "baseline_breaks_caught_when_tests_cover": caught(lambda r: r["tests_cover"] and r["baseline_tests"] == "fail"),
        "baseline_breaks_with_covering_tests": sum(1 for r in breaks if r["tests_cover"]),
        "checker": {
            "tp": tp, "fn": fn, "fp": fp,
            "recall": ratio(tp, tp + fn),
            "precision": ratio(tp, tp + fp),
            "safe_false_positive_rate": ratio(fp_safe, len(safes)),
            "conflicts_identified": sum(1 for r in conflicts if r["checker_status"] == "TEXT_CONFLICT"),
            "inconclusive": sum(1 for r in rows if r["checker_status"] == "INCONCLUSIVE"),
            "determinate_coverage": ratio(determinate, len(rows)),
            "strict_accuracy": ratio(correct, len(rows)),
            "attribution_correct": sum(1 for r in breaks if r["attribution_correct"]),
        },
        "pylint": {
            "safe_cases_with_messages": sum(1 for r in safes if r["pylint_messages"]),
            "messages_total": sum(len(r["pylint_messages"]) for r in rows),
        },
        "triage_base_defect_cases": [
            {"id": r["id"], "label": r["label"], "pylint_messages": len(r["pylint_messages"]),
             "checker_findings": len(r["checker_findings"])}
            for r in base_defect
        ],
        "confusion_matrix": confusion,
    }
