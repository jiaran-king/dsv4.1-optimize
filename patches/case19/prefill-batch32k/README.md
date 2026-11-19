# Enable the 32K Prefill batch budget in case 19

Set the P scheduler budget to 32,768 tokens and retain MegaMoE with PCP4. The archived engine patch caps the attention-free startup profiling batch at the rank's 16,384-token capacity, then restores the scheduler budget. The actual request path continues to use the existing PCP partitioning and capacity checks.

## Apply

Apply the engine patch on the P checkout first. Use a launcher checkout with the repository renderer setting for four workers on P and the baseline profile on D. The 32K patch keeps the P rank's max_num_seqs at 16 and the original HBM target. Set VLLM_ASCEND_SRC to the vLLM-Ascend checkout at [24487f4](https://github.com/vllm-project/vllm-ascend/commit/24487f4f48ee99cf45d86d1c504e645549b8c1ef). Engine patches retain the [Apache 2.0 license](../../LICENSE).

Run the applicable commands from the root of a separate launcher checkout.

```bash
git apply --check patches/case19/prefill-batch32k/launcher.patch
git apply patches/case19/prefill-batch32k/launcher.patch
CASE_PATCH_FILE="$PWD/patches/case19/prefill-batch32k/vllm-ascend.patch"
git -C "$VLLM_ASCEND_SRC" apply --check "$CASE_PATCH_FILE"
git -C "$VLLM_ASCEND_SRC" apply "$CASE_PATCH_FILE"
```

## Archived A3 results

At C42 and RR=0, the 16K MegaMoE case measured 74,291 tok/s per P card and 8.257 s mean TTFT. The 32K MegaMoE case measured 75,503 tok/s per P card (+1.63%) and 8.179 s mean TTFT. These are individual runs. All 16 P workers exercised the startup path in the archived A3 run. That run retained the 1,048,576-token context limit, reported 10.95 GiB of KV cache, and completed the 128K smoke and full workload. See [case 19 trials](../../../results/case19/trials.json).
