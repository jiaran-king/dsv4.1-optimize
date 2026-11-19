# Overlap Engram lookup with Prefill work in case 19

Enable multistream_engram_overlap in the P-side additional configuration. The pinned engine already implements scheduling of Engram hashing, table lookup and communication on an auxiliary stream.

## Apply

Use the case 19 32K MegaMoE setup and the [shared Engram Host VMM backport](../../README.md). Apply the launcher patch on the P launcher checkout.

Run the applicable commands from the root of a separate launcher checkout.

```bash
git apply --check patches/case19/engram-overlap/launcher.patch
git apply patches/case19/engram-overlap/launcher.patch
```

## Archived A3 results

At C42 and RR=0, adding this option to the 32K MegaMoE configuration moved P input throughput from 75,503 to 76,698 tok/s per P card (+1.58%). Mean TTFT moved from 8.179 to 8.133 seconds. These are single-run comparisons on the same case 19 workload. See [case 19 trials](../../../results/case19/trials.json).
