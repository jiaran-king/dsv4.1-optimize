"""Verify archived Case 21 request timelines and both optimization rounds."""

import json
from pathlib import Path
from statistics import median

from report import check_value, load_trials, points_for


RESULTS = Path(__file__).resolve().parents[1] / "results" / "case21"


def main():
    comparison = json.loads((RESULTS / "comparison.json").read_text(encoding="utf-8"))
    trials = load_trials(RESULTS)
    by_trial = {trial["trial"]: trial for trial in trials}
    workload = comparison["workload"]
    acceptance = comparison["acceptance"]
    cards = comparison["deployment"]["decode_physical_cards"]
    limit = acceptance["mean_tpot_limit_ms"]
    if len(by_trial) != len(trials):
        raise ValueError("Duplicate trial IDs")
    for trial in trials:
        if (
            trial["completed_requests"] != trial["planned_requests"]
            or trial["prompt_row_sha256"] != workload["prompt_row_sha256"]
        ):
            raise ValueError(f"{trial['trial']} did not complete the expected workload")

    steady_output = {}
    full_output = {}
    metric = "output_tok_s_d_card"
    for stage, summary in comparison["formal"].items():
        labels = summary["trials"]
        if len(set(labels)) != len(labels) or len(labels) != acceptance["repetitions_per_profile"]:
            raise ValueError(f"{stage} has missing or duplicate confirmation trials")
        selected = [by_trial[label] for label in labels]
        expected = (stage, summary["concurrency"], summary["request_rate"], workload["requests"])
        for trial in selected:
            actual = (trial["profile"], trial["concurrency"], trial["request_rate"], trial["planned_requests"])
            if actual != expected or trial["steady"] is None:
                raise ValueError(f"{trial['trial']} does not match the {stage} confirmation settings")
        point, = points_for(selected, cards, limit)
        if point["runs_below_limit"] != len(selected):
            raise ValueError(f"{stage} did not meet the TPOT limit in every confirmation trial")
        for field in (metric, "ttft_mean_ms", "tpot_mean_ms", "tpot_p90_ms"):
            check_value(f"{stage}/{field}", point[field], summary[field])
        steady_output[stage] = point[metric]
        full_output[stage] = median(trial["full"]["output_tok_s"] for trial in selected) / cards
        check_value(f"{stage}/full throughput", full_output[stage], summary["full_output_tok_s_d_card"])

    gains = {
        "round1_vs_baseline": 100 * (steady_output["round1"] / steady_output["baseline"] - 1),
        "round2_vs_round1": 100 * (steady_output["round2"] / steady_output["round1"] - 1),
        "round2_vs_baseline": 100 * (steady_output["round2"] / steady_output["baseline"] - 1),
        "round2_full_vs_round1_full": 100 * (full_output["round2"] / full_output["round1"] - 1),
    }
    for label, gain in gains.items():
        check_value(label, gain, comparison["gain_pct"][label])
    if min(gains["round1_vs_baseline"], gains["round2_vs_round1"]) < acceptance["minimum_gain_pct_per_round"]:
        raise ValueError("A round missed the median throughput improvement target")

    print(f"Verified {len(trials)} trials and {sum(trial['planned_requests'] for trial in trials)} requests.")
    print(f"D steady output per card: {steady_output['baseline']:,.2f} → {steady_output['round1']:,.2f}"
          f" → {steady_output['round2']:,.2f} tok/s")
    print(f"Round gains: +{gains['round1_vs_baseline']:.2f}%, +{gains['round2_vs_round1']:.2f}%."
          f" Cumulative: +{gains['round2_vs_baseline']:.2f}%.")


if __name__ == "__main__":
    main()
