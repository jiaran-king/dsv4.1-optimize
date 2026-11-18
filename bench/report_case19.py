"""Check the archived Case 19 full-window results using per-request timings."""

from collections import defaultdict
import csv
import gzip
import json
from pathlib import Path
from statistics import mean, median, quantiles

from report import check_value


RESULTS = Path(__file__).resolve().parents[1] / "results" / "case19"


def verify_trial(trial, rows, workload, cards):
    label = trial["trial"]
    if len(rows) != workload["requests"] or len({row["row"] for row in rows}) != len(rows):
        raise ValueError(f"{label} has missing or duplicate request records")
    lengths = (workload["input_tokens"], workload["output_tokens"])
    if any(row["success"] != "True" or (int(row["input_tokens"]), int(row["output_tokens"])) != lengths
           for row in rows):
        raise ValueError(f"{label} contains failed requests or unexpected token counts")
    starts = [float(row["start_s"]) for row in rows]
    ends = [float(row["end_s"]) for row in rows]
    ttft = [float(row["ttft_ms"]) for row in rows]
    if any(not 0 < wait <= (end - start) * 1000 + 1e-3 for start, end, wait in zip(starts, ends, ttft)):
        raise ValueError(f"{label} contains invalid timing")
    duration = max(ends) - min(starts)
    input_count = len(rows) * lengths[0]
    output_count = len(rows) * lengths[1]
    expected = {
        "requests": len(rows),
        "duration_s": duration,
        "input_tokens_total": input_count,
        "output_tokens_total": output_count,
        "input_tokens_per_second": input_count / duration,
        "output_tokens_per_second": output_count / duration,
        "requests_per_second": len(rows) / duration,
        "ttft_ms_mean": mean(ttft),
        "ttft_ms_p90": quantiles(ttft, n=10, method="inclusive")[-1],
    }
    for key, value in expected.items():
        check_value(f"{label}/{key}", value, trial["full"][key])
    check_value(f"{label}/input_per_card", expected["input_tokens_per_second"] / cards, trial["input_tok_s_p_card"])
    counters = trial["prefill_prefix_cache"]
    check_value(f"{label}/cache_hit", counters["hits"] / counters["queries"], trial["prefill_prefix_hit_rate"])


def summarize(trials):
    return {
        "duration_s": median(row["full"]["duration_s"] for row in trials),
        "mean_ttft_ms": median(row["full"]["ttft_ms_mean"] for row in trials),
        "p90_ttft_ms": median(row["full"]["ttft_ms_p90"] for row in trials),
        "input_tok_s_p_card": median(row["input_tok_s_p_card"] for row in trials),
        "prefill_prefix_hit_rate": median(row["prefill_prefix_hit_rate"] for row in trials),
    }


def verify_points(trials, threshold):
    groups = defaultdict(list)
    for trial in trials:
        if "curve_profile" in trial:
            groups[(trial["curve_profile"], trial["concurrency"], trial["request_rate"])].append(trial)
    with (RESULTS / "points.csv").open(newline="", encoding="utf-8") as stream:
        points = {(row["profile"], int(row["concurrency"]), float(row["request_rate"])): row
                  for row in csv.DictReader(stream)}
    if set(groups) != set(points):
        raise ValueError("Curve points disagree with the marked trials")
    for key, rows in groups.items():
        point = points[key]
        stats = summarize(rows)
        check_value(f"{key}/runs", len(rows), int(point["runs"]))
        for field in ("mean_ttft_ms", "p90_ttft_ms", "input_tok_s_p_card"):
            check_value(f"{key}/{field}", stats[field], float(point[field]))
        eligible = all(row["full"]["ttft_ms_mean"] < threshold for row in rows)
        if str(eligible) != point["eligible"]:
            raise ValueError(f"{key} has the wrong TTFT eligibility")
    return len(points)


def main():
    comparison = json.loads((RESULTS / "comparison.json").read_text())
    trials = json.loads((RESULTS / "trials.json").read_text())
    by_trial = {trial["trial"]: trial for trial in trials}
    requests = defaultdict(list)
    with gzip.open(RESULTS / "requests.csv.gz", "rt", encoding="utf-8", newline="") as stream:
        for row in csv.DictReader(stream):
            requests[row["trial"]].append(row)
    if set(requests) != set(by_trial) or len(by_trial) != len(trials):
        raise ValueError("Trial identifiers disagree between files")
    workload = comparison["workload"]
    acceptance = comparison["acceptance"]
    threshold = acceptance["mean_ttft_limit_ms"]
    for label, trial in by_trial.items():
        expected_sha = (
            comparison["eplb_calibration"]["sha256"]
            if trial["purpose"] == "calibration"
            else workload["dataset_sha256"]
        )
        if trial["dataset_sha256"] != expected_sha:
            raise ValueError(f"{label} has a mismatched dataset")
        verify_trial(trial, requests[label], workload, comparison["deployment"]["prefill_cards"])
    for arm in ("baseline", "optimized"):
        summary = comparison[arm]
        labels = summary["trials"]
        if len(labels) != acceptance["repetitions_per_arm"] or len(set(labels)) != len(labels):
            raise ValueError(f"{arm} has missing or duplicate confirmation trials")
        selected = [by_trial[label] for label in labels]
        expected_load = (summary["concurrency"], summary["request_rate"])
        if any(
            row["purpose"] != "evaluation"
            or (row["concurrency"], row["request_rate"]) != expected_load
            or row["full"]["ttft_ms_mean"] >= threshold
            for row in selected
        ):
            raise ValueError(f"{arm} has an invalid confirmation group")
        for field, value in summarize(selected).items():
            check_value(f"{arm}/{field}", value, summary[field])
    same_load = comparison["fixed_load_c42"]
    base, control, candidate = (by_trial[same_load[key]] for key in ("baseline_trial", "pre_eplb_trial", "optimized_trial"))
    if any((row["concurrency"], row["request_rate"], row["purpose"]) != (42, 0, "evaluation")
           for row in (base, control, candidate)):
        raise ValueError("The fixed-concurrency comparison changed the workload")
    metric = "input_tok_s_p_card"
    check_value("fixed load gain", 100 * (candidate[metric] / base[metric] - 1), same_load["gain_pct"])
    check_value("EPLB stage gain", 100 * (candidate[metric] / control[metric] - 1), same_load["eplb_stage_gain_pct"])
    gain = 100 * (comparison["optimized"][metric] / comparison["baseline"][metric] - 1)
    check_value("peak gain", gain, comparison["improvement_pct"])
    if gain < acceptance["minimum_gain_pct"]:
        raise ValueError("The confirmation trials missed the throughput target")
    points = verify_points(trials, threshold)
    print(f"Verified {len(trials)} trials, {sum(len(rows) for rows in requests.values())} requests, and {points} curve points.")
    print(f"P input throughput per card improved by {gain:.2f}%.")


if __name__ == "__main__":
    main()
