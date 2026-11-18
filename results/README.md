# 实测数据

[实验清单](manifest.json)记录模型、镜像、软件版本、拓扑和正式负载。[对比结果](comparison.json)由[离线回算脚本](../bench/report.py)生成。

| 实验 | 轮数 | 逐轮指标 | 逐请求时间线 |
| --- | ---: | --- | --- |
| 基线扫描 | 19 | [JSON](baseline/trials.json) · [并发点 CSV](baseline/points.csv) | [CSV.gz](baseline/requests.csv.gz) |
| 优化扫描 | 6 | [JSON](optimized/trials.json) · [并发点 CSV](optimized/points.csv) | [CSV.gz](optimized/requests.csv.gz) |
| 同机 A/B 的 A 样本 | 1 | [JSON](ab/trials.json) · [配对绑定](ab/pair.json) | [CSV.gz](ab/requests.csv.gz) |
| smoke、1300 条全程、C144 稳态 | 3 | [JSON](supplemental/trials.json) | [CSV.gz](supplemental/requests.csv.gz) |

同机 A/B 的 B 样本就是优化扫描的第一轮 C216。时间线用各轮第一条成功请求的起点归零，逐行保留请求序号、成功标记、相对起止时间、token 数、TTFT、TPOT 和稳态标记。`trials.json` 保留各轮的全程和稳态窗口统计。稳态窗口为 `null` 时该轮使用全程结果。

`python3 bench/report.py` 从逐请求记录回算窗口内 TTFT、TPOT、P90、吞吐和请求数，再按并发聚合、生成并发点 CSV 与比较 JSON。加 `--plot` 可重画[对比图](tpot-throughput.svg)和[基线图](baseline/baseline-curve.png)。
