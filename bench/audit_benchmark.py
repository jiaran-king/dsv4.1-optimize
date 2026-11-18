#!/usr/bin/env python3
import argparse
import json
import sqlite3
from pathlib import Path


def read_requests(details):
    import numpy as np
    from ais_bench.benchmark.openicl.icl_inferencer.output_handler.db_utils import load_all_numpy_from_db
    from ais_bench.benchmark.utils.perf_details import derive_request_metrics

    databases = {}
    requests = []
    with details.open(encoding="utf-8") as stream:
        for index, line in enumerate(stream):
            data = json.loads(line)
            row = {"row": index, "success": bool(data.get("success"))}
            requests.append(row)
            if not row["success"]:
                continue
            points = data.get("time_points")
            if isinstance(points, dict):
                name = data.get("db_name")
                if not name or Path(name).name != name:
                    raise ValueError(f"Invalid AISBench DB name in row {index}")
                if name not in databases:
                    path = (details.parent / "db_data" / name).resolve()
                    with sqlite3.connect(path.as_uri() + "?mode=ro", uri=True) as db:
                        databases[name] = load_all_numpy_from_db(db)
                points = databases[name].get(points.get("__db_ref__"))
            if points is None or len(points) < 2:
                continue
            it = data.get("input_tokens")
            ot = data.get("output_tokens")
            derived = derive_request_metrics(np.asarray(points), ot)
            row.update(
                start_s=float(points[0]),
                end_s=float(points[-1]),
                input_tokens=it,
                output_tokens=ot,
                ttft_ms=float(derived["ttft"]) * 1000,
                tpot_ms=None if derived["tpot"] is None else float(derived["tpot"]) * 1000,
            )
    return requests


def metrics(rows, start, end):
    import numpy as np

    duration = end - start
    result = {
        "requests": len(rows),
        "duration_s": duration,
        "requests_per_second": len(rows) / duration if duration > 0 else None,
    }
    for name in ("input_tokens", "output_tokens"):
        values = [row[name] for row in rows]
        total = sum(values) if all(isinstance(value, int) for value in values) else None
        result[name + "_total"] = total
        result[name + "_per_second"] = total / duration if total is not None and duration > 0 else None
    for name in ("ttft_ms", "tpot_ms"):
        values = [row[name] for row in rows if row[name] is not None]
        if values:
            result[name + "_mean"] = float(np.mean(values))
            result[name + "_p90"] = float(np.percentile(values, 90))
    return result


def main():
    parser = argparse.ArgumentParser(description="Audit AISBench full and steady request cohorts.")
    parser.add_argument("details", type=Path)
    parser.add_argument("--expected", type=int, required=True)
    parser.add_argument("--concurrency", type=int, required=True)
    parser.add_argument("--timeline-output", type=Path, required=True)
    args = parser.parse_args()
    from ais_bench.benchmark.calculators import StablePerfMetricCalculator
    from ais_bench.benchmark.utils.logging.exceptions import AISBenchDataContentError

    requests = read_requests(args.details)
    timed = [row for row in requests if "start_s" in row]
    if not timed:
        raise SystemExit("No successful request rows with timings")

    first = min(row["start_s"] for row in timed)
    last = max(row["end_s"] for row in timed)
    successes = sum(row["success"] for row in requests)
    report = {
        "planned_requests": args.expected,
        "recorded_rows": len(requests),
        "successful_rows": successes,
        "failed_rows": len(requests) - successes,
        "successful_rows_without_timing": successes - len(timed),
        "different_input_or_output_length": sum(
            (row["input_tokens"], row["output_tokens"]) != (131072, 1024) for row in timed
        ),
        "full_window": metrics(timed, first, last),
    }
    perf = {
        "id": list(range(len(timed))),
        "start_time": [row["start_s"] for row in timed],
        "end_time": [row["end_s"] for row in timed],
    }
    calc = StablePerfMetricCalculator()
    calc.max_concurrency = args.concurrency
    calc.stage_section = [0, 0]
    try:
        selected = calc._get_requests_id(perf)
    except AISBenchDataContentError:
        report["steady_window"] = None
    else:
        steady_start, steady_end = calc.stage_section
        cohort = [timed[i] for i in selected]
        completed = [row for row in timed if steady_start <= row["end_s"] <= steady_end]
        report["steady_window"] = {
            "relative_start_s": steady_start - first,
            "relative_end_s": steady_end - first,
            "aisbench_start_selected": metrics(cohort, steady_start, steady_end),
            "actually_completed_in_window": metrics(completed, steady_start, steady_end),
        }
        for row in cohort:
            row["aisbench_steady_selected"] = True
    with args.timeline_output.open("x", encoding="utf-8") as stream:
        for row in requests:
            if "start_s" in row:
                row["start_s"] -= first
                row["end_s"] -= first
            stream.write(json.dumps(row) + "\n")
    print(json.dumps(report, indent=2), flush=True)
    if (len(requests) != args.expected or successes != args.expected
            or successes != len(timed) or report["different_input_or_output_length"]):
        raise SystemExit("The recorded requests failed the count, success or length audit")


if __name__ == "__main__":
    main()
