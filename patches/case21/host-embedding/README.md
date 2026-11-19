# Move case 21 BF16 input embeddings to Host VMM

Use the existing [shared Engram Host VMM backport](../../README.md) to map the input embeddings of the target and DSpark draft models into host memory for TP1 Decode. Preserve the BF16 bytes. The installer verifies a sample of real lookup results before replacing the device weight and updates the worker's model-memory accounting before graph capture. Build and load the Host VMM backport first.

## Apply

Apply [the patch](vllm-ascend.patch) to the D-side vLLM-Ascend checkout at [24487f4](https://github.com/vllm-project/vllm-ascend/commit/24487f4f48ee99cf45d86d1c504e645549b8c1ef) from the 0.32.0rc1 experiment. Set CASE21_PATCH_REPO to the absolute path of this documentation repository and VLLM_ASCEND_SRC to the D-side engine checkout.

```bash
CASE21_PATCH_FILE="$CASE21_PATCH_REPO/patches/case21/host-embedding/vllm-ascend.patch"
git -C "$VLLM_ASCEND_SRC" apply --check "$CASE21_PATCH_FILE"
git -C "$VLLM_ASCEND_SRC" apply "$CASE21_PATCH_FILE"
```

See the [Apache 2.0 license](../../LICENSE).

## A3 evidence

Both input tables moved on all 16 D ranks. The load check compared four token IDs per table bit for bit, and the patched service completed the 128K/1K smoke. The measured release was 2,647,654,400 HBM bytes per D DIE (about 2.47 GiB). The available KV cache budget grew from about 12.79 to 15.26 GiB per DIE.

The pre-layout combination paired Host VMM embeddings with per-step MoE dispatch and active-row SwiGLU. With the same P and Proxy, two full C1152 trials per version each completed 4,608 requests with 131,072 input tokens and 1,024 output tokens. Steady output rose from 1,711.98 to 1,868.59 tok/s per D physical card (+9.15%), with mean TPOT moving from 27.15 to 28.44 ms. This is the combination's throughput. The isolated evidence for Host VMM embeddings is HBM reclaimed and lookup parity.
