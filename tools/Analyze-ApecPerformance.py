#!/usr/bin/env python3
"""Summarize RouteBench evidence without discarding original frame gaps."""
import argparse
import hashlib
import json
from pathlib import Path


def stats(values):
    values = sorted(values)
    if not values:
        return {"count": 0}
    return {
        "count": len(values), "median_ms": values[len(values) // 2],
        "p95_ms": values[min(len(values) - 1, int(len(values) * .95))],
        "p99_ms": values[min(len(values) - 1, int(len(values) * .99))],
        "max_ms": values[-1], "over_8_333_ms": sum(v > 1000 / 120 for v in values),
        "over_16_667_ms": sum(v > 1000 / 60 for v in values),
        "over_50_ms": sum(v > 50 for v in values),
    }


def overlap(start, end, spans):
    return sum(max(0, min(end, right) - max(start, left)) for left, right in spans)


def state_spans(events, property_name, signal_kind, end):
    """Use direct notify observations, never infer activity from frame endpoints."""
    observations = [(event["t_ns"], event["gui"][property_name]) for event in events
                    if event["kind"] in ("setup-begin", signal_kind)]
    spans, started = [], None
    for when, active in observations:
        if active and started is None:
            started = when
        elif not active and started is not None:
            spans.append((started, when))
            started = None
    if started is not None:
        spans.append((started, end))
    return spans


def analyze(path):
    raw = path.read_bytes()
    report = json.loads(raw)
    if report.get("schema", 0) < 3:
        raise ValueError(f"{path}: requires RouteBench schema 3")
    events, frames, renders = report["events"], report["frames"], report["render_frames"]
    end = max([e["t_ns"] for e in events] + [f["t_ns"] for f in frames])
    travel = state_spans(events, "travel_running", "page-travel-running-changed", end)
    commit = state_spans(events, "commit_running", "page-commit-running-changed", end)
    pending = state_spans(events, "pending_grab", "host-pending-changed", end)
    phases, opened = [], {}
    for event in events:
        if event["kind"] == "phase-begin":
            opened[event["phase"]] = event["t_ns"]
        elif event["kind"] == "phase-end":
            phases.append((event["phase"], opened.pop(event["phase"]), event["t_ns"]))
    phase_name = lambda start, stop: next((name for name, left, right in phases
                                          if start >= left and stop <= right), "setup-or-boundary")
    groups, details = {}, []
    for frame in frames:
        if frame["previous_t_ns"] is None:
            continue
        start, stop = frame["previous_t_ns"], frame["t_ns"]
        duration = stop - start
        travelling, holding, loading = (overlap(start, stop, spans) for spans in (travel, commit, pending))
        phase = phase_name(start, stop)
        # "Fully" means contained by signal observations; it is not a claim
        # about GPU presentation, every pixel, or other component animations.
        category = ("within-travel-events" if travelling == duration else
                    "within-commit-events" if holding == duration and not travelling and not loading else
                    "within-pending-events" if loading == duration else
                    "boundary-or-other")
        groups.setdefault(phase, {}).setdefault(category, []).append(duration / 1e6)
        if duration > 16_666_667:
            matching = [r for r in renders if r["present_queued_ns"] is not None
                        and start < r["present_queued_ns"] <= stop]
            cpu = lambda first, last: [(r[last] - r[first]) / 1e6 for r in matching
                                      if r[first] is not None and r[last] is not None]
            details.append({
                "frame_seq": frame["seq"], "phase": phase, "interval_ms": duration / 1e6,
                "category": category, "route": frame["gui"]["route_key"],
                "travel_overlap_ms": travelling / 1e6, "commit_overlap_ms": holding / 1e6,
                "pending_overlap_ms": loading / 1e6,
                "sync_bracket_ms": cpu("sync_begin_ns", "sync_end_ns"),
                "record_bracket_ms": cpu("render_begin_ns", "render_end_ns"),
                "render_frame_bracket_ms": cpu("begin_ns", "end_ns"),
                "events": [{"kind": e["kind"], "offset_ms": (e["t_ns"] - start) / 1e6,
                            "travel": e["gui"]["travel_running"], "commit": e["gui"]["commit_running"],
                            "pending": e["gui"]["pending_grab"]}
                           for e in events if start < e["t_ns"] <= stop],
            })
    cpu_phases = {}
    for name, start, stop in phases:
        selected = [r for r in renders if r["begin_ns"] is not None and start <= r["begin_ns"] < stop]
        cpu_phases[name] = {}
        for label, first, last in [("sync_bracket", "sync_begin_ns", "sync_end_ns"),
                                   ("record_bracket", "render_begin_ns", "render_end_ns"),
                                   ("render_frame_bracket", "begin_ns", "end_ns")]:
            cpu_phases[name][label] = stats([(r[last] - r[first]) / 1e6 for r in selected
                                            if r[first] is not None and r[last] is not None])
    requests = [(i, e) for i, e in enumerate(events) if e["kind"] == "route-request"]
    routes = []
    for position, (index, request) in enumerate(requests):
        if request["phase"] not in ("first-visits", "warm-visits", "routes-settled"):
            continue
        next_time = requests[position + 1][1]["t_ns"] if position + 1 < len(requests) else end
        after = [e for e in events[index + 1:] if e["t_ns"] < next_time]
        active = next((e for e in after if e["kind"] == "host-active-loader-changed"
                       and e["gui"]["active_route"] == request["route"]), None)
        settled = next((e for e in after if e["kind"] == "settle-return"), None)
        presented = next((f for f in frames if request["t_ns"] <= f["t_ns"] < next_time
                          and f["gui"]["active_route"] == request["route"]
                          and f["gui"]["travel_running"]), None)
        routes.append({"phase": request["phase"], "route": request["route"],
                       "active_loader_observed_ms": (active["t_ns"] - request["t_ns"]) / 1e6 if active else None,
                       "first_frame_with_travel_snapshot_ms": (presented["t_ns"] - request["t_ns"]) / 1e6 if presented else None,
                       "settled_observed_ms": (settled["t_ns"] - request["t_ns"]) / 1e6 if settled else None})
    return {
        "source_report": str(path.resolve()), "source_report_sha256": hashlib.sha256(raw).hexdigest(),
        "source_sha": report["source_sha"], "scenario": report["scenario"],
        "environment": report["environment"], "failures": report["failures"], "probes": report["probes"],
        "whole_continuous_run": stats([f["delta_ns"] / 1e6 for f in frames if f["delta_ns"] is not None]),
        "phase_interval_groups": {phase: {name: stats(values) for name, values in groups.items()}
                                  for phase, groups in groups.items()},
        "render_cpu_brackets": cpu_phases, "route_observations": routes, "intervals_over_16_667_ms": details,
        "limits": ["Raw frame gaps are retained in the original report and whole-run statistics.",
                   "Activity groups use direct GUI notify observations. Signal callback order and observation delay remain.",
                   "CPU brackets are elapsed time between Qt render signals, not CPU utilization or GPU execution time.",
                   "Reported refresh rate and frameSwapped do not establish physical high-refresh presentation.",
                   "Statistics use sorted index floor(N*p), matching the historical motion probe."]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("reports", type=Path, nargs="+")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        parser.error("output already exists; retain prior evidence")
    results = [analyze(path) for path in args.reports]
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    for result in results:
        print(json.dumps({"scenario": result["scenario"], "failures": result["failures"],
                          "whole_continuous_run": result["whole_continuous_run"]}))


if __name__ == "__main__":
    main()
