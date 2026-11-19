# Increase Prefill renderer workers for cases 19 and 23

Use four renderer workers per P rank for CPU tokenization and input preparation. The repository already provides both launch profiles. The patch shows the one-field change between them.

## Apply

Run Prefill with the existing optimized profile and select the original profile independently for Decode. For the case 23 single-variable comparison, run P with graph78 for one worker and optimized for four, while the same graph78 D and Proxy continue serving. The [original A/B procedure](../../../docs/optimization.md#同机-ab-复现) uses this pair.

The diff can also be applied from the root of a separate launcher checkout.

```bash
git apply --check patches/shared/prefill-renderer/profile.patch
git apply patches/shared/prefill-renderer/profile.patch
```

## Archived A3 results

| Matched A/B | Throughput unit | 1 worker | 4 workers | Change |
|---|---|---:|---:|---:|
| Case 23, C216, fixed D and Proxy | Steady output tok/s per D card | 1,204.2 | 1,372.9 | +14.01% |
| Case 19, C24, RR=0, fixed D and Proxy | Input tok/s per P card | 68,256 | 68,189 | −0.10% |

Case 23 mean TTFT fell from 2.90 to 2.31 seconds. Case 19 mean TTFT was 5.440 and 5.439 seconds. The [case 23 pair](../../../results/ab/pair.json) and [case 19 trial records](../../../results/case19/trials.json) preserve the individual runs.
