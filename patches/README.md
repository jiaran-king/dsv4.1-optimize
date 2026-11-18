# Shared Engram Host VMM backport

The 0.32.0rc1 experiment used a backport of the Host VMM implementation from vLLM-Ascend [PR #21623 at dab8705](https://github.com/vllm-project/vllm-ascend/commit/dab870524ae2bc713ba51deae811488cadbe75e3). The four-file [adaptation diff](host-vmm-0.32.patch) applies to vLLM-Ascend [24487f4](https://github.com/vllm-project/vllm-ascend/commit/24487f4f48ee99cf45d86d1c504e645549b8c1ef). Both the baseline and optimized deployments use this backport. Upstream source and the backport diff retain the [Apache 2.0 license](LICENSE).

Build inside the A3 runtime using a vLLM-Ascend Git checkout with both recorded revisions present. Use the same base revisions for the serving environment. Set `VLLM_ASCEND_SRC` to the checkout and `ASCEND_HOME_PATH` to the CANN toolkit.

```bash
git -C "$VLLM_ASCEND_SRC" fetch origin dab870524ae2bc713ba51deae811488cadbe75e3
python3 patches/build_host_vmm.py \
  --vllm-ascend-source "$VLLM_ASCEND_SRC" \
  --output build/host-vmm
export PD_HOST_VMM_OVERLAY="$PWD/build/host-vmm"
```

The builder applies the adaptation to the pinned base files, reads the three native and Python sources from the pinned upstream commit, compiles the library and checks ABI 2. The loader resolves the six backport modules from the overlay.
