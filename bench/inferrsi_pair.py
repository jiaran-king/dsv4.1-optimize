"""Pair a retained graph78/worker-1 measurement with a worker-4 run."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--a-result", type=Path, required=True)
    parser.add_argument("--dataset", type=Path, required=True)
    parser.add_argument("--tokenizer", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    for name, env_var in (("--proxy-host", "PD_PROXY_HOST"), ("--prefill-host", "PD_P_HOST")):
        default = os.getenv(env_var)
        parser.add_argument(name, default=default, required=not default, help=f"Fallback is {env_var}")
    parser.add_argument("--proxy-port", type=int, default=8080)
    parser.add_argument("--prefill-api-port", type=int, default=7100)
    args = parser.parse_args()

    from inferrsi.apps.legacy.run import run_experiment
    from inferrsi.contracts import RunSpec

    reference = args.a_result.resolve(strict=True)
    a = json.loads(reference.read_text())
    with args.dataset.open("rb") as source:
        workload_hash = hashlib.file_digest(source, "sha256").hexdigest()
    if (a["case"], a["concurrency"], a["dataset_sha256"]) != ("steady", 216, workload_hash):
        parser.error("A must use the same 576-request dataset and concurrency 216")
    if not all(a["checks"].values()):
        parser.error("A needs a complete workload and a steady mean TPOT below 21 ms")

    output = args.output.resolve()
    if output.exists():
        parser.error("Use a new output directory")
    candidate = (
        sys.executable, str(ROOT / "bench/run_case.py"), "steady",
        "--dataset", str(args.dataset.resolve()), "--tokenizer", str(args.tokenizer.resolve()),
        "--proxy-host", args.proxy_host, "--proxy-port", str(args.proxy_port),
        "--prefill-host", args.prefill_host, "--prefill-api-port", str(args.prefill_api_port),
        "--output", str(output / "candidate"),
    )
    replay = "from shutil import copyfile; from sys import argv; copyfile(argv[1], argv[2])"
    revision = subprocess.check_output(["git", "-C", str(ROOT), "rev-parse", "HEAD"], text=True).strip()
    spec = RunSpec(
        repo=str(ROOT), repo_type="vllm_ascend", revision=revision,
        backend="ascend", device="A3", model="DeepSeek-V4.1-Flash", model_revision="1017 W4A8",
        scenario="dsv41_pd_128k_1k_c216", workload_id=workload_hash,
        baseline_command=(sys.executable, "-c", replay, str(reference), "{result}"),
        candidate_command=candidate, repetitions=1, direction="maximize",
        metric_key="metrics.output_tok_s_d_card", metric_unit="tok/s/D card",
        comparison_scope="prefill_renderer_workers",
        required_trial_checks=("checks.complete_workload", "checks.mean_tpot_within_limit"),
        output_dir=str(output / "inferrsi"),
    )
    report_dir = run_experiment(spec, {
        "comparison": "Graph78 worker 1 versus graph78 worker 4",
        "baseline_replayed": True,
        "baseline_result_sha256": hashlib.sha256(reference.read_bytes()).hexdigest(),
        "control": "Retain the same Decode and Proxy processes between arms",
    })
    print(report_dir)


if __name__ == "__main__":
    main()
