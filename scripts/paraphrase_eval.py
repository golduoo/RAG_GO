"""把 eval_v1.jsonl 的问题改写成口语/抽象表达,降低与原文的词面相似度。

用途:验证 baseline 的高指标是否来自合成评估集的词面泄漏。

工作流:
- 读 eval_v1.jsonl
- 对每条 question,让 DeepSeek 改写成:
  · 用日常口语
  · 不直接复用原问题里的关键词,改用近义词或概括描述
  · 语义不变,gold_answer 仍然是正确答案
- 输出到 data/eval/eval_v1_paraphrased.jsonl(同样的 qid + gold_doc_ids,只换 question)

用法:
    uv run python scripts/paraphrase_eval.py
    uv run python scripts/paraphrase_eval.py --workers 5
"""

from __future__ import annotations

import argparse
import json
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from tqdm import tqdm

from src.eval.schema import EvalSample
from src.generate.llm import LLMClient
from src.logger import logger


DEFAULT_INPUT = Path("data/eval/eval_v1.jsonl")
DEFAULT_OUTPUT = Path("data/eval/eval_v1_paraphrased.jsonl")


PARAPHRASE_PROMPT = """你是中文 QA 数据扩增助手。给定一个原始问题和它的标准答案,
请把**问题**改写成同样语义、但**词面更接近真实用户口语**的版本。

强约束:
- 改写后的问题**不能复用原问题里的核心名词**(用近义词、上位词、解释性短语替换)
- 改写后的问题应该更口语、更简短或更抽象
- 改写后的问题问的是**同一件事**,标准答案不变
- 输出**严格 JSON**,只有一个字段 question,不要其他解释

原始问题: {question}
标准答案: {gold_answer}

示例(仅参考结构,不要照搬内容):
{{"question": "顺丰快件大概要几天能到?"}}
"""


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    p.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    p.add_argument("--workers", type=int, default=5)
    return p.parse_args()


def load_samples(path: Path) -> list[EvalSample]:
    out: list[EvalSample] = []
    with path.open("r", encoding="utf-8") as fh:
        for line in fh:
            out.append(EvalSample(**json.loads(line)))
    return out


def paraphrase_one(llm: LLMClient, s: EvalSample) -> EvalSample | None:
    try:
        raw = llm.complete(
            [
                {
                    "role": "user",
                    "content": PARAPHRASE_PROMPT.format(
                        question=s.question, gold_answer=s.gold_answer
                    ),
                }
            ],
            temperature=0.7,
            max_tokens=150,
        ).strip()
        if raw.startswith("```"):
            raw = raw.strip("`")
            if raw.lower().startswith("json"):
                raw = raw[4:].strip()
        data = json.loads(raw)
        new_q = data.get("question", "").strip()
        if not new_q:
            return None
        return EvalSample(
            qid=s.qid + "_p",
            question=new_q,
            gold_answer=s.gold_answer,
            gold_doc_ids=s.gold_doc_ids,
            question_type=s.question_type,
            metadata={**s.metadata, "paraphrased_from": s.question},
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning(f"paraphrase fail qid={s.qid}: {type(exc).__name__}: {exc}")
        return None


def main() -> int:
    args = parse_args()
    samples = load_samples(args.input)
    logger.info(f"loaded {len(samples)} samples from {args.input}")

    llm = LLMClient()
    out: list[EvalSample] = []
    with ThreadPoolExecutor(max_workers=args.workers) as ex:
        futures = {ex.submit(paraphrase_one, llm, s): s for s in samples}
        for fut in tqdm(as_completed(futures), total=len(futures), desc="paraphrase"):
            r = fut.result()
            if r is not None:
                out.append(r)

    logger.info(f"paraphrased {len(out)}/{len(samples)}")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", encoding="utf-8") as fh:
        for s in out:
            fh.write(json.dumps(s.model_dump(), ensure_ascii=False) + "\n")
    print(f"\n[ OK ] wrote {len(out)} paraphrased samples to {args.output}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
