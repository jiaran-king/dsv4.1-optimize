# 实测数据

## 编号 23 · 稳态

[实验清单](manifest.json)记录模型、镜像、软件版本、拓扑和正式负载。[对比结果](comparison.json)由[离线回算脚本](../bench/report.py)生成。

| 实验 | 轮数 | 逐轮指标 | 逐请求时间线 |
| --- | ---: | --- | --- |
| 基线扫描 | 19 | [JSON](baseline/trials.json) · [并发点 CSV](baseline/points.csv) | [CSV.gz](baseline/requests.csv.gz) |
| 优化扫描 | 6 | [JSON](optimized/trials.json) · [并发点 CSV](optimized/points.csv) | [CSV.gz](optimized/requests.csv.gz) |
| 同机 A/B 的 A 样本 | 1 | [JSON](ab/trials.json) · [配对绑定](ab/pair.json) | [CSV.gz](ab/requests.csv.gz) |
| smoke、1300 条全程、C144 稳态 | 3 | [JSON](supplemental/trials.json) | [CSV.gz](supplemental/requests.csv.gz) |

同机 A/B 的 B 样本就是优化扫描的第一轮 C216。时间线用各轮第一条成功请求的起点归零，逐行保留请求序号、成功标记、相对起止时间、token 数、TTFT、TPOT 和稳态标记。`trials.json` 保留各轮的全程和稳态窗口统计。稳态窗口为 `null` 时该轮使用全程结果。

`python3 bench/report.py` 从逐请求记录回算窗口内 TTFT、TPOT、P90、吞吐和请求数，再按并发聚合、生成并发点 CSV 与比较 JSON。加 `--plot` 可重画[对比图](tpot-throughput.svg)和[基线图](baseline/baseline-curve.png)。

## 编号 19 · 纯 P

[对比结果](case19/comparison.json)记录用户原表、正式基线、优化版、运行配置和可比条件。[实测点](case19/points.csv)对应 [TTFT 与 P 单卡输入吞吐图](case19/ttft-throughput.svg)，正式基线和最终点采用确认轮的中位数。[逐轮结果](case19/trials.json)和[逐请求时间线](case19/requests.csv.gz)保留 34 轮记录，每轮 168 条，其中 2 轮用于 EPLB 校准。时间线按各轮第一条请求的发出时间归零。

在仓库根目录运行 `python3 bench/report_case19.py` 可回算每轮与曲线点，并核对最终增益。 [编号 19 实验报告](../docs/case19-pure-p.md)

## 编号 21 · 纯 D

当前 [C1152 阶段对照](../docs/case21-c1152.md) 包含 13 个计时轮、59,904 条成功请求。用 [逐轮和精度 JSON](case21/c1152.json) 查稳态窗口，用 [逐请求 CSV.gz](case21/c1152-requests.csv.gz) 查各轮起止、输入输出 token 和选样标记。请求时间以每轮首条请求为零点。稳态单卡输出为稳态标记行的输出 token 总数除以窗口时长和 8 张 D 卡。

[对比结果](case21/comparison.json)记录原表、正式基线、两轮优化、配置及延迟门限。[逐轮结果](case21/trials.json)和[逐请求时间线](case21/requests.csv.gz)包含 22 轮、86,016 条记录，覆盖原表同档复测、基线扫描、关键 A/B 和两轮验收。相对时间以每轮第一条请求的发出时间归零，稳态使用 AISBench 按请求发起时间选中的样本。

在仓库根目录运行 `python3 bench/report_case21.py` 可核对逐轮全程和稳态统计、每轮平均 TPOT 门限、正式样本中位数与增益。 [第一轮曲线](case21/round1.svg) · [第二轮曲线](case21/round2.svg) · [编号 21 实验报告](../docs/case21-pure-d.md)
