#!/usr/bin/env python3
import argparse
import json
import os
import signal
import subprocess
import time
from pathlib import Path


def parse_args():
    parser = argparse.ArgumentParser(description="Start one side of the A3 1P1D service.")
    parser.add_argument("role", choices=("p", "d"))
    parser.add_argument("--profile", choices=("baseline", "graph78", "optimized"), default="baseline")
    for flag, env_var, value_type in (
        ("--model-path", "PD_MODEL_PATH", Path),
        ("--local-ip", "PD_LOCAL_IP", str),
        ("--nic", "PD_NIC", str),
        ("--devices", "PD_DEVICES", str),
        ("--log-dir", "PD_LOG_DIR", Path),
    ):
        default = os.environ.get(env_var)
        parser.add_argument(flag, type=value_type, default=default, required=not default,
                            help=f"May also be supplied via {env_var}")
    parser.add_argument("--host-vmm-overlay", type=Path, default=os.getenv("PD_HOST_VMM_OVERLAY"))
    parser.add_argument("--api-base-port", type=int, default=7100)
    parser.add_argument("--dp-rpc-port", type=int, default=12321)
    parser.add_argument("--kv-port", type=int)
    parser.add_argument("--hccl-buffsize", type=int, help="HCCL buffer size in MiB")
    parser.add_argument("--no-expandable-segments", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    configs = Path(__file__).resolve().parents[1] / "configs"
    args.tuning = json.loads((configs / f"{args.profile}.json").read_text())
    args.devices = [device.strip() for device in args.devices.split(",")]
    if len(args.devices) != 16 or len(set(args.devices)) != 16 or not all(d.isdecimal() for d in args.devices):
        parser.error("--devices must contain exactly 16 distinct logical device IDs")
    if args.kv_port is None:
        args.kv_port = 30000 if args.role == "p" else 30100
    if args.hccl_buffsize is not None and args.hccl_buffsize <= 0:
        parser.error("--hccl-buffsize must be positive")
    return args


def engine_specs(args):
    is_prefill = args.role == "p"
    tp_size = 1
    prefill_dp_size = 4
    decode_dp_size = len(args.devices) // tp_size
    dp_size = prefill_dp_size if is_prefill else decode_dp_size
    pcp_size = len(args.devices) // (dp_size * tp_size)
    transfer = {
        "kv_connector": "MooncakeHybridConnector",
        "kv_role": "kv_producer" if is_prefill else "kv_consumer",
        "kv_port": str(args.kv_port),
        "kv_connector_extra_config": {
            "prefill": {"dp_size": prefill_dp_size, "tp_size": tp_size},
            "decode": {"dp_size": decode_dp_size, "tp_size": tp_size},
        },
    }
    env = os.environ.copy()
    for key in ("http_proxy", "https_proxy", "all_proxy", "HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY"):
        env.pop(key, None)
    env.update({
        "HCCL_IF_IP": args.local_ip,
        "VLLM_HOST_IP": args.local_ip,
        "GLOO_SOCKET_IFNAME": args.nic,
        "TP_SOCKET_IFNAME": args.nic,
        "HCCL_SOCKET_IFNAME": args.nic,
        "HCCL_BUFFSIZE": str(args.hccl_buffsize or (1024 if is_prefill else 4096)),
        "VLLM_USE_V2_MODEL_RUNNER": "1",
        "VLLM_ENGINE_READY_TIMEOUT_S": "36000",
        "PYTORCH_NPU_ALLOC_CONF": f"expandable_segments:{not args.no_expandable_segments}",
        "PYTHONUNBUFFERED": "1",
    })
    env["LD_LIBRARY_PATH"] = ":".join(filter(None, (env.get("LD_LIBRARY_PATH"), "/usr/local/lib")))
    if args.host_vmm_overlay is not None:
        loader = args.host_vmm_overlay.resolve() / "loader"
        if not (loader / "sitecustomize.py").is_file():
            raise SystemExit("Host VMM overlay is missing loader/sitecustomize.py")
        env["PYTHONPATH"] = os.pathsep.join(filter(None, (str(loader), env.get("PYTHONPATH"))))
    speculative = {"method": "dspark", "num_speculative_tokens": 5}
    if not is_prefill:
        speculative["enforce_eager"] = False
    common = [
        "vllm", "serve", str(args.model_path), "--host", args.local_ip,
        "--served-model-name", "dsv41", "--seed", "1024",
        "--data-parallel-size", str(dp_size), "--tensor-parallel-size", str(tp_size),
        "--prefill-context-parallel-size", str(pcp_size),
        "--data-parallel-address", args.local_ip, "--data-parallel-rpc-port", str(args.dp_rpc_port),
        "--enable-expert-parallel", "--max-model-len", "1048576", "--block-size", "128",
        "--trust-remote-code", "--tokenizer-mode", "deepseek_v41", "--reasoning-parser", "deepseek_v41",
        "--tool-call-parser", "deepseek_v41", "--enable-auto-tool-choice",
        "--safetensors-load-strategy", "lazy", "--quantization", "ascend",
        "--speculative-config", json.dumps(speculative),
        "--engram-config", json.dumps({"cpu_offload": True, "dp_shared_memory": True}),
        "--kv-transfer-config", json.dumps(transfer),
    ]
    additional = {"enable_cpu_binding": True}
    if is_prefill:
        env["HCCL_OP_EXPANSION_MODE"] = "AIV"
        role_flags = [
            "--max-num-batched-tokens", "8192", "--max-num-seqs", "16", "--gpu-memory-utilization", "0.90",
            "--enforce-eager", "--swa-bounded-replay", "--enable-prefix-caching",
        ]
        workers = args.tuning["prefill_renderer_workers"]
        if workers != 1:
            role_flags.extend(["--renderer-num-workers", str(workers)])
        additional.update(
            enable_fused_mc2=2,
            enable_flashcomm1=False,
            enable_shared_expert_dp=tp_size == 1,
            multistream_overlap_shared_expert=False,
        )
    else:
        compilation = {"cudagraph_mode": "FULL_DECODE_ONLY"}
        sizes = args.tuning["decode_graph_capture_sizes"]
        if sizes is not None:
            compilation["cudagraph_capture_sizes"] = sizes
        role_flags = [
            "--max-num-batched-tokens", "512", "--max-num-seqs", "72", "--gpu-memory-utilization", "0.95",
            "--async-scheduling", "--no-enable-prefix-caching", "--no-swa-bounded-replay",
            "--compilation-config", json.dumps(compilation),
        ]
        additional.update(
            ascend_compilation_config={"enable_npugraph_ex": True, "enable_static_kernel": False},
            enable_flashcomm1=False,
            multistream_overlap_shared_expert=True,
            recompute_scheduler_enable=True,
        )

    for rank in range(dp_size):
        port = args.api_base_port + rank
        devices_per_rank = pcp_size * tp_size
        devices = args.devices[rank * devices_per_rank:(rank + 1) * devices_per_rank]
        rank_env = dict(env, ASCEND_RT_VISIBLE_DEVICES=",".join(devices))
        command = common + role_flags + [
            "--additional-config", json.dumps(additional), "--data-parallel-rank", str(rank), "--port", str(port),
        ]
        yield rank, port, rank_env, command


def main():
    args = parse_args()
    specs = list(engine_specs(args))
    if args.dry_run:
        for rank, port, env, command in specs:
            print(json.dumps({
                "role": args.role, "rank": rank, "api_port": port,
                "device_count": len(env["ASCEND_RT_VISIBLE_DEVICES"].split(",")),
                "hccl_buffsize": int(env["HCCL_BUFFSIZE"]),
                "allocator": env["PYTORCH_NPU_ALLOC_CONF"],
                "argv": ["<ROLE_IP>" if x == args.local_ip else "<MODEL_PATH>" if x == str(args.model_path) else x
                         for x in command],
            }))
        return 0

    if not (args.model_path / "config.json").is_file():
        raise SystemExit("The checkpoint directory must contain config.json")
    args.log_dir.mkdir(parents=True, exist_ok=False)
    children = {}
    stopping = False

    def stop(_signum, _frame):
        nonlocal stopping
        stopping = True

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    try:
        for rank, port, env, command in specs:
            if stopping:
                break
            with (args.log_dir / f"rank-{rank:02d}.log").open("x") as log:
                child = subprocess.Popen(command, env=env, stdin=subprocess.DEVNULL,
                                         stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
            children[rank] = child
            print(f"started role={args.role} rank={rank} port={port} pid={child.pid}", flush=True)
        while not stopping:
            for rank, child in children.items():
                status = child.poll()
                if status is not None:
                    print(f"engine exited role={args.role} rank={rank} status={status}", flush=True)
                    return 1
            time.sleep(1)
        return 0
    finally:
        for child in children.values():
            try:
                os.killpg(child.pid, signal.SIGTERM)
            except ProcessLookupError:
                pass
        deadline = time.monotonic() + 45
        for child in children.values():
            try:
                child.wait(timeout=max(0, deadline - time.monotonic()))
            except subprocess.TimeoutExpired:
                try:
                    os.killpg(child.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                child.wait()


if __name__ == "__main__":
    raise SystemExit(main())
