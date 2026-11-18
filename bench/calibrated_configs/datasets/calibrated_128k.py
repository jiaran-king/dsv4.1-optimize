calibrated_128k_datasets = [
    dict(
        abbr="calibrated_128k",
        type="ais_bench.benchmark.datasets.custom.CustomDataset",
        path="{{$AISBENCH_DATASET_PATH:dataset.jsonl}}",
        reader_cfg=dict(input_columns=["question", "max_out_len"], output_column=None),
        infer_cfg=dict(
            prompt_template=dict(
                type="ais_bench.benchmark.openicl.icl_prompt_template.PromptTemplate", template="{question}"
            ),
            retriever=dict(type="ais_bench.benchmark.openicl.icl_retriever.ZeroRetriever"),
            inferencer=dict(type="ais_bench.benchmark.openicl.icl_inferencer.GenInferencer"),
        ),
        eval_cfg=dict(evaluator=dict(type="ais_bench.benchmark.openicl.icl_evaluator.AccEvaluator")),
    )
]
