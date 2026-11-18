# 编号 21 · 纯 D 高吞吐

128K 单前缀、1K 输出下，D 单卡稳态输出从正式基线的 **1,353.50** 增至第一轮的 **1,870.71**，再到第二轮的 **2,440.30 tok/s/卡**。两步增幅分别为 **38.21%** 和 **30.45%**，累计 **80.30%**。延迟门限是每一轮**稳态平均 TPOT < 50 ms**，同时记录 P90 和 TTFT。 [实测汇总](../results/case21/comparison.json)

## 负载和部署

原表与正式复测每轮均发 4,608 条，单条 131,072 输入 token、1,024 输出 token，100% 单前缀。原表发压并发上限 1,152，发压速率设 0。实测使用编号 23 的 GSM8K 重构 prompt，P 实际前缀 token 命中率约 99.90%。P、D 各 8 张物理卡，经原 Proxy 发压，保持共享 Engram、DSpark 5、1M 上下文和 0.32.0rc1 默认解码图档。 [公共部署参数](benchmark.md#软件和部署)

| 设置 | 基线 | 第一轮 | 第二轮 |
| --- | --- | --- | --- |
| 启动配置 | [baseline](../configs/baseline.json) | [case21-round1](../configs/case21-round1.json) | [case21-round2](../configs/case21-round2.json) |
| P 每 rank renderer 数 | 1 | 4 | 4 |
| P 批次预算 | 8192 | 8192 | 8192 |
| D 本地前缀缓存 / SWA bounded replay | 关 / 关 | 开 / 开 | 开 / 开 |
| D 重算调度器 | 开 | 关 | 关 |
| D 批次预算 | 512 | 512 | 768 |
| 最终点客户端并发上限 | 384 | 512 | 1,280 |
| 最终点发压速率 | 不限 | 不限 | 26 req/s |

编号 21 的基线按原 P 启动参数重测，P 与 D 的 EPLB 均关闭。P 保留默认的 8192 token 调度预算，D 设备内存比例为 0.95，最大序列数 72。

## 原表与正式基线

| 阶段 | D 单卡稳态输出（tok/s） | 平均 TPOT（ms） | TPOT P90（ms） | 平均 TTFT（s） |
| --- | ---: | ---: | ---: | ---: |
| 原表，C1152 | 1,456.69 | 30.80 | 35.20 | 66.29 |
| 同档复测首轮，C1152 | 1,439.60 | 22.67 | 26.08 | 80.15 |
| 正式基线，C384 | 1,353.50 | 23.11 | 26.26 | 12.01 |
| 第一轮，C512 | 1,870.71 | 30.45 | 34.39 | 2.71 |
| 第二轮，C1280 / 26 req/s | **2,440.30** | **44.20** | 51.11 | 19.88 |

C1152 首轮 D 实际运行并发平均 272、峰值 304。原部署后续复测 C1152 的吞吐中位数为 1,236.23。固定原 P/D、Proxy、语料和生成参数扫描并发后，C384 两轮 **1,270.41 / 1,436.59 tok/s/卡**，中位数是确认轮中达标吞吐最高的点。 [基线与第一轮曲线](../results/case21/round1.svg) · [逐轮数据](../results/case21/trials.json)

## 第一轮 · 供流和 KV 复用

1. **P renderer 从 1 调到 4。** 保持 D 和 Proxy 进程，使用同样的 4,608 条、C384、RR=0。候选轮的 D 单卡稳态输出为 **1,652.72 tok/s**，比正式基线中位数高 **22.11%**。平均 TTFT 从 12.01 s 降至 2.40 s。
2. **D 开本地前缀缓存和 SWA bounded replay。** 只增加 renderer 后，C512 的 D KV 使用峰值为 99.84%，实际运行峰值 384 条，平均等待约 108 条。D 复用收到的全局前缀 KV，再接收请求末尾所需的窗口数据，减少重复存储。关闭与 bounded replay 冲突的重算调度器。同样 C512、RR=0、1,536 条的 A/B，KV 峰值降至 **8.10%**，实际运行峰值升到 **511 条**，单卡吞吐 **1,708.07 → 1,890.52（+10.68%）**。
3. **在 C512 正式确认。** 两轮各发 4,608 条，稳态分别计入 4,088 / 4,086 条。D 单卡输出分别为 **1,875.20 / 1,866.21 tok/s**，中位数较正式基线 **+38.21%**。 [逐请求证据](../results/case21/requests.csv.gz)

## 第二轮 · D 调度预算与发压节奏

提高客户端并发到 1,024 后，D 有大量请求在等，实际运行峰值固定在 **816 条**，KV 峰值约 **10.76%**。这版 DSpark 5 每条运行请求占 6 个验证 slot 和 4 个草稿 slot，因此每 rank 的预算 512 只能容纳 51 条，16 个 rank 合计 816 条。

把 D 批次预算从 **512 调到 768**，保留相同的 P 和 Proxy。相同 C1024、RR=0、3,072 条的 A/B，D 运行峰值 **816 → 1,003**，平均等待 **137.34 → 10.34 条**，单卡稳态输出 **2,101.99 → 2,173.92 tok/s**。在新预算上继续扫并发和速率，最终选 C1280、26 req/s。

| C1280 / 26 req/s 正式复测 | 第一轮样本 | 第二轮样本 | 中位数 |
| --- | ---: | ---: | ---: |
| 稳态计入请求数 | 2,437 | 2,333 | |
| D 单卡稳态输出（tok/s） | 2,485.59 | 2,395.01 | **2,440.30** |
| 平均 TPOT（ms） | 45.35 | 43.05 | **44.20** |

本轮相对上一阶段的 30% 门槛为 **2,431.92 tok/s/卡**。中位数高出门槛 **8.38 tok/s/卡**，两个样本中有一个低于吞吐目标。稳态吞吐增加 **30.45%**，全程吞吐增加 **22.29%**。稳态平均 TTFT 同时从 **2.71 s 升到 19.88 s**。 [第二轮 TPOT 与吞吐曲线](../results/case21/round2.svg) · [逐轮与逐请求记录](../results/README.md#编号-21--纯-d)

## 复现

先按[共用启动步骤](benchmark.md#启动-pd-和-proxy)准备模型、Host VMM overlay、P/D 环境及原版 Proxy。基线两端使用 `--profile baseline`，第一轮两端使用 `--profile case21-round1`。第二轮 P 启动参数与第一轮相同，D 改用 `--profile case21-round2`。新启动前可用 `--dry-run` 查看发送给各 rank 的参数。

用[负载生成步骤](benchmark.md#构造负载)准备 `steady.jsonl` 后，取其中第一条写出 Case 21 的 4,608 条同前缀请求。该文件会重复保存完整的 128K prompt。

```bash
python3 - datasets/gsm8k/steady.jsonl datasets/gsm8k/case21.jsonl <<'PY'
from pathlib import Path
import sys

with Path(sys.argv[1]).open("rb") as source:
    prompt_row = source.readline()
if not prompt_row.endswith(b"\n"):
    raise SystemExit("Expected a full first JSONL row")
with Path(sys.argv[2]).open("xb") as output:
    for _ in range(4608):
        output.write(prompt_row)
PY
```

在 AISBench 客户端设置 `TOKENIZER_PATH`、`PD_PROXY_HOST` 和 `PD_P_HOST`。先用基线服务跑原表点和基线确认点。重跑同一点时使用新的输出目录。

```bash
for concurrency in 1152 384; do
  python3 bench/run_case.py case21 --dataset datasets/gsm8k/case21.jsonl \
    --tokenizer "$TOKENIZER_PATH" --concurrency "$concurrency" \
    --output "local-runs/case21-c${concurrency}"
done
```

切换到第一轮 P/D 配置后发压。

```bash
python3 bench/run_case.py case21 --dataset datasets/gsm8k/case21.jsonl \
  --tokenizer "$TOKENIZER_PATH" --concurrency 512 --output local-runs/case21-round1
```

P 继续供流，D 切换到第二轮配置后发压。

```bash
python3 bench/run_case.py case21 --dataset datasets/gsm8k/case21.jsonl \
  --tokenizer "$TOKENIZER_PATH" --concurrency 1280 --request-rate 26 \
  --output local-runs/case21-c1280-rr26
```

可在本地运行 `python3 bench/report_case21.py`，从归档时间线校验全程与稳态数据以及两轮正式增益。
