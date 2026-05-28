"""Cross-Encoder 重排:bge-reranker-v2-m3 对 (query, passage) 打分,重排候选。

与 Retriever 不同:reranker 输入是"query + 一批候选 doc",输出重排后的 top_n。
用法:召回阶段多取(top_k=50)→ reranker 精排到 top_n=3 给 LLM。

延迟加载 + 依赖注入(``model`` 可被 mock),对齐 ``BGEEmbedder`` 风格。
"""

from __future__ import annotations

from typing import Any

from src.config import settings
from src.ingest.schema import RetrievedDoc
from src.logger import logger
from src.retrieval.base import Retriever

DEFAULT_TOP_N = 3
DEFAULT_BATCH_SIZE = 16
DEFAULT_CANDIDATE_K = 50


class CrossEncoderReranker:
    """bge-reranker-v2-m3 封装。首次 rerank 时才加载权重。"""

    def __init__(
        self,
        model_name: str = settings.reranker_model,
        device: str = settings.embedding_device,
        use_fp16: bool = settings.embedding_use_fp16,
        model: Any = None,
        batch_size: int = DEFAULT_BATCH_SIZE,
    ) -> None:
        self.model_name = model_name
        self.device = self._resolve_device(device)
        self.use_fp16 = use_fp16 and self.device != "cpu"
        self.batch_size = batch_size
        self._model = model  # 注入则跳过加载(测试用)

    @staticmethod
    def _resolve_device(device: str) -> str:
        if device == "auto":
            import torch

            return "cuda" if torch.cuda.is_available() else "cpu"
        return device

    def _ensure_loaded(self) -> None:
        if self._model is not None:
            return
        logger.info(
            f"loading reranker: {self.model_name} on {self.device} fp16={self.use_fp16}"
        )
        # 直接用 transformers(fast tokenizer),绕开 FlagReranker 在本环境的
        # XLMRobertaTokenizer.prepare_for_model 不兼容问题。
        self._model = _HFCrossEncoder(self.model_name, self.device, self.use_fp16)
        # 预热:首次前向有 CUDA/cudnn 编译开销(实测 ~9s),用满 batch 预热一次,
        # 之后稳态 ~180ms/50 候选。注入 mock(测试)时不触发。
        try:
            self._model.compute_score([["warmup", "warmup"]] * self.batch_size)
        except Exception:  # noqa: BLE001  预热失败不应阻断
            pass

    def score(self, query: str, passages: list[str]) -> list[float]:
        """对每个 passage 算与 query 的相关性分数(归一化到 0-1)。"""
        if not passages:
            return []
        self._ensure_loaded()
        pairs = [[query, p] for p in passages]
        raw = self._model.compute_score(
            pairs, batch_size=self.batch_size, normalize=True
        )
        # 单条时部分版本返回标量,统一成 list[float]
        if isinstance(raw, (int, float)):
            return [float(raw)]
        return [float(x) for x in raw]

    def rerank(
        self, query: str, docs: list[RetrievedDoc], top_n: int = DEFAULT_TOP_N
    ) -> list[RetrievedDoc]:
        """对候选 docs 重排,返回相关性降序的前 top_n,``source="rerank"``。"""
        if not query or not query.strip() or not docs or top_n <= 0:
            return []
        scores = self.score(query, [d.text for d in docs])
        ranked = sorted(zip(docs, scores), key=lambda ds: ds[1], reverse=True)
        out: list[RetrievedDoc] = []
        for new_rank, (doc, sc) in enumerate(ranked[:top_n]):
            out.append(
                doc.model_copy(
                    update={"score": sc, "source": "rerank", "rank": new_rank}
                )
            )
        return out


class RerankRetriever(Retriever):
    """把"基础检索器 + reranker"组合成一个 Retriever:召回多候选 → 精排到 top_k。

    可热插拔进 pipeline / 评估:base 可以是 Dense / Hybrid 等任意 Retriever。
    """

    def __init__(
        self,
        base: Retriever,
        reranker: CrossEncoderReranker,
        candidate_k: int = DEFAULT_CANDIDATE_K,
    ) -> None:
        self.base = base
        self.reranker = reranker
        self.candidate_k = candidate_k

    def search(self, query: str, top_k: int = 10) -> list[RetrievedDoc]:
        if not query or not query.strip() or top_k <= 0:
            return []
        candidates = self.base.search(query, top_k=max(self.candidate_k, top_k))
        return self.reranker.rerank(query, candidates, top_n=top_k)


class _HFCrossEncoder:
    """transformers 后端的 cross-encoder 打分器,暴露 ``compute_score`` 接口。"""

    def __init__(self, model_name: str, device: str, use_fp16: bool) -> None:
        import torch
        from transformers import AutoModelForSequenceClassification, AutoTokenizer

        self._torch = torch
        self.device = device
        self.tokenizer = AutoTokenizer.from_pretrained(model_name, use_fast=True)
        model = AutoModelForSequenceClassification.from_pretrained(model_name)
        if use_fp16 and device != "cpu":
            model = model.half()
        self.model = model.to(device).eval()

    def compute_score(
        self,
        pairs: list[list[str]],
        batch_size: int = DEFAULT_BATCH_SIZE,
        normalize: bool = True,
    ) -> list[float]:
        torch = self._torch
        scores: list[float] = []
        for i in range(0, len(pairs), batch_size):
            batch = pairs[i : i + batch_size]
            enc = self.tokenizer(
                [p[0] for p in batch],
                [p[1] for p in batch],
                padding=True,
                truncation=True,
                max_length=512,
                return_tensors="pt",
            ).to(self.device)
            with torch.no_grad():
                logits = self.model(**enc).logits.view(-1).float()
            if normalize:
                logits = torch.sigmoid(logits)
            scores.extend(logits.cpu().tolist())
        return scores
