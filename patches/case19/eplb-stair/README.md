# Enable asynchronous STAIR expert balancing in case 19

Enable the pinned engine's EPLB with STAIR, an expert-load window of 32, a step interval of 40, and 16 redundant experts. The recorded A3 deployment used asynchronous HIXL transfers and the default heat-collection stage.

## Apply

Apply the launcher patch on P with the case 19 32K MegaMoE, Engram overlap and PCP overlap setup. After startup, run two calibration rounds, each with 168 requests, C42 and RR=0. Use a separate GSM8K-derived set with the same token lengths and prefix profile. Reuse the warmed service for the scored dataset. The archived calibration reused zero evaluation prompts. Follow the [benchmark guide](../../../docs/benchmark.md) for request format and generation settings.

Run the applicable commands from the root of a separate launcher checkout.

```bash
git apply --check patches/case19/eplb-stair/launcher.patch
git apply patches/case19/eplb-stair/launcher.patch
```

## Archived A3 results

At C42 and RR=0, the one-run matched comparison measured **76,928 → 102,756 tok/s per P card (+33.58%)**. Mean TTFT moved from 8.114 to 5.942 seconds. The baseline for this comparison already had the other P changes and ran the same 168-request test. See [case 19 trials](../../../results/case19/trials.json) and the [calibration summary](../../../results/case19/comparison.json).
