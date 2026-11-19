# Size case 21 MoE dispatch by the synchronized DP batch

Use the existing DP token-count synchronization for DeepSeek V4.1 Decode with expert parallelism, DP > 1, and TP1. The synchronized per-step shape and MC2 active-token mask let the runtime size dispatch and combine buffers for the running batch. The patch changes the DP-sync predicate in vllm_ascend/utils.py.

## Apply

Apply [the patch](vllm-ascend.patch) to the D-side vLLM-Ascend checkout at [24487f4](https://github.com/vllm-project/vllm-ascend/commit/24487f4f48ee99cf45d86d1c504e645549b8c1ef) from the 0.32.0rc1 experiment. Set CASE21_PATCH_REPO to the absolute path of this documentation repository and VLLM_ASCEND_SRC to the D-side engine checkout.

```bash
CASE21_PATCH_FILE="$CASE21_PATCH_REPO/patches/case21/moe-dispatch/vllm-ascend.patch"
git -C "$VLLM_ASCEND_SRC" apply --check "$CASE21_PATCH_FILE"
git -C "$VLLM_ASCEND_SRC" apply "$CASE21_PATCH_FILE"
```

See the [Apache 2.0 license](../../LICENSE).

## A3 evidence

| Capture on A3 | Original buffer rows | Per-step dispatch buffer rows |
|---|---:|---:|
| Main model | 41,472 | 13,824 |
| DSpark draft | 20,736 | 5,760 |

The C768 diagnostic used 1,536 requests with 131,072 input tokens and 1,024 output tokens, with rank-zero profiling. The draft-SwiGLU prototype measured 1,778.63 tok/s per D physical card. The variant with per-step dispatch measured 1,837.14 tok/s per D physical card. The 5,760-row shape also caused the earlier draft-SwiGLU prototype to select its original activation path, so this comparison includes that change in executed work. An isolated C1152 service uplift for the dispatch predicate is unmeasured.
