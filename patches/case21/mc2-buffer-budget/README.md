# Bound case 21 A3 MC2 dispatch and graph capture by the HCCL window

Size the A3 Decode MC2 token limit from the HCCL communication window. Keep FULL_DECODE_ONLY graph captures within that limit. Larger batches go through the existing eager AllToAll path. This change lets the case reclaim device memory for KV by selecting a smaller buffer.

## Apply

Apply the patch to the D vLLM-Ascend checkout at [24487f4](https://github.com/vllm-project/vllm-ascend/commit/24487f4f48ee99cf45d86d1c504e645549b8c1ef). The measured comparison uses the compact KV stack described in [the preceding patch](https://github.com/jiaran-king/dsv4.1-optimize/tree/codex/case21-compact-kv/patches/case21/compact-kv). Launch D with the original launch settings and use the existing --hccl-buffsize 2368 option. The measured deployment has DSpark 5, TP1, DP16, EP16, and D local prefix caching disabled. Set CASE21_PATCH_REPO and VLLM_ASCEND_SRC to the two checkout paths.

```bash
CASE21_PATCH_DIR="$CASE21_PATCH_REPO/patches/case21/mc2-buffer-budget"
git -C "$VLLM_ASCEND_SRC" apply --check "$CASE21_PATCH_DIR/vllm-ascend.patch"
git -C "$VLLM_ASCEND_SRC" apply "$CASE21_PATCH_DIR/vllm-ascend.patch"
```

Build or import the patched sources on Decode. See the [Apache 2.0 license](../../LICENSE).

## Design sources

The capacity calculation uses the [CANN A3 DispatchV2/CombineV2 window contract](https://www.hiascend.com/document/detail/zh/CANNCommunityEdition/850/API/aolapi/context/ops-transformer/aclnnMoeDistributeCombineV2.md). The A3 trial used a 2,368 MiB communication buffer and reduced the highest captured graph from 432 to 288 token rows. A wide-batch run exercised the eager path above the capture range.

## Archived A3 evidence

On the compact KV baseline, the buffer change increased available KV memory from 15.26 to 18.82 GiB per D DIE. At C1152 and RR=0, the two-round steady median increased from 2,144.23 to 2,232.20 tok/s per D card (+4.10%). The two mean TPOT medians were 32.51 and 37.78 ms. Each round completed 4,608 128K/1K requests.
