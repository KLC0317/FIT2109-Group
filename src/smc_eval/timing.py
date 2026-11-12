"""Timing harness: repeated checker runs summarised as CSV (proposal Section 4, technique 2).

    python -m smc_eval timing --scenarios <dir> --out <dir> [--runs 5]

Each run's JSON-lines log gives the per-stage durations. Run 1 for a case
is recorded as "first" (cold: first run after the fixtures were rebuilt);
the rest are "repeated".

Following the Week 9 method, the timer covers the whole command a developer
waits for, every individual run is kept in the CSV, the summary reports the
median together with the range, and each case's result (status and
findings) must be identical across runs, so a faster run that changes the
answer is never counted as an improvement. Profiling is a separate step
(cprofile_analyser), never switched on while timing.
"""

from __future__ import annotations

import csv
import json
import os
import statistics
import subprocess
import time
from pathlib import Path

from smc_eval.harness import CHECKER, bash

DEFAULT_CASES = [
    ("latency100", "latency-api", "latency-caller"),
    ("c05", "r2-api-change", "r2-new-caller"),
    ("c13", "safe-optional-email", "safe-badge"),
    ("c25", "conflict-team-field", "conflict-email-field"),
]
STAGES = ["validate", "merge_base", "preflight", "workdir", "merge", "export", "analyse"]
ANALYSER_STAGES = ["parse", "analyse", "report"]


def stage_times(log: Path) -> dict[str, float]:
    times: dict[str, float] = {}
    for line in log.read_text(encoding="utf-8").splitlines():
        record = json.loads(line)
        if record.get("event") != "stage":
            continue
        prefix = "py_" if record["component"] == "analyser" else ""
        times[prefix + record["stage"]] = float(record["duration_ms"])
    return times


def result_signature(report: Path) -> str:
    """The behaviour every run must preserve: status plus findings."""
    if not report.exists():
        return "no report"
    data = json.loads(report.read_text(encoding="utf-8"))
    findings = sorted(f"{f['rule_id']}:{f['file']}:{f['line']}" for f in data.get("findings", []))
    return " ".join([data.get("status", "?"), *findings])


def time_cases(scenarios: Path, out: Path, runs: int, cases=DEFAULT_CASES) -> list[dict]:
    out.mkdir(parents=True, exist_ok=True)
    rows = []
    for case, ref_a, ref_b in cases:
        repo = scenarios / case
        if not repo.exists():
            print(f"skip {case}: {repo} not built")
            continue
        for run in range(1, runs + 1):
            log = out / "logs" / f"{case}-{run}.jsonl"
            report = out / "reports" / f"{case}-{run}.json"
            log.unlink(missing_ok=True)
            start = time.perf_counter()
            done = subprocess.run(
                [bash(), CHECKER.as_posix(), "--repo", repo.as_posix(), "--out-dir", (out / "checker").as_posix(),
                 "--json", report.as_posix(), "--log", log.as_posix(), "--quiet", ref_a, ref_b],
                capture_output=True, text=True, env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
            )
            wall = round((time.perf_counter() - start) * 1000, 1)
            stages = stage_times(log)
            row = {"case": case, "run": run, "kind": "first" if run == 1 else "repeated",
                   "exit": done.returncode, "wall_ms": wall, "result": result_signature(report)}
            row.update({s: stages.get(s, "") for s in STAGES})
            row.update({f"py_{s}": stages.get(f"py_{s}", "") for s in ANALYSER_STAGES})
            rows.append(row)
            print(f"{case} run {run}: exit {done.returncode}, {wall:.0f} ms", flush=True)
    with (out / "timing.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    return rows


def summarise(rows: list[dict]) -> list[dict]:
    summary = []
    for case in dict.fromkeys(r["case"] for r in rows):
        mine = [r for r in rows if r["case"] == case]
        walls = [r["wall_ms"] for r in mine]
        stage_medians = {s: statistics.median(float(r[s]) for r in mine if r[s] != "") for s in STAGES
                         if any(r[s] != "" for r in mine)}
        dominant = max(stage_medians, key=stage_medians.get) if stage_medians else ""
        results = {r["result"] for r in mine}
        summary.append({
            "case": case,
            "runs": len(mine),
            "first_ms": mine[0]["wall_ms"],
            "median_ms": statistics.median(walls),
            "min_ms": min(walls),
            "max_ms": max(walls),
            "range_ms": round(max(walls) - min(walls), 1),
            "median_repeated_ms": statistics.median(walls[1:]) if len(walls) > 1 else walls[0],
            "same_result": len(results) == 1,
            "result": mine[0]["result"],
            "dominant_stage": dominant,
            "dominant_stage_median_ms": stage_medians.get(dominant, 0),
            "stage_medians_ms": stage_medians,
        })
    return summary


def render(summary: list[dict], target_ms: float = 5000) -> str:
    lines = ["| Case | Runs | First (ms) | Median (ms) | Range (ms) | Same result every run | Dominant stage |",
             "|---|---|---|---|---|---|---|"]
    for s in summary:
        same = "yes" if s["same_result"] else "NO"
        lines.append(f"| {s['case']} | {s['runs']} | {s['first_ms']:.0f} | {s['median_ms']:.0f} | "
                     f"{s['min_ms']:.0f}-{s['max_ms']:.0f} ({s['range_ms']:.0f}) | {same} | "
                     f"{s['dominant_stage']} ({s['dominant_stage_median_ms']:.0f} ms) |")
    latency = next((s for s in summary if s["case"] == "latency100"), None)
    if latency:
        verdict = "met" if latency["median_ms"] < target_ms else "NOT met"
        lines += ["", f"Target: median under {target_ms / 1000:.0f} s on the 100-file fixture: "
                      f"{latency['median_ms'] / 1000:.2f} s ({verdict})."]
    return "\n".join(lines) + "\n"


def cprofile_analyser(scenarios: Path, out: Path, case: str = "latency100",
                      refs: tuple[str, str] = ("latency-api", "latency-caller"), top: int = 15) -> str:
    """Function profile of the Python analyser on one case (separate from timing).

    The checker runs once with --keep-temp so its manifest survives; the
    analyser is then re-run on that manifest under cProfile and the top
    functions by cumulative time are written to <out>/cprofile.txt.
    """
    import io
    import pstats
    import sys

    from smc_eval.harness import ROOT, _force_remove

    work_out = out / "cprofile-run"
    _force_remove(work_out)
    subprocess.run([bash(), CHECKER.as_posix(), "--repo", (scenarios / case).as_posix(), "--out-dir",
                    work_out.as_posix(), "--quiet", "--keep-temp", *refs], capture_output=True, text=True)
    kept = sorted((work_out / "tmp").glob("run.*"))
    if not kept:
        raise RuntimeError("the checker did not keep its work directory")
    stats_file = out / "analyser.prof"
    subprocess.run([sys.executable, "-m", "cProfile", "-o", str(stats_file), "-m", "smc", "analyse",
                    "--manifest", str(kept[-1] / "manifest.json"), "--quiet"],
                   env={**os.environ, "PYTHONPATH": str(ROOT / "src"), "PYTHONDONTWRITEBYTECODE": "1"},
                   capture_output=True, text=True)
    text = io.StringIO()
    stats = pstats.Stats(str(stats_file), stream=text)
    stats.strip_dirs().sort_stats("cumulative").print_stats(top)
    (out / "cprofile.txt").write_text(text.getvalue(), encoding="utf-8", newline="\n")
    _force_remove(work_out)
    return text.getvalue()
