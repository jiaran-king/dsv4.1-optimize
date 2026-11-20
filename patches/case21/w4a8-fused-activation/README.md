# Defer shared expert activation behind case 21 fused W4A8 routing

Use fused dispatch/FFN/combine for the supported W4A8 target path. Let shared gate/up projections overlap routed experts, and submit shared vector activation after the routed kernel's event. The measured revision checks for SiLU because the fused operator executes SwiGLU. Other activations use the existing implementation.

## Apply

Apply on the D vLLM-Ascend checkout at [24487f4](https://github.com/vllm-project/vllm-ascend/commit/24487f4f48ee99cf45d86d1c504e645549b8c1ef). The comparison holds the compact KV code and [the 2,368 MiB MC2 buffer and graph cap](https://github.com/jiaran-king/dsv4.1-optimize/tree/codex/case21-mc2-buffer-budget/patches/case21/mc2-buffer-budget) fixed. The fused path uses the uniform DP shape and MC2 token mask already provided by [per-step MoE dispatch](https://github.com/jiaran-king/dsv4.1-optimize/pull/1). Set CASE21_PATCH_REPO and VLLM_ASCEND_SRC to the two checkout paths.

```bash
CASE21_PATCH_DIR="$CASE21_PATCH_REPO/patches/case21/w4a8-fused-activation"
git -C "$VLLM_ASCEND_SRC" apply --check "$CASE21_PATCH_DIR/vllm-ascend.patch"
git -C "$VLLM_ASCEND_SRC" apply "$CASE21_PATCH_DIR/vllm-ascend.patch"
```

Build or import the patched sources on Decode. See the [Apache 2.0 license](../../LICENSE).

## Design sources

The ordering came from the A3 timeline, where simultaneous fused routing and shared-expert activation contended for vector execution. A CPU dispatch check kept SiLU on the fused path and sent SiTU through the original implementation. The later quality audit compared original and guarded D under fixed P and Proxy, including 192 paired long-context questions with identical numeric answers.

## Archived A3 evidence

The 4,608-request C1152 run of the merged configuration with the SiLU guard measured 2,330.28 tok/s per D card at 35.41 ms mean TPOT. That is +4.39% against the two-run buffer-only median of 2,232.20, and +8.68% against the compact KV baseline. The guarded run is a single timed follow-up. The two earlier performance confirmation rounds before the activation guard had a median of 2,344.55 tok/s per D card (+5.03% against buffer-only). The full quality audit recorded 1,269/1,319 GSM8K short questions and 189/192 long-context questions on the guarded version.
