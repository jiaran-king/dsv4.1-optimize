"""Verify archived request timelines, aggregate concurrency points, and render curves."""

import argparse
from collections import defaultdict
import csv
import gzip
import json
import math
from pathlib import Path
from statistics import mean, median


RESULTS = Path(__file__).resolve().parents[1] / "results"
SERIES = ("baseline", "optimized", "ab", "supplemental")


def check_value(label, calculated, recorded):
    if not math.isclose(calculated, recorded, rel_tol=1e-10, abs_tol=1e-8):
        raise ValueError(f"{label} is {calculated}, expected {recorded}")


def check_window(label, window, rows, duration):
    tpot = sorted(float(row["tpot_ms"]) for row in rows)
    position = (len(tpot) - 1) * 0.90
    lower, upper = math.floor(position), math.ceil(position)
    p90 = tpot[lower] + (tpot[upper] - tpot[lower]) * (position - lower)
    output_count = sum(int(row["output_tokens"]) for row in rows)
    values = {
        "requests": len(rows),
        "duration_s": duration,
        "input_tokens": sum(int(row["input_tokens"]) for row in rows),
        "output_tokens": output_count,
        "output_tok_s": output_count / duration,
        "ttft_mean_ms": mean(float(row["ttft_ms"]) for row in rows),
        "tpot_mean_ms": mean(tpot),
        "tpot_p90_ms": p90,
    }
    for key, calculated in values.items():
        check_value(f"{label}/{key}", calculated, window[key])


def load_trials(root):
    trials = json.loads((root / "trials.json").read_text())
    by_trial = defaultdict(list)
    with gzip.open(root / "requests.csv.gz", "rt", encoding="utf-8", newline="") as stream:
        for row in csv.DictReader(stream):
            by_trial[row["trial"]].append(row)
    if set(by_trial) != {trial["trial"] for trial in trials}:
        raise ValueError(f"Trial IDs differ between measurements and requests in {root.name}")
    for trial in trials:
        label = f"{root.name}/{trial['trial']}"
        rows = by_trial[trial["trial"]]
        successful = [row for row in rows if row["success"] == "True"]
        check_value(f"{label}/planned", len(rows), trial["planned_requests"])
        check_value(f"{label}/completed", len(successful), trial["completed_requests"])
        for row in successful:
            if (int(row["input_tokens"]), int(row["output_tokens"])) != (131072, 1024):
                raise ValueError(f"{label} contains a request outside the 128K/1K workload")
        full_start = min(float(row["start_s"]) for row in successful)
        full_end = max(float(row["end_s"]) for row in successful)
        check_window(f"{label}/full", trial["full"], successful, full_end - full_start)
        steady = trial["steady"]
        cohort = [row for row in successful if row["aisbench_steady_selected"] == "True"]
        if steady is not None:
            check_window(f"{label}/steady", steady, cohort, steady["end_s"] - steady["start_s"])
        elif cohort:
            raise ValueError(f"{label} has steady rows without a recorded window")
    return trials


def points_for(trials, cards, limit):
    runs_by_concurrency = defaultdict(list)
    for trial in trials:
        runs_by_concurrency[trial["concurrency"]].append(trial["steady"])
    points = []
    for concurrency, runs in sorted(runs_by_concurrency.items()):
        def median_for(key):
            return median(run[key] for run in runs)

        mean_tpot = [run["tpot_mean_ms"] for run in runs]
        points.append({
            "concurrency": concurrency,
            "runs": len(runs),
            "runs_below_limit": sum(value < limit for value in mean_tpot),
            "steady_requests_min": min(run["requests"] for run in runs),
            "steady_requests_max": max(run["requests"] for run in runs),
            "tpot_mean_ms": median(mean_tpot),
            "tpot_mean_min_ms": min(mean_tpot),
            "tpot_mean_max_ms": max(mean_tpot),
            "tpot_p90_ms": median_for("tpot_p90_ms"),
            "ttft_mean_ms": median_for("ttft_mean_ms"),
            "output_tok_s_d_card": median_for("output_tok_s") / cards,
        })
    return points


def best_point(points):
    return max((point for point in points if point["runs"] == point["runs_below_limit"]),
               key=lambda point: point["output_tok_s_d_card"])


def plot(root, groups, limit, output, title):
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    plt.rcParams.update({"font.family": "DejaVu Sans", "svg.fonttype": "none", "axes.spines.top": False,
                         "axes.spines.right": False})
    fig, ax = plt.subplots(figsize=(8.6, 5.15), layout="constrained")
    ax.set_title(title, loc="left", fontweight="bold", fontsize=15, pad=16)
    ax.set_xlabel("Steady-state mean TPOT (ms/token)")
    ax.set_ylabel("Output tokens/s per Decode card")
    ax.grid(axis="y", alpha=0.22)
    all_values = [p["tpot_mean_ms"] for points in groups.values() for p in points]
    xmin = min(all_values) - 0.35
    xmax = max(all_values + [limit]) + 0.72
    ax.set_xlim(xmin, xmax)
    ax.set_ylim(640, max(p["output_tok_s_d_card"] for points in groups.values() for p in points) + 98)
    ax.axvspan(xmin, limit, color="#edf5ef", zorder=0)
    ax.axvline(limit, color="#596674", linestyle="--", linewidth=1.2, zorder=1)
    ax.text(limit + 0.08, 0.04, f"{limit:g} ms limit", transform=ax.get_xaxis_transform(),
            color="#455260", fontsize=9, ha="left")

    for series, points in groups.items():
        color, marker = {"Baseline": ("#315d84", "o"), "Optimized": ("#b95020", "s")}[series]
        x = [point["tpot_mean_ms"] for point in points]
        y = [point["output_tok_s_d_card"] for point in points]
        ax.plot(x, y, color=color, linewidth=1.1, alpha=0.58, label=series, zorder=2, marker=marker,
                markersize=4, markerfacecolor="none")
        for point in points:
            passed = point["runs"] == point["runs_below_limit"]
            ax.scatter(point["tpot_mean_ms"], point["output_tok_s_d_card"], marker=marker,
                       facecolors=color if passed else "white", edgecolors=color, s=40, zorder=3)
        best = best_point(points)
        ax.scatter(best["tpot_mean_ms"], best["output_tok_s_d_card"], marker=marker,
                   facecolors=color, edgecolors="white", linewidths=1.3, s=105, zorder=4)
        ax.annotate(f"C{best['concurrency']}  {best['output_tok_s_d_card']:,.0f}",
                    (best["tpot_mean_ms"], best["output_tok_s_d_card"]), xytext=(-7, 12),
                    textcoords="offset points", ha="right", color=color, fontsize=10, fontweight="bold")

    ax.legend(loc="upper left", frameon=False)
    fig.savefig(root / f"{output}.png", dpi=170)
    fig.savefig(root / f"{output}.svg", metadata={"Date": None})
    plt.close(fig)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--results", type=Path, default=RESULTS)
    parser.add_argument("--plot", action="store_true", help="Render PNG and SVG figures with matplotlib")
    args = parser.parse_args()
    root = args.results
    manifest = json.loads((root / "manifest.json").read_text())
    cards = manifest["platform"]["decode_cards"]
    limit = manifest["mean_tpot_limit_ms"]
    trials = {series: load_trials(root / series) for series in SERIES}
    point_groups = {series: points_for(trials[series], cards, limit) for series in ("baseline", "optimized")}
    for series, points in point_groups.items():
        with (root / series / "points.csv").open("w", encoding="utf-8", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=list(points[0]), lineterminator="\n")
            writer.writeheader()
            writer.writerows(points)
    baseline = best_point(point_groups["baseline"])
    optimized = best_point(point_groups["optimized"])
    pair = json.loads((root / "ab/pair.json").read_text())
    control = next(t for t in trials["ab"] if t["trial"] == pair["baseline"]["trial"])
    treatment = next(t for t in trials["optimized"] if t["trial"] == pair["candidate"]["trial"])
    response = {
        "baseline": baseline,
        "optimized": optimized,
        "peak_gain_pct": 100 * (optimized["output_tok_s_d_card"] / baseline["output_tok_s_d_card"] - 1),
        "prefill_worker_gain_pct": 100 * (treatment["steady"]["output_tok_s"] / control["steady"]["output_tok_s"] - 1),
        "trials_verified": sum(len(items) for items in trials.values()),
        "request_rows_verified": sum(t["planned_requests"] for items in trials.values() for t in items),
    }
    (root / "comparison.json").write_text(json.dumps(response, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(response, indent=2))
    if args.plot:
        groups = {"Baseline": point_groups["baseline"], "Optimized": point_groups["optimized"]}
        plot(root, groups, limit, "tpot-throughput", "DeepSeek V4.1 Flash on Ascend A3")
        plot(root / "baseline", {"Baseline": point_groups["baseline"]}, limit, "baseline-curve", "Baseline concurrency sweep")


if __name__ == "__main__":
    main()
