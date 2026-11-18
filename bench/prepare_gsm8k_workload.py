"""Construct exact-length AISBench workloads from a frozen GSM8K question corpus."""

import argparse
import hashlib
import json
import random
from pathlib import Path

INPUT_TOKENS = 131072
OUTPUT_TOKENS = 1024
SHARED_90_TOKENS = 117888
CASE_COUNTS = {"smoke": 8, "baseline": 1300, "steady": 576}


BLOCK_SIZE = 128
SEED = 42
SEPARATORS = ("\n\n", "\n", "\n\n---\n\n", " ", ".\n\n")


def digest(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def fit(expected, initial, make_text, count_tokens):
    size = initial
    for _ in range(6):
        text = make_text(size)
        actual = count_tokens(text)
        if actual == expected:
            return text, size
        size += expected - actual
    raise RuntimeError(f"Could not calibrate {expected} rendered tokens")


def fit_excerpt(tokenizer, corpus_ids, start, expected, head, tail, count):
    """Fit a corpus substring, allowing for token merges at either boundary."""
    estimate = expected - count(head + tail)

    def excerpt(size):
        return tokenizer.decode(
            corpus_ids[start : start + size],
            skip_special_tokens=False,
            clean_up_tokenization_spaces=False,
        ).strip("\ufffd")

    for divider in SEPARATORS:
        def make_text(size):
            return head + excerpt(size) + divider + tail

        try:
            result, _size = fit(expected, estimate, make_text, count)
            return result
        except RuntimeError:
            # The rendered length can skip a value when the final token merges.
            close = estimate + expected - count(make_text(estimate))
            for size in range(max(1, close - 5), close + 6):
                result = make_text(size)
                if count(result) == expected:
                    return result
    raise RuntimeError(f"Could not fit a GSM8K excerpt to {expected} rendered tokens")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--tokenizer", type=Path, required=True)
    parser.add_argument("--corpus", type=Path, required=True)
    parser.add_argument("--source", type=Path, default=Path(__file__).with_name("gsm8k-source.json"))
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    from vllm.tokenizers.deepseek_v41 import DeepseekV41Tokenizer


    source = json.loads(args.source.read_text(encoding="utf-8"))
    if digest(args.corpus) != source["sha256"]:
        raise ValueError("GSM8K corpus checksum differs from its source receipt")
    with args.corpus.open(encoding="utf-8") as stream:
        questions = [json.loads(line)["question"].strip() for line in stream if line.strip()]
    if len(questions) != source["rows"] or len(set(questions)) < CASE_COUNTS["baseline"]:
        raise ValueError("GSM8K corpus has an unexpected number of questions")

    args.out.mkdir()
    rng = random.Random(SEED)
    rng.shuffle(questions)

    tokenizer = DeepseekV41Tokenizer.from_pretrained(str(args.tokenizer), local_files_only=True)
    needle = "A placeholder for exact chat-template calibration"
    template = tokenizer.apply_chat_template(
        [{"role": "user", "content": needle}], tokenize=False, add_generation_prompt=True
    )
    if not isinstance(template, str) or template.count(needle) != 1:
        raise ValueError("Could not calibrate the service chat template")
    head, foot = template.split(needle)

    def encode(text):
        return tokenizer.encode(text, add_special_tokens=False)

    corpus_text = "\n\n".join(questions) + "\n\n"
    corpus_ids = encode(corpus_text)
    repeats = (INPUT_TOKENS + CASE_COUNTS["baseline"]) // len(corpus_ids) + 1
    if repeats > 1:
        corpus_ids = encode(corpus_text * repeats)
    common = fit_excerpt(
        tokenizer, corpus_ids, 0, SHARED_90_TOKENS,
        "Read the following grade-school math problems for context.\n\n", "",
        lambda text: len(encode(head + text)),
    )
    common_ids = encode(head + common)
    tail_tokens = INPUT_TOKENS - SHARED_90_TOKENS
    starts = rng.sample(range(len(corpus_ids) - tail_tokens - BLOCK_SIZE), CASE_COUNTS["baseline"])
    next_blocks = set()
    first_row = None

    with (args.out / "baseline.jsonl").open("xb") as baseline, (args.out / "smoke.jsonl").open("xb") as smoke:
        for offset in range(0, CASE_COUNTS["baseline"], 8):
            batch = list(enumerate(starts[offset : offset + 8], offset))
            tails = []
            for index, start in batch:
                tag = f"Additional practice problems, set {index + 1}.\n\n"
                question = "\n\nQuestion to solve. Show your reasoning.\n" + questions[index]
                tails.append(fit_excerpt(
                    tokenizer, corpus_ids, start, tail_tokens, tag, question,
                    lambda text: len(encode(text + foot)),
                ))
            encoded = tokenizer(
                [head + common + tail + foot for tail in tails],
                add_special_tokens=False, return_attention_mask=False,
            )["input_ids"]
            for (index, start), tail, ids in zip(batch, tails, encoded, strict=True):
                if len(ids) != INPUT_TOKENS:
                    tag = f"Additional practice problems, set {index + 1}.\n\n"
                    question = "\n\nQuestion to solve. Show your reasoning.\n" + questions[index]
                    tail = fit_excerpt(
                        tokenizer, corpus_ids, start, tail_tokens, tag, question,
                        lambda text: len(encode(head + common + text + foot)) - SHARED_90_TOKENS,
                    )
                    ids = encode(head + common + tail + foot)
                if len(ids) != INPUT_TOKENS or ids[:SHARED_90_TOKENS] != common_ids:
                    raise ValueError(f"Request {index + 1} failed exact length or shared-prefix verification")
                suffix_block = tuple(ids[SHARED_90_TOKENS : SHARED_90_TOKENS + BLOCK_SIZE])
                if suffix_block in next_blocks:
                    raise ValueError(f"Request {index + 1} shares the first non-prefix block")
                next_blocks.add(suffix_block)
                prompt = common + tail
                row = (json.dumps({"question": prompt, "max_tokens": OUTPUT_TOKENS}, ensure_ascii=False) + "\n").encode()
                baseline.write(row)
                if index < CASE_COUNTS["smoke"]:
                    smoke.write(row)
                if first_row is None:
                    first_row = row
            complete = offset + len(batch)
            if complete % 128 == 0 or complete == CASE_COUNTS["baseline"]:
                print(f"GSM8K baseline length and prefix verified: {complete}/{CASE_COUNTS['baseline']}", flush=True)

    with (args.out / "steady.jsonl").open("xb") as stream:
        for _ in range(CASE_COUNTS["steady"]):
            stream.write(first_row)

    manifest = {
        "source": source,
        "generation_seed": SEED,
        "corpus_cycles": repeats,
        "tokenizer_sha256": digest(args.tokenizer / "tokenizer.json"),
        "tokenizer_config_sha256": digest(args.tokenizer / "tokenizer_config.json"),
        "rendered_chat_template_sha256": hashlib.sha256(template.encode()).hexdigest(),
        "generator_sha256": digest(Path(__file__)),
        "block_size": BLOCK_SIZE,
        "shared_prefix_policy": "One global prefix for all requests in a case. Steady repeats the first baseline request.",
        "cases": {},
    }
    for case, count in CASE_COUNTS.items():
        path = args.out / f"{case}.jsonl"
        manifest["cases"][case] = {
            "requests": count, "input_tokens": INPUT_TOKENS, "max_output_tokens": OUTPUT_TOKENS,
            "shared_prefix_tokens": INPUT_TOKENS if case == "steady" else SHARED_90_TOKENS,
            "first_non_prefix_blocks": None if case == "steady" else count,
            "dataset_sha256": digest(path), "dataset_bytes": path.stat().st_size,
        }
    receipt = json.dumps(manifest, indent=2)
    (args.out / "manifest.json").write_text(receipt + "\n", encoding="utf-8")
    print(receipt, flush=True)


if __name__ == "__main__":
    main()
