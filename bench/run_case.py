"""Warm four Prefill ranks, launch AISBench, and audit the request timeline."""

import argparse
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import urllib.request


BENCH = Path(__file__).resolve().parent
CASES = {"smoke": (8, 2, 1.0), "full1300": (1300, 130, 3.6), "steady": (576, 216, 0.0)}
GENERATION = {"temperature": 0, "ignore_eos": True, "seed": 1024}
OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}))


def http(url, payload=None):
    data = None if payload is None else json.dumps(payload).encode("utf-8")
    headers = {} if data is None else {"Content-Type": "application/json"}
    with OPENER.open(urllib.request.Request(url, data=data, headers=headers), timeout=240 if data else 10) as response:
        return response.read()


def prefix_counts(prefillers):
    def scrape(endpoint):
        counts = {}
        for line in http(endpoint + "/metrics").decode("utf-8").splitlines():
            match = re.fullmatch(
                r"vllm:prefix_cache_(hits|queries)(?:_total)?(?:\{[^}]*\})?\s+([\d.eE+-]+)", line,
            )
            if match:
                key, value = match.groups()
                counts[key] = counts.get(key, 0) + int(float(value))
        return counts if {"hits", "queries"} <= counts.keys() else None

    with ThreadPoolExecutor(max_workers=4) as workers:
        return list(workers.map(scrape, prefillers))


def run(args):
    count, default_concurrency, request_rate = CASES[args.case]
    concurrency = args.concurrency if args.concurrency is not None else default_concurrency
    if not 1 <= concurrency <= count:
        raise ValueError("Concurrency must be between 1 and the number of requests")
    output = args.output.resolve()
    output.mkdir(parents=True)
    dataset = args.dataset.resolve(strict=True)
    tokenizer = args.tokenizer.resolve(strict=True)
    with dataset.open("rb") as source:
        dataset_sha256 = hashlib.file_digest(source, "sha256").hexdigest()
    with dataset.open(encoding="utf-8") as source:
        prompt = json.loads(next(source))["question"]

    proxy = f"http://{args.proxy_host}:{args.proxy_port}"
    prefillers = [f"http://{args.prefill_host}:{args.prefill_api_port + rank}" for rank in range(4)]
    health = json.loads(http(proxy + "/healthcheck"))
    if (health.get("prefill_instances"), health.get("decode_instances")) != (4, 16):
        raise RuntimeError("The Proxy is expected to have four P and sixteen D endpoints")
    messages = [{"role": "user", "content": prompt}]
    call_args = {"model": "dsv41", "messages": messages}
    measured = json.loads(http(prefillers[0] + "/tokenize", call_args))["count"]
    if measured != 131072:
        raise ValueError(f"The service rendered {measured} input tokens, expected 131072")

    def warm(endpoint):
        result = http(endpoint + "/v1/chat/completions", dict(call_args, temperature=0, max_tokens=1))
        return json.loads(result)["usage"]["prompt_tokens"]

    with ThreadPoolExecutor(max_workers=4) as workers:
        warm_counts = list(workers.map(warm, prefillers))
    if warm_counts != [131072] * 4:
        raise RuntimeError("The four P warmups did not use 131072 input tokens")
    before = prefix_counts(prefillers)
    env = dict(os.environ, AISBENCH_DATASET_PATH=str(dataset), HF_HUB_OFFLINE="1", TRANSFORMERS_OFFLINE="1")
    for key in ("http_proxy", "https_proxy", "all_proxy", "HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY"):
        env.pop(key, None)
    command = [
        "ais_bench", "--mode", "perf", "--models", "vllm_api_stream_chat",
        "--host-ip", args.proxy_host, "--host-port", str(args.proxy_port), "--model-name", "dsv41",
        "--path", str(tokenizer), "--config-dir", str(BENCH / "calibrated_configs"),
        "--datasets", "calibrated_128k", "--num-prompts", str(count), "--max-out-len", "1024",
        "--generation-kwargs", json.dumps(GENERATION), "--num-warmups", "0",
        "--request-rate", str(request_rate), "--batch-size", str(concurrency), "--work-dir", str(output / "aisbench"),
    ]
    print(f"Running {count} timed requests at concurrency {concurrency}", flush=True)
    with (output / "aisbench.log").open("x", encoding="utf-8") as log:
        subprocess.run(command, env=env, stdout=log, stderr=subprocess.STDOUT, check=True)
    after = prefix_counts(prefillers)
    hit_rate = None
    if all(entry is not None for entry in before + after):
        hits = sum(r["hits"] - l["hits"] for l, r in zip(before, after, strict=True))
        queries = sum(r["queries"] - l["queries"] for l, r in zip(before, after, strict=True))
        if 0 <= hits <= queries and queries > 0:
            hit_rate = hits / queries

    details = list((output / "aisbench").rglob("calibrated_128k_details.jsonl"))
    if len(details) != 1:
        raise RuntimeError(f"Expected one AISBench details file, found {len(details)}")
    with (output / "audit.json").open("x", encoding="utf-8") as audit:
        subprocess.run([
            sys.executable, str(BENCH / "audit_benchmark.py"), str(details[0]),
            "--expected", str(count), "--concurrency", str(concurrency),
            "--timeline-output", str(output / "request-timeline.jsonl"),
        ], env=env, stdout=audit, check=True)
    audited = json.loads((output / "audit.json").read_text())
    steady = audited["steady_window"]
    selected = steady["aisbench_start_selected"] if steady is not None else None
    result = {
        "case": args.case,
        "concurrency": concurrency,
        "request_rate": request_rate,
        "dataset_sha256": dataset_sha256,
        "generation": GENERATION,
        "prefill_prefix_hit_rate": hit_rate,
        "full": audited["full_window"],
        "steady": steady,
        "metrics": {"output_tok_s_d_card": selected["output_tokens_per_second"] / 8 if selected else None},
        "checks": {
            "complete_workload": True,
            "mean_tpot_within_limit": selected is not None and selected["tpot_ms_mean"] < 21.0,
        },
    }
    result_json = json.dumps(result, indent=2) + "\n"
    (output / "result.json").write_text(result_json, encoding="utf-8")
    if args.case == "steady" and selected is None:
        raise ValueError("AISBench did not find a steady window")
    if (result_path := os.getenv("INFERRSI_RESULT_PATH")) is not None:
        Path(result_path).write_text(result_json, encoding="utf-8")
    print("RSI_RESULT " + json.dumps(result), flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("case", choices=CASES)
    parser.add_argument("--dataset", type=Path, required=True)
    parser.add_argument("--tokenizer", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--concurrency", type=int)
    for name, env_var in (("--proxy-host", "PD_PROXY_HOST"), ("--prefill-host", "PD_P_HOST")):
        value = os.getenv(env_var)
        parser.add_argument(name, default=value, required=not value, help=f"Fallback is {env_var}")
    parser.add_argument("--proxy-port", type=int, default=8080)
    parser.add_argument("--prefill-api-port", type=int, default=7100)
    run(parser.parse_args())


if __name__ == "__main__":
    main()
