# Capture the 78-row Decode graph in case 23

Capture an additional 78-query-row shape in FULL_DECODE_ONLY mode while keeping the original capture list and ceiling. At DSpark width 5, a uniform 13-request decode batch uses 13 × 6 = 78 query rows. An exact graph at that size reduces graph padding.

## Apply

Run D with the existing graph78 profile and P with the one-worker baseline profile for this comparison. The reviewed profile delta contains the capture list used in the archived A3 run.

The diff can also be applied from the root of a separate launcher checkout.

```bash
git apply --check patches/case23/decode-graph78/profile.patch
git apply patches/case23/decode-graph78/profile.patch
```

## Archived A3 results

At C248 (576 requests, 128K/1K, RR=0), the original point was 1,108.2 tok/s per D physical card at 19.23 ms mean TPOT. The two graph78 runs measured 1,162.8 and 1,133.3 tok/s per D card, with a median of 1,148.1 (+3.59% at C248) and 17.63 ms mean TPOT. Against the best point on the original curve, the gain was +1.34%. The C216 graph-only result varied on repeat, from 1,204.2 to 1,049.0 tok/s per D card. Both C216 measurements selected 360 steady requests. See the [case 23 comparison](../../../docs/optimization.md) for the later renderer A/B.
