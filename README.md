# DeepSeek V4.1 Flash on Ascend A3

在同一 Ascend A3 SuperPod 的两台服务器上部署 DeepSeek-V4.1-Flash 1017 W4A8。1P1D 的 P 和 D 各用 8 张物理卡、16 DIE。三组实验用 AISBench 发压、用 InferRSI 复核吞吐，从端到端、Prefill 和 Decode 三个场景观察瓶颈。

## 三组优化总览

| 场景 | 吞吐指标（tok/s/物理卡） | 实测延迟门限 | 原表 | 正式基线 | 最终优化 | 相对基线 |
| --- | --- | --- | ---: | ---: | ---: | ---: |
| [23 · 端到端稳态](docs/overview.md#23--端到端稳态) | D 单卡稳态输出 | 平均 TPOT < 21 ms | 805.35 | 1,132.9 | **1,368.5** | **+20.80%** |
| [19 · 纯 P](docs/case19-pure-p.md) | P 单卡全程输入 | 平均 TTFT < 10 s | 58,583 | 68,239 | **105,397** | **+54.45%** |
| [21 · 纯 D 高吞吐](docs/case21-pure-d.md) | D 单卡稳态输出 | 平均 TPOT < 50 ms | 1,456.69 | 1,353.50 | **2,440.30** | **+80.30%** |

每组先在原表并发复测，再固定基线部署扫并发，选出延迟达标且吞吐最高的实测点。正式基线与最终点均取两轮中位数。编号 21 的两轮优化依次为 **1,353.50 → 1,870.71（+38.21%）→ 2,440.30（再 +30.45%）**。 [原表配置、同档复测及优化依据](docs/overview.md)

| 场景 | 实测瓶颈与主要改动 | 曲线 |
| --- | --- | --- |
| 23 | P 侧长输入分词供流慢，renderer 从 1 增至 4。D 增加 78 行解码图档。 | [优化前后 TPOT 曲线](results/tpot-throughput.png) |
| 19 | 多请求合批和专家负载均衡带来主要收益。P 批次从 8K 加到 32K，保留融合 MoE，开启 EPLB 和通信重叠。 | [TTFT 与输入吞吐](results/case19/ttft-throughput.svg) |
| 21 | D 先受 KV 容量限制，后受批次预算限制。P 增加 renderer，D 复用前缀 KV、扩大批次，最后调整发压节奏。 | [第一轮](results/case21/round1.svg) · [第二轮](results/case21/round2.svg) |

## 测试代码和数据

- [测试和复现步骤](docs/benchmark.md)包含 A3 环境、P/D/Proxy 启动、GSM8K 负载构造、预热和稳态计算。
- [部署脚本](deploy/)读取[共用基线](configs/baseline.json)、[编号 23 优化版](configs/optimized.json)与 [编号 21 第一轮](configs/case21-round1.json)、[第二轮](configs/case21-round2.json)配置。[Host VMM 回移](patches/)为共用启动条件。
- [压测代码](bench/)包含 AISBench 驱动、逐请求审计、InferRSI 配对适配器及绘图脚本。
- [数据说明](results/README.md)索引三组的逐轮结果和逐请求时间线。编号 23 的 [A/B 与启动配置](docs/optimization.md)、编号 19 的 [P 侧配置](docs/case19-pure-p.md#优化与同负载对照)和编号 21 的 [D 侧配置与发压命令](docs/case21-pure-d.md#复现)见各自报告。

用 Python 3.11 或更新版本在仓库根目录离线核对三组结果。编号 23 的回算可加 `--plot` 重画曲线，需要 matplotlib。

```bash
python3 bench/report.py
python3 bench/report_case19.py
python3 bench/report_case21.py
```
