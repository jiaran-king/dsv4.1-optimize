# Run case 21 draft SwiGLU only on active expert rows

Fuse clipping and SwiGLU for the draft MoE's contiguous BF16 activation on Ascend. The Triton kernel reads expert-group counts, then computes and writes the valid row prefix. Grouped matmul and expert combine consume those rows. The packaged guard uses the 5,760-row threshold tested with per-step dispatch.

## Apply

Apply [the patch](vllm-ascend.patch) to the D-side vLLM-Ascend checkout at [24487f4](https://github.com/vllm-project/vllm-ascend/commit/24487f4f48ee99cf45d86d1c504e645549b8c1ef) from the 0.32.0rc1 experiment. Set CASE21_PATCH_REPO to the absolute path of this documentation repository and VLLM_ASCEND_SRC to the D-side engine checkout.

```bash
CASE21_PATCH_FILE="$CASE21_PATCH_REPO/patches/case21/ragged-swiglu/vllm-ascend.patch"
git -C "$VLLM_ASCEND_SRC" apply --check "$CASE21_PATCH_FILE"
git -C "$VLLM_ASCEND_SRC" apply "$CASE21_PATCH_FILE"
```

See the [Apache 2.0 license](../../LICENSE).

## A3 evidence

| A3 BF16 operator check | Active rows | Original | Fused |
|---|---:|---:|---:|
| 20,736-row buffer | 864 | 2.12 ms | 0.056 ms |
| 5,760-row buffer | 864 | 546.74 µs | 49.40 µs |

Both operator checks matched the original output bit for bit on the active rows. The standalone draft-SwiGLU prototype at C768 used the earlier 8,192-row guard and rank-zero profiling. On 1,536 requests with 131,072 input tokens and 1,024 output tokens, steady output rose from 1,640.16 to 1,778.63 tok/s per D physical card (+8.44%) and mean TPOT moved from 26.47 to 24.63 ms. The 5,760-row guard was verified at the reduced dispatch shape and in the pre-layout service combination.
