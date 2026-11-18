# 测试方法与复现

以下是三组共用的部署和编号 23 的发压步骤。编号 19 的输入负载与全程口径见[纯 P 报告](case19-pure-p.md)，编号 21 的完整启动和发压命令见[纯 D 复现](case21-pure-d.md#复现)。

## 软件和部署

P/D 分别运行在同一 SuperPod 的两台 A3 服务器上。每台分配 8 张物理卡，每卡 2 DIE。模型为 DeepSeek-V4.1-Flash 1017 W4A8，使用 vLLM-Ascend 0.32.0rc1 A3 aarch64 镜像和 Host VMM 回移。运行版本、镜像构建标识、权重元数据与负载摘要见[实验清单](../results/manifest.json)。复测需要自行提供同版本镜像、检查点和有 Host VMM 支持的 CANN 运行时。

| 参数 | P（Prefill） | D（Decode） |
| --- | --- | --- |
| DP / PCP / TP | 4 / 4 / 1 | 16 / 1 / 1 |
| MoE 专家并行 | 开启 | EP16 |
| API rank | 4 | 16 |
| 最大 batch tokens | 8,192 | 512 |
| 最大 sequences | 16 | 72 |
| 设备内存比例 | 0.90 | 0.95 |
| 前缀缓存 | 开启 | 关闭 |
| 执行模式 | Eager | Full Decode Only 图模式，异步调度 |

共享设置包括 Model Runner V2、CPU offload 的共享 Engram、DSpark 草拟 5 token、MooncakeHybridConnector、上下文长度 1,048,576、KV block 大小 128。其余启动实参在[启动脚本](../deploy/launch_node.py)中。基线使用原图捕获列表和默认 renderer worker 1。优化版显式设置 D 捕获列表及 P renderer worker 4。

## 启动 P、D 和 Proxy

在两个角色各自的镜像内准备[Host VMM 回移](../patches/README.md)。设置 `PD_MODEL_PATH`、`PD_LOCAL_IP`、`PD_NIC` 和 `PD_HOST_VMM_OVERLAY`。其中 `PD_LOCAL_IP`、`PD_NIC` 是当前角色的通信地址和网卡，overlay 路径指向构建输出目录。设备序号按当前容器可见的 16 个 DIE 填写。命令分别在 P、D 容器运行，角色日志目录使用新路径。

```bash
export PD_DEVICES=0,1,2,3,4,5,6,7,8,9,10,11,12,13,14,15

# P
PD_LOG_DIR=local-runs/p-baseline python3 deploy/launch_node.py p --profile baseline

# D
PD_LOG_DIR=local-runs/d-baseline python3 deploy/launch_node.py d --profile baseline
```

编号 23 的优化版在两端都用 `--profile optimized`。`--dry-run` 打印隐藏节点地址和模型路径的 rank 参数。Proxy 脚本取自[实测使用的 vLLM-Ascend 修订](https://github.com/vllm-project/vllm-ascend/blob/24487f4f48ee99cf45d86d1c504e645549b8c1ef/examples/disaggregated_prefill_v1/load_balance_proxy_server_example.py)。在 P 服务器上设置 `PD_P_HOST` 和 `PD_D_HOST`，默认监听 P 的 8080，P/D 两端的 API port 从 7100 起递增。

```bash
export PD_PROXY_SCRIPT="$VLLM_ASCEND_SRC/examples/disaggregated_prefill_v1/load_balance_proxy_server_example.py"
bash deploy/launch_proxy.sh
```

## 构造负载

语料使用公开的 [GSM8K test split](https://github.com/openai/grade-school-math)。生成器固定 seed 42，使用与服务一致的 DeepSeek V4.1 tokenizer 和 chat template 校验每条请求恰好为 131,072 个输入 token。576 条稳态场景重复同一个完整 prompt。1300 条补充场景共享 117,888 token 前缀，每条请求使用不同后缀。语料文件 SHA-256 见[来源记录](../bench/gsm8k-source.json)。

在具有实测 vLLM tokenizer 的环境运行下面的命令。先将 `TOKENIZER_PATH` 设为检查点对应的本地 tokenizer 目录。

```bash
mkdir -p datasets
curl -fL https://raw.githubusercontent.com/openai/grade-school-math/master/grade_school_math/data/test.jsonl \
  -o datasets/gsm8k-test.jsonl
python3 bench/prepare_gsm8k_workload.py \
  --tokenizer "$TOKENIZER_PATH" \
  --corpus datasets/gsm8k-test.jsonl \
  --out datasets/gsm8k
```

生成的 `steady.jsonl` 对应主曲线。`baseline.jsonl` 和 `smoke.jsonl` 用于补充验证。生成清单记录每个数据集的 SHA-256，主曲线使用的 SHA-256 见[实验清单](../results/manifest.json)。

## 执行 AISBench

客户端使用 Python 3.11+，实测为 Python 3.12.16。AISBench 版本固定到 [8b80c4e](https://github.com/AISBench/benchmark/tree/8b80c4e667657086b845879f61ae8a520db7f9fd)，客户端依赖版本包括 `datasets==3.6.0` 和 `pyarrow==25.0.1`。在客户端虚拟环境安装依赖，并设置 `TOKENIZER_PATH`、`PD_PROXY_HOST`、`PD_P_HOST`。如果使用自定义端口，通过 `--proxy-port` 和 `--prefill-api-port` 传入。

```bash
python3 -m pip install \
  'ais_bench_benchmark @ git+https://github.com/AISBench/benchmark.git@8b80c4e667657086b845879f61ae8a520db7f9fd' \
  'datasets==3.6.0' 'pyarrow==25.0.1'

python3 bench/run_case.py smoke --dataset datasets/gsm8k/smoke.jsonl \
  --tokenizer "$TOKENIZER_PATH" --output local-runs/smoke
python3 bench/run_case.py steady --dataset datasets/gsm8k/steady.jsonl \
  --tokenizer "$TOKENIZER_PATH" --concurrency 216 --output local-runs/steady-c216
```

发压前校验 Proxy 有 4 个 P 和 16 个 D 端点，并向每个 P rank 发送一次 128K 输入、1 token 输出的预热请求。正式请求走 Proxy 的流式 Chat Completions，生成参数为 `temperature=0`、`ignore_eos=true`、`seed=1024`，输出上限 1,024 token。

扫并发时，复用同一套 P/D 和 Proxy，按点修改 `--concurrency`，使用独立的输出目录。每轮完成后再发起下一轮。基线的 12 个并发点和优化版的 4 个并发点见逐组 [基线表](../results/baseline/points.csv) 和 [优化表](../results/optimized/points.csv)。

```bash
python3 bench/run_case.py full1300 --dataset datasets/gsm8k/baseline.jsonl \
  --tokenizer "$TOKENIZER_PATH" --output local-runs/full1300
```

主场景以不限制发送速率的方式发送 576 条。1300 条补充验证的并发上限为 130，发送速率为 3.60 请求/秒，按全程统计。[补充实测数据](../results/supplemental/trials.json)

## 统计口径

`audit_benchmark.py` 保留逐请求相对起止时间、输入输出 token 数、TTFT、TPOT 和 AISBench 稳态标记。全程从第一条发出算到最后一条结束。稳态使用固定版本 AISBench 的 `StablePerfMetricCalculator`，按请求发起时间选入样本。并发 216 的正式对比每轮发出 576 条且全部成功，稳态计入 360 条。并发 144 的补充测量稳态计入 432 条。

稳态输出吞吐等于所选请求输出 token 总数除以稳态窗口长度。D 侧单卡输出再除以 8。平均 TPOT 严格小于 21 ms 的轮次计入该并发点的达标轮数。每个点使用逐轮指标的中位数，P90 同表记录。选择在每轮都达到门限的并发点中 D 侧单卡输出吞吐最高的点。[逐轮数据与离线回算](../results/README.md)
