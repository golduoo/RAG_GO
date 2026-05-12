"""用 DeepSeek 从语料中生成评估集(每条 1 个 question + gold_answer + gold_doc_ids)。

工作流程:
1. 从 logistics_corpus.jsonl 随机采样 N 条 Document
2. 对每条 Document 用同样的 FixedTokenSplitter 算出 chunk IDs(必须与 ingest 一致)
3. 让 LLM 阅读 Document 文本,产出 JSON {question, answer, type}
4. gold_doc_ids = 该 Document 的所有 chunk ID
5. 输出到 data/eval/eval_v1.jsonl(EvalSample schema)

用法:
    uv run python scripts/build_eval_set.py
    uv run python scripts/build_eval_set.py -n 100 --workers 5 --seed 42
"""

from __future__ import annotations

import argparse
import json
import random
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from tqdm import tqdm

from src.eval.schema import EvalSample
from src.generate.llm import LLMClient
from src.ingest.schema import Document
from src.ingest.splitters import FixedTokenSplitter
from src.logger import logger


DEFAULT_INPUT = Path("data/processed/logistics_corpus.jsonl")
DEFAULT_OUTPUT = Path("data/eval/eval_v1.jsonl")


EVAL_PROMPT = """你是中文 QA 数据构造助手。根据下面这段资料,**严格生成一对**问答用于评估检索 RAG 系统。

资料:
{passage}

要求:
- 问题必须**只能**通过这段资料才能正确回答(不要太泛化)
- 问题用一句话,陈述清楚,可以是事实型 / 解释型 / 是否型
- 答案是从资料中直接归纳出来的简短句子(< 100 字)
- 输出**严格 JSON**,只有 question / answer / question_type 三个字段
- question_type 必须从下列选一个:single_hop / yesno / chat
- 不要任何前后说明,不要 ```json``` 围栏,直接给 JSON

示例输出:
{{"question": "顺丰特快从上海到北京一般几天到?", "answer": "1-2 个工作日。", "question_type": "single_hop"}}
"""


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("-n", "--num", type=int, default=100, help="生成多少条")
    p.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    p.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    p.add_argument("--chunk-size", type=int, default=400)
    p.add_argument("--chunk-overlap", type=int, default=50)
    p.add_argument("--seed", type=int, default=42)
    p.add_argument("--workers", type=int, default=5, help="并发线程数")
    p.add_argument("--min-len", type=int, default=80, help="过滤过短文档(信息密度低)")
    return p.parse_args()


def load_docs(path: Path) -> list[Document]:
    docs = []
    with path.open("r", encoding="utf-8") as fh:
        for line in fh:
            docs.append(Document(**json.loads(line)))
    return docs


def llm_generate_qa(llm: LLMClient, passage: str) -> dict | None:
    """调一次 LLM 生成 QA;解析失败返 None。"""
    try:
        raw = llm.complete(
            [{"role": "user", "content": EVAL_PROMPT.format(passage=passage)}],
            temperature=0.5,
            max_tokens=300,
        ).strip()
        # 兼容性:有些时候模型仍会加 ```json``` 围栏
        if raw.startswith("```"):
            raw = raw.strip("`")
            if raw.lower().startswith("json"):
                raw = raw[4:].strip()
        data = json.loads(raw)
        if not all(k in data for k in ("question", "answer", "question_type")):
            return None
        return data
    except Exception as exc:  # noqa: BLE001
        logger.warning(f"LLM parse fail: {type(exc).__name__}: {exc}")
        return None


def build_samples(
    docs: list[Document],
    llm: LLMClient,
    splitter: FixedTokenSplitter,
    workers: int,
) -> list[EvalSample]:
    """并发调 LLM 生成 QA;每条 doc 一个 EvalSample。"""
    samples: list[EvalSample] = []

    def _one(doc: Document) -> EvalSample | None:
        chunks = splitter.split_document(doc)
        gold_ids = [c.id for c in chunks]
        qa = llm_generate_qa(llm, doc.text)
        if not qa:
            return None
        return EvalSample(
            qid=f"q_{doc.id[:12]}",
            question=qa["question"].strip(),
            gold_answer=qa["answer"].strip(),
            gold_doc_ids=gold_ids,
            question_type=qa.get("question_type", "single_hop"),
            metadata={"src_doc_id": doc.id, "source": doc.source},
        )

    with ThreadPoolExecutor(max_workers=workers) as ex:
        futures = {ex.submit(_one, d): d for d in docs}
        for fut in tqdm(as_completed(futures), total=len(futures), desc="LLM gen"):
            s = fut.result()
            if s is not None:
                samples.append(s)
    return samples


def main() -> int:
    args = parse_args()
    random.seed(args.seed)

    docs_all = load_docs(args.input)
    docs_all = [d for d in docs_all if len(d.text) >= args.min_len]
    logger.info(f"corpus: {len(docs_all)} docs (len>={args.min_len})")

    if args.num > len(docs_all):
        raise ValueError(f"-n {args.num} > corpus size {len(docs_all)}")

    docs = random.sample(docs_all, args.num)
    logger.info(f"sampled {len(docs)} docs for eval generation")

    llm = LLMClient()
    splitter = FixedTokenSplitter(chunk_size=args.chunk_size, chunk_overlap=args.chunk_overlap)

    samples = build_samples(docs, llm, splitter, workers=args.workers)
    logger.info(f"generated {len(samples)}/{len(docs)} samples (drop rate {1-len(samples)/len(docs):.1%})")

    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", encoding="utf-8") as fh:
        for s in samples:
            fh.write(json.dumps(s.model_dump(), ensure_ascii=False) + "\n")

    print(f"\n[ OK ] wrote {len(samples)} samples to {args.output}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
