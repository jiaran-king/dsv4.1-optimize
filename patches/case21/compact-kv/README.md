# Pack Decode history KV and bounded state separately in case 21

Use smaller pages for historical KV and sparse indices. Allocate sliding-window and compressor state from a bounded short pool. The companion vLLM patch keeps block zeroing aligned with pool ownership. Mooncake reads the original Prefill page stride and writes the compact Decode layout.

## Apply

Apply both patches to the D checkouts at [vLLM 5df63a7](https://github.com/vllm-project/vllm/commit/5df63a7203cdb9328d824a27b682e77c7b9928be) and [vLLM-Ascend 24487f4](https://github.com/vllm-project/vllm-ascend/commit/24487f4f48ee99cf45d86d1c504e645549b8c1ef). The archived C1152 comparison builds on [per-step MoE dispatch](https://github.com/jiaran-king/dsv4.1-optimize/pull/1), [active-row SwiGLU](https://github.com/jiaran-king/dsv4.1-optimize/pull/2), and [Host VMM input embeddings](https://github.com/jiaran-king/dsv4.1-optimize/pull/3), together with the [shared Host VMM backport](../../README.md). The layout is scoped to the MooncakeHybridConnector consumer and TP1, with D prefix caching and bounded replay disabled. P keeps the original layout. Set CASE21_PATCH_REPO, CASE21_VLLM_SRC, and VLLM_ASCEND_SRC to the three checkout paths.

```bash
CASE21_PATCH_DIR="$CASE21_PATCH_REPO/patches/case21/compact-kv"
git -C "$CASE21_VLLM_SRC" apply --check "$CASE21_PATCH_DIR/vllm-core.patch"
git -C "$CASE21_VLLM_SRC" apply "$CASE21_PATCH_DIR/vllm-core.patch"
git -C "$VLLM_ASCEND_SRC" apply --check "$CASE21_PATCH_DIR/vllm-ascend.patch"
git -C "$VLLM_ASCEND_SRC" apply "$CASE21_PATCH_DIR/vllm-ascend.patch"
```

Build or import the patched sources on Decode. See the [Apache 2.0 license](../../LICENSE).

## Design sources

The direct community precedent is [vLLM-Ascend RFC #21324](https://github.com/vllm-project/vllm-ascend/issues/21324), implemented upstream in [PR #22398](https://github.com/vllm-project/vllm-ascend/pull/22398). This case is an independent implementation of that direction on 0.32.0rc1. It uses two block pools, keeps P's PCP4 and DSpark 5, and adapts the original hybrid connector on D. The upstream PR has separate history, SWA, and compressor pools and a different P/D handoff contract.

## Archived A3 evidence

At the same 15.26 GiB KV budget per D DIE, the history stride per block ID decreased from 540,928 to 369,280 bytes. All 16 D ranks provisioned about 39.5K long blocks. Address, zeroing, and deferred-free checks covered the two pools. At C1152 and RR=0, two rounds per arm each completed 4,608 128K/1K requests. The D steady output median rose from 1,868.59 to 2,144.23 tok/s per physical card (+14.75%). Full-window throughput rose 14.70%, and mean TPOT moved from 28.44 to 32.51 ms. The D prefix-cache hit and query increments were zero.
