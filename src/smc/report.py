"""JSON report and human-readable diagnostics."""

from __future__ import annotations

import json
from pathlib import Path

from smc import __version__

EXIT_CODES = {"SAFE": 0, "SILENT_BREAK": 1, "TEXT_CONFLICT": 2, "INCONCLUSIVE": 3, "ERROR": 3}
LABELS = {
    "SAFE": "SAFE",
    "SILENT_BREAK": "SILENT BREAK",
    "TEXT_CONFLICT": "TEXT CONFLICT",
    "INCONCLUSIVE": "INCONCLUSIVE",
    "ERROR": "ERROR",
}


def build_report(manifest: dict, status: str, *, findings=(), coverage=None, excluded=(),
                 unsupported=(), conflicts=(), timings=None) -> dict:
    return {
        "tool": "silent-merge-check",
        "version": __version__,
        "status": status,
        "exit_code": EXIT_CODES[status],
        "run_id": manifest.get("run_id", ""),
        "refs": manifest.get("refs", {}),
        "commits": manifest.get("commits", {}),
        "source_root": manifest.get("source_root", "."),
        "merge": {
            "result": manifest.get("merge", {}).get("result"),
            "conflicts": list(conflicts),
        },
        "findings": list(findings),
        "excluded": list(excluded),
        "unsupported": list(unsupported),
        "coverage": coverage or {},
        "notes": manifest.get("notes", []),
        "timings_ms": timings or {},
        "meaning": _meaning(status),
    }


def _meaning(status: str) -> str:
    return {
        "SAFE": "No supported incompatibility was found within completed analysis. "
                "This is not proof of program correctness.",
        "SILENT_BREAK": "Git merges the branches cleanly, but the merged program contains a use "
                        "that one branch's change breaks.",
        "TEXT_CONFLICT": "Git cannot merge the branches automatically; resolve the textual "
                         "conflicts first, then re-run the check.",
        "INCONCLUSIVE": "Analysis could not be completed for code relevant to the branches' "
                        "changes, so SAFE cannot be reported.",
        "ERROR": "The check could not run.",
    }[status]


def write_report(report: dict, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")


def render(report: dict) -> str:
    refs, commits = report["refs"], report["commits"]
    lines = [f"silent-merge-check: {LABELS[report['status']]}"]
    for side in ("a", "b"):
        if side in refs:
            lines.append(f"  {side.upper()}     {refs[side]}  {str(commits.get(side, ''))[:12]}")
    if commits.get("base"):
        lines.append(f"  base  {commits['base'][:12]}")
    lines.append("")

    if report["status"] == "TEXT_CONFLICT":
        lines.append("Git reported textual conflicts in:")
        lines.extend(f"  {path}" for path in report["merge"]["conflicts"])
        lines.append("")

    for finding in report["findings"]:
        use, change = finding["provenance"]["use"], finding["provenance"]["change"]
        lines.append(f"[{finding['rule_id']}] {finding['title']}  {finding['file']}:{finding['line']}")
        lines.append(f"  use:     {finding['use']}  ({use['origin']} by {use['ref']})")
        lines.append(f"  reason:  {finding['reason']}")
        where = change.get("file") or ""
        if change.get("line"):
            where += f":{change['line']}"
        lines.append(f"  change:  {change['ref']} {change['kind'].replace('_', ' ')} {where}".rstrip())
        if change.get("before"):
            after = change.get("after") or "(removed)"
            lines.append(f"           {change['before']}  ->  {after}")
        lines.append(f"  {finding['message']}")
        lines.append("")

    relevant = [u for u in report["unsupported"] if u["relevant"]]
    if relevant:
        lines.append("Unsupported code relevant to the branches' changes:")
        lines.extend(f"  {u['file']}:{u['line']}  {u['use']}  ({u['reason']})" for u in relevant)
        lines.append("")
    coverage = report["coverage"]
    for error in coverage.get("syntax_errors", []):
        lines.append(f"Syntax error on {error['state']}: {error['file']}: {error['error']}")
    if coverage:
        lines.append(
            "coverage: {examined} uses examined, {tracked} resolved to local code, "
            "{shadowed} shadowed, {excluded} existing defect(s) excluded, "
            "{relevant} relevant unsupported".format(
                examined=coverage.get("uses_examined", 0),
                tracked=coverage.get("uses_tracked", 0),
                shadowed=coverage.get("uses_shadowed", 0),
                excluded=coverage.get("existing_defects_excluded", 0),
                relevant=coverage.get("unsupported_relevant", 0),
            )
        )
    for note in report["notes"]:
        lines.append(f"note: {note}")
    lines.append(report["meaning"])
    return "\n".join(lines)
