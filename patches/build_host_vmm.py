"""Prepare and compile the Host VMM backport in a separate overlay."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile


ROOT = Path(__file__).resolve().parent
MANIFEST = json.loads((ROOT.parent / "results/manifest.json").read_text())
BASE_FILES = (
    "vllm_ascend/device/hardware_profile.py",
    "vllm_ascend/models/deepseek_v41/engram/embedding.py",
    "vllm_ascend/models/deepseek_v41/model.py",
    "vllm_ascend/worker/worker.py",
)
UPSTREAM_FILES = (
    "csrc/engram_vmm/native.cpp",
    "vllm_ascend/models/deepseek_v41/engram/local_shared_vmm.py",
    "vllm_ascend/models/deepseek_v41/engram/local_vmm_host.py",
)
UPSTREAM_SHA256 = (
    "486e4e23db6b8ba48abf32ec6d1fb2fbba1f032e4264232f365900ae5e4a8099",
    "a7d99119934bac8c99dbc581d2004a534fcfa45cbcc526ee8464889dafa20921",
    "133bf6b096e396d75f81e85ba3be5c1719f6859e8342e5ce384b55f27bc5d6bd",
)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--vllm-ascend-source", type=Path, required=True)
    parser.add_argument("--cann-home", type=Path, default=os.getenv("ASCEND_HOME_PATH"))
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.cann_home is None:
        parser.error("Supply --cann-home or ASCEND_HOME_PATH")
    if args.output.exists():
        parser.error("Use a new output directory")
    cann = args.cann_home.resolve()
    if not (cann / "include/acl/acl.h").is_file() or not (cann / "lib64/libascendcl.so").is_file():
        parser.error("The CANN installation must provide acl/acl.h and libascendcl.so")

    revisions = MANIFEST["revisions"]
    with tempfile.TemporaryDirectory(prefix="dsv41-host-vmm-") as work:
        overlay = Path(work) / "overlay"
        overlay.mkdir()

        def git_show(revision, name):
            return subprocess.check_output([
                "git", "-C", str(args.vllm_ascend_source), "show", f"{revision}:{name}",
            ])

        for name in BASE_FILES:
            destination = overlay / name
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(git_show(revisions["vllm_ascend"], name))
        subprocess.run(["git", "apply", str(ROOT / "host-vmm-0.32.patch")], cwd=overlay, check=True)

        for name, expected in zip(UPSTREAM_FILES, UPSTREAM_SHA256, strict=True):
            contents = git_show(revisions["host_vmm_upstream"], name)
            if hashlib.sha256(contents).hexdigest() != expected:
                raise ValueError(f"Unexpected source digest for {name}")
            destination = overlay / name
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(contents)
        library = overlay / "vllm_ascend/libengram_host_vmm.so"
        subprocess.run([
            "g++", "-std=c++17", "-O2", "-shared", "-fPIC", "-pthread",
            f"-I{cann / 'include'}", str(overlay / UPSTREAM_FILES[0]),
            f"-L{cann / 'lib64'}", f"-Wl,-rpath,{cann / 'lib64'}", "-lascendcl",
            "-o", str(library),
        ], check=True)
        import ctypes

        if ctypes.CDLL(str(library)).host_vmm_abi_version() != 2:
            raise RuntimeError("Unexpected Host VMM library ABI")
        (overlay / "loader").mkdir()
        shutil.copyfile(ROOT / "sitecustomize.py", overlay / "loader/sitecustomize.py")
        shutil.copytree(overlay, args.output)


if __name__ == "__main__":
    main()
