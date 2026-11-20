# DeepSeek V4.1 Flash on Ascend A3

在同一 Ascend A3 SuperPod 的两台服务器上部署 DeepSeek-V4.1-Flash 1017 W4A8。1P1D 的 P 和 D 各用 8 张物理卡、16 DIE。三组实验用 AISBench 发压、用 InferRSI 复核吞吐，从端到端、Prefill 和 Decode 三个场景观察瓶颈。

三组的取舍来自供流、合批、缓存和设备时间线的实测。我们用同负载 A/B 验证单项收益，再按同一延迟门限比较最终吞吐。 [优化选择原则](docs/overview.md#优化选择原则)

## 三组优化总览

| 场景 | 吞吐指标（tok/s/物理卡） | 实测延迟门限 | 原表 | 正式基线 | 最终优化 | 相对基线 |
| --- | --- | --- | ---: | ---: | ---: | ---: |
| [23 · 端到端稳态](docs/overview.md#23--端到端稳态) | D 单卡稳态输出 | 平均 TPOT < 21 ms | 805.35 | 1,132.9 | **1,368.5** | **+20.80%** |
| [19 · 纯 P](docs/case19-pure-p.md) | P 单卡全程输入 | 平均 TTFT < 10 s | 58,583 | 68,239 | **105,397** | **+54.45%** |
| [21 · 纯 D，C1152 同负载](docs/case21-c1152.md) | D 单卡稳态输出 | 平均 TPOT < 50 ms | 1,456.69 | 1,711.98 | **2,330.28** | **+36.12%** |

编号 19 和 23 的正式点取两轮中位数。编号 21 固定 C1152、RR=0、P renderer=4 和关闭 D 本地前缀缓存来比较 D 的改动。相对紧凑 KV 版，两轮性能确认中位数为 **2,344.55（+9.34%）**，加 SiLU 保护后的一轮复测为 **2,330.28（+8.68%）**。上表采用带保护的保留版结果。此前启用 D 前缀复用并调整发压的 **2,440.30** 仍可在历史报告核对。 [本轮逐阶段对照](docs/case21-c1152.md) · [历史配置与结果](docs/case21-pure-d.md)

| 场景 | 实测瓶颈与主要改动 | 曲线 |
| --- | --- | --- |
| 23 | P 侧长输入分词供流慢，renderer 从 1 增至 4。D 增加 78 行解码图档。 | [优化前后 TPOT 曲线](results/tpot-throughput.png) |
| 19 | 多请求合批和专家负载均衡带来主要收益。P 批次从 8K 加到 32K，保留融合 MoE，开启 EPLB 和通信重叠。 | [TTFT 与输入吞吐](results/case19/ttft-throughput.svg) |
| 21 | D 先受 KV 容量限制。减小 MoE 缓冲和长 KV 页的占位，迁移输入 embedding，缩小 HCCL 缓冲，再消除融合 MoE 与共享专家激活的争用。 | [C1152 逐轮结果](results/case21/c1152.json) · [历史曲线](results/case21/round2.svg) |

## 逐项优化与实测收益

C 表示客户端并发上限。吞吐均按 P 或 D 的物理卡计。算子测量和服务吞吐在各行标明。

| 场景 | 优化方法 | 对照与实测提升 | PR 或证据 |
| --- | --- | --- | --- |
| 19、23、21 | P renderer 1 → 4 | 19 C24 单卡输入 −0.10%，TTFT 5.440 → 5.439 s。23 C216 单卡输出 +14.01%，TTFT 2.90 → 2.31 s。21 C1152 单卡输出 +40.03%，TPOT 21.75 → 27.15 ms。 | [#4](https://github.com/jiaran-king/dsv4.1-optimize/pull/4) · [21 对照](docs/case21-c1152.md#逐阶段实测) |
| 23 · C248 | 加 78 行 Decode 图捕获档位 | D 单卡输出 1,108.2 → 1,148.1 tok/s（+3.59%），平均 TPOT 19.23 → 17.63 ms。 | [#5](https://github.com/jiaran-king/dsv4.1-optimize/pull/5) |
| 19 · C42 | 32K Prefill 批次与 MegaMoE 启动修复 | 32K 与 16K 同负载相比，P 单卡输入 +1.63%，平均 TTFT 8.257 → 8.179 s。 | [#6](https://github.com/jiaran-king/dsv4.1-optimize/pull/6) |
| 19 · C42 | Engram 查表重叠 | P 单卡输入 +1.58%，平均 TTFT 8.179 → 8.133 s。 | [#7](https://github.com/jiaran-king/dsv4.1-optimize/pull/7) |
| 19 · C42 / C52 | PCP AllGather 与 Q 投影重叠 | 单轮 P 单卡输入分别 +0.30% / −1.17%。C42 平均 TTFT 8.133 → 8.114 s。 | [#8](https://github.com/jiaran-king/dsv4.1-optimize/pull/8) |
| 19 · C42 | STAIR EPLB | P 单卡输入 +33.58%，平均 TTFT 8.114 → 5.942 s。 | [#9](https://github.com/jiaran-king/dsv4.1-optimize/pull/9) |
| 21 · D 侧算子 | 按每步批次缩容 MoE 分发 | 主模型缓冲 41,472 → 13,824 行，草稿缓冲 20,736 → 5,760 行。 | [#1](https://github.com/jiaran-king/dsv4.1-optimize/pull/1) |
| 21 · D 侧算子 | SwiGLU 仅处理有效行 | 5,760 行容量、864 行有效时，算子 546.74 → 49.40 µs，有效行逐位一致。 | [#2](https://github.com/jiaran-king/dsv4.1-optimize/pull/2) |
| 21 · D 侧显存 | BF16 输入 embedding 迁移 Host VMM | 每 DIE 释放约 2.47 GiB，抽查的 embedding 结果逐位一致。 | [#3](https://github.com/jiaran-king/dsv4.1-optimize/pull/3) |
| 21 · C1152 | 上述三项组合 | 相对原始 D，单卡输出 1,711.98 → 1,868.59 tok/s（+9.15%），TPOT 27.15 → 28.44 ms。各项正式吞吐增益未单测。 | [组合实测](docs/case21-c1152.md#逐阶段实测) |
| 21 · C1152 | KV 紧凑布局 | D 单卡输出 1,868.59 → 2,144.23 tok/s（+14.75%），TPOT 28.44 → 32.51 ms。 | [#10](https://github.com/jiaran-king/dsv4.1-optimize/pull/10) · [上游 RFC](https://github.com/vllm-project/vllm-ascend/issues/21324) |
| 21 · C1152 | 缩减 HCCL 缓冲并限制图捕获 | D 单卡输出 2,144.23 → 2,232.20 tok/s（+4.10%），TPOT 32.51 → 37.78 ms。 | [#11](https://github.com/jiaran-king/dsv4.1-optimize/pull/11) |
| 21 · C1152 | W4A8 融合 MoE 与共享专家激活顺序，带 SiLU 保护 | 与仅调缓冲相比，单卡输出 2,232.20 → 2,330.28 tok/s（+4.39%），TPOT 37.78 → 35.41 ms。候选为一轮复测。 | [#12](https://github.com/jiaran-king/dsv4.1-optimize/pull/12) · [精度复审](docs/case21-c1152.md#精度复审) |

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
