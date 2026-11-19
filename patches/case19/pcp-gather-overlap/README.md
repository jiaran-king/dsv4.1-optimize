# Overlap PCP hidden-state all-gather with Q projection in case 19

Backport the two production modules of [vLLM-Ascend PR #21628](https://github.com/vllm-project/vllm-ascend/pull/21628). Start the hidden-state all-gather asynchronously, execute the local Q_a projection while it runs, and wait before consuming the gathered hidden state.

## Apply

Apply the engine patch on the P checkout with the case 19 32K MegaMoE and Engram-overlap setup. The two patched modules match the archived A3 source digests. Set VLLM_ASCEND_SRC to the vLLM-Ascend checkout at [24487f4](https://github.com/vllm-project/vllm-ascend/commit/24487f4f48ee99cf45d86d1c504e645549b8c1ef). Engine patches retain the [Apache 2.0 license](../../LICENSE).

Run the applicable commands from the root of a separate launcher checkout.

```bash
CASE_PATCH_FILE="$PWD/patches/case19/pcp-gather-overlap/vllm-ascend.patch"
git -C "$VLLM_ASCEND_SRC" apply --check "$CASE_PATCH_FILE"
git -C "$VLLM_ASCEND_SRC" apply "$CASE_PATCH_FILE"
```

## Archived A3 results

At C42 and RR=0, adding the backport moved P input throughput from 76,698 to 76,928 tok/s per P card (+0.30%). At C52 and RR=0, the single-run readings were 76,713 and 75,812 tok/s per P card (−1.17%). The archived A3 check reported 42 upstream unit tests passing. See [case 19 trials](../../../results/case19/trials.json).
