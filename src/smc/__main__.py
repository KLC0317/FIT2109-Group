"""Analyser entry point, called by scripts/silent-merge-check.sh.

    python -m smc analyse --manifest <manifest.json> [--quiet]

The manifest is written by the Bash orchestrator. It names the exported
directory and a NUL-delimited file list for each code state (base, a, b and,
after a clean merge, merged), the resolved commits and the merge result.
Exit codes: 0 SAFE, 1 SILENT BREAK, 2 TEXT CONFLICT, 3 INCONCLUSIVE/ERROR.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from smc.logjson import JsonLog
from smc.report import EXIT_CODES, build_report, render, write_report
from smc.rules import analyse
from smc.snapshot import Snapshot

STATES = ("base", "a", "b", "merged")


def read_list(path: Path) -> list[str]:
    data = path.read_bytes().decode("utf-8", errors="surrogateescape")
    return [item for item in data.split("\0") if item]


def run(manifest_path: Path, quiet: bool = False) -> int:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    log = JsonLog(Path(manifest["log"]) if manifest.get("log") else None, manifest.get("run_id", ""))
    report_path = Path(manifest["report"])
    merge = manifest["merge"]

    if merge["result"] == "conflict":
        conflicts = read_list(Path(merge["conflicts_file"]))
        report = build_report(manifest, "TEXT_CONFLICT", conflicts=conflicts)
    else:
        snapshots = {}
        with log.stage("parse"):
            for label in STATES:
                state = manifest["states"][label]
                snapshots[label] = Snapshot.load(
                    label,
                    Path(state["dir"]),
                    read_list(Path(state["files"])),
                    manifest.get("source_root", "."),
                    manifest["commits"].get(label if label != "merged" else "merged_tree"),
                )
        with log.stage("analyse"):
            result = analyse(snapshots["base"], snapshots["a"], snapshots["b"], snapshots["merged"],
                             manifest.get("refs"))
        report = build_report(
            manifest,
            result.status,
            findings=result.findings,
            coverage=result.coverage,
            excluded=result.excluded,
            unsupported=result.unsupported,
            timings=dict(log.durations),
        )
        log.event("result", status=result.status, findings=len(result.findings),
                  unsupported_relevant=result.coverage["unsupported_relevant"],
                  complete=result.coverage["complete"])

    with log.stage("report"):
        write_report(report, report_path)
    log.close()  # release the log file before the orchestrator appends to it
    if not quiet:
        print(render(report))
    return EXIT_CODES[report["status"]]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m smc")
    commands = parser.add_subparsers(dest="command", required=True)
    analyse_cmd = commands.add_parser("analyse", help="analyse the states named in a manifest")
    analyse_cmd.add_argument("--manifest", type=Path, required=True)
    analyse_cmd.add_argument("--quiet", action="store_true")
    args = parser.parse_args(argv)
    try:
        return run(args.manifest, args.quiet)
    except Exception as exc:  # reported as ERROR, never as SAFE
        print(f"error: analyser failed: {exc.__class__.__name__}: {exc}", file=sys.stderr)
        return EXIT_CODES["ERROR"]


if __name__ == "__main__":
    sys.exit(main())
