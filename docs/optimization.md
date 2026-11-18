# 优化结果与改动

| 配置 | D 图捕获尺寸 | P renderer workers / rank | 用途 |
| --- | --- | ---: | --- |
| [baseline](../configs/baseline.json) | 0.32.0rc1 默认 | 1 | 12 个并发点的原基线 |
| [graph78](../configs/graph78.json) | 显式列表加入 78 | 1 | 固定 D 的同机 A/B 对照 |
| [optimized](../configs/optimized.json) | 同 graph78 | 4 | 最终配置 |

D 侧继续使用 `FULL_DECODE_ONLY`，以显式的 `cudagraph_capture_sizes` 包含捕获尺寸 78。P 侧在四个 rank 上增加 `--renderer-num-workers 4`，提高长输入预处理并行度。两个参数均由[同一份 P/D 启动代码](../deploy/launch_node.py)加载。DSpark 草拟长度为 5。Host VMM 回移是基线和最终配置共用的启动条件。[共享回移和来源](../patches/README.md)

在并发 248 的诊断轮中，P 侧前缀 token 命中率约为 99.903%，引擎内 prefill 平均约 0.23 秒，客户端稳态平均 TTFT 约 5.52 秒。随后在并发 216、同一 D 和 Proxy 上，只切换 P 的 renderer worker 数。两组的 P 前缀命中率相同，平均 TTFT 从 2.90 秒降到 2.31 秒。[并发 248 诊断计数](../results/ab/prefill-diagnostic.json) · [同机 A/B 的样本绑定](../results/ab/pair.json)

| 并发 216 的比较 | 对照（tok/s/卡） | 候选（tok/s/卡） | 提升 |
| --- | ---: | ---: | ---: |
| 原始曲线的基线峰值与最终配置峰值 | 1,132.9 | 1,368.5 | 20.80% |
| 固定 D 和 Proxy 的 P worker A/B | 1,204.2 | 1,372.9 | 14.01% |

第一行是完整配置的对比，比较各侧两轮的中位数。第二行是单因素 A/B，InferRSI 复用了同一个 D 和 Proxy 进程上的 A 样本。最终 C216 的两轮输出分别为 1,372.9、1,364.2 tok/s/卡，平均 TPOT 分别为 19.90、19.86 ms。优化版 C248 也保留在曲线中，该轮平均 TPOT 为 21.09 ms。[可复算的比较](../results/comparison.json) · [优化版逐轮记录](../results/optimized/trials.json)

## 同机 A/B 复现

1. 用 `graph78` 启动 P/D 和 Proxy，执行[并发 216 的稳态测试](benchmark.md#执行-aisbench)，将 A 结果写到 `local-runs/ab-a/result.json`。
2. 保持 D 和 Proxy 进程在线。停止 P 启动进程，用 `optimized` 在同一组 API 端口启动 P，指定新日志目录。
3. 在客户端使用 [InferRSI 61303fa](https://github.com/InferMatrixLab/InferRSI/commit/61303fa8150472dfbda62ec8d77908bc05c73f3b) 运行[配对适配器](../bench/inferrsi_pair.py)。适配器核对 A 的工作负载和并发，读取留存的 A 样本，在线执行 B。

```bash
python3 -m pip install \
  'inferrsi @ git+https://github.com/InferMatrixLab/InferRSI.git@61303fa8150472dfbda62ec8d77908bc05c73f3b'
python3 bench/inferrsi_pair.py \
  --a-result local-runs/ab-a/result.json \
  --dataset datasets/gsm8k/steady.jsonl --tokenizer "$TOKENIZER_PATH" \
  --output local-runs/ab
```

配对适配器输出两侧的吞吐和检查结果。InferRSI 的质量验收需要对应的长上下文正确性验证，使用这个性能适配器时验收状态为 INCONCLUSIVE。

此处的启动和压测脚本由原运行脚本适配，节点及文件位置由运行时填入。仓库内的结果取自当时在 A3 上完成的历史测量，离线脚本可从逐请求数据重算这些结果。
