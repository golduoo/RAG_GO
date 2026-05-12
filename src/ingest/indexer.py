"""Embedding + 双写入库(Milvus + ES)。

- ``BGEEmbedder``:加载 BAAI/bge-m3,fp16,支持 CUDA / CPU 自动选择
- ``MilvusWriter``:建 collection(schema 对齐 data-schemas.md §3),HNSW M=16 efConstruction=200 COSINE
- ``ESWriter``:建 index(schema §4),Phase 1 用 standard analyzer(见 ADR-003)
- ``DualWriter``:把 chunks 切批 embed + 双写
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Iterable

from elasticsearch import Elasticsearch, helpers
from pymilvus import (
    Collection,
    CollectionSchema,
    DataType,
    FieldSchema,
    connections,
    utility,
)

from src.config import settings
from src.ingest.schema import Chunk
from src.logger import logger


EMBEDDING_DIM = 1024
DEFAULT_BATCH_SIZE = 32


# ---------------------------------------------------------------------------
# Embedder
# ---------------------------------------------------------------------------


class BGEEmbedder:
    """BAAI/bge-m3,延迟加载,首次调用时触发权重下载/读盘。"""

    def __init__(
        self,
        model_name: str = settings.embedding_model,
        device: str = settings.embedding_device,
        use_fp16: bool = settings.embedding_use_fp16,
    ) -> None:
        self.model_name = model_name
        self.device = self._resolve_device(device)
        self.use_fp16 = use_fp16 and self.device != "cpu"
        self._model: Any = None

    @staticmethod
    def _resolve_device(device: str) -> str:
        if device == "auto":
            import torch

            return "cuda" if torch.cuda.is_available() else "cpu"
        return device

    def _ensure_loaded(self) -> None:
        if self._model is not None:
            return
        logger.info(f"loading embedding model: {self.model_name} on {self.device} fp16={self.use_fp16}")
        from FlagEmbedding import BGEM3FlagModel

        self._model = BGEM3FlagModel(
            self.model_name,
            use_fp16=self.use_fp16,
            devices=self.device,
        )

    def encode(self, texts: list[str], batch_size: int = DEFAULT_BATCH_SIZE) -> list[list[float]]:
        self._ensure_loaded()
        out = self._model.encode(
            texts,
            batch_size=batch_size,
            return_dense=True,
            return_sparse=False,
            return_colbert_vecs=False,
        )
        vecs = out["dense_vecs"]
        return [v.tolist() for v in vecs]


# ---------------------------------------------------------------------------
# Milvus
# ---------------------------------------------------------------------------


def _milvus_schema() -> CollectionSchema:
    fields = [
        FieldSchema(name="id", dtype=DataType.VARCHAR, max_length=128, is_primary=True),
        FieldSchema(name="doc_id", dtype=DataType.VARCHAR, max_length=128),
        FieldSchema(name="text", dtype=DataType.VARCHAR, max_length=65535),
        FieldSchema(name="vector", dtype=DataType.FLOAT_VECTOR, dim=EMBEDDING_DIM),
        FieldSchema(name="granularity", dtype=DataType.VARCHAR, max_length=32),
        FieldSchema(name="metadata", dtype=DataType.JSON),
    ]
    return CollectionSchema(fields, description="sf-rag-kb chunks")


@dataclass
class MilvusWriter:
    collection_name: str = settings.milvus_collection
    host: str = settings.milvus_host
    port: str = settings.milvus_port
    drop_existing: bool = False

    def __post_init__(self) -> None:
        connections.connect(alias="default", host=self.host, port=self.port)
        if utility.has_collection(self.collection_name):
            if self.drop_existing:
                logger.warning(f"dropping existing collection {self.collection_name}")
                utility.drop_collection(self.collection_name)
            else:
                logger.info(f"collection {self.collection_name} already exists, reusing")
        if not utility.has_collection(self.collection_name):
            logger.info(f"creating collection {self.collection_name}")
            self.collection = Collection(self.collection_name, _milvus_schema())
            self.collection.create_index(
                field_name="vector",
                index_params={
                    "index_type": "HNSW",
                    "metric_type": "COSINE",
                    "params": {"M": 16, "efConstruction": 200},
                },
            )
        else:
            self.collection = Collection(self.collection_name)
        self.collection.load()

    def insert(self, chunks: list[Chunk], vectors: list[list[float]]) -> int:
        assert len(chunks) == len(vectors), "chunks/vectors length mismatch"
        rows = [
            {
                "id": c.id,
                "doc_id": c.doc_id,
                "text": c.text[:65535],
                "vector": v,
                "granularity": c.granularity,
                "metadata": c.metadata,
            }
            for c, v in zip(chunks, vectors)
        ]
        self.collection.insert(rows)
        return len(rows)

    def flush(self) -> int:
        self.collection.flush()
        return self.collection.num_entities


# ---------------------------------------------------------------------------
# Elasticsearch
# ---------------------------------------------------------------------------


def _es_index_body(use_ik: bool = False) -> dict:
    if use_ik:
        analyzer: dict = {"analysis": {"analyzer": {"default": {"type": "ik_smart"}}}}
        text_field: dict = {"type": "text", "analyzer": "ik_smart", "search_analyzer": "ik_smart"}
    else:
        # ADR-003: Phase 1 fallback 到 standard
        analyzer = {}
        text_field = {"type": "text", "analyzer": "standard"}
    return {
        "settings": analyzer,
        "mappings": {
            "properties": {
                "id": {"type": "keyword"},
                "doc_id": {"type": "keyword"},
                "text": text_field,
                "granularity": {"type": "keyword"},
                "metadata": {"type": "object", "dynamic": True},
            }
        },
    }


@dataclass
class ESWriter:
    index_name: str = settings.es_index
    host: str = settings.es_host
    drop_existing: bool = False
    use_ik: bool = False

    def __post_init__(self) -> None:
        self.client = Elasticsearch(self.host, request_timeout=30)
        if self.client.indices.exists(index=self.index_name):
            if self.drop_existing:
                logger.warning(f"deleting existing ES index {self.index_name}")
                self.client.indices.delete(index=self.index_name)
        if not self.client.indices.exists(index=self.index_name):
            logger.info(f"creating ES index {self.index_name} (use_ik={self.use_ik})")
            self.client.indices.create(index=self.index_name, body=_es_index_body(self.use_ik))

    def insert(self, chunks: list[Chunk]) -> int:
        actions: Iterable[dict] = (
            {
                "_index": self.index_name,
                "_id": c.id,
                "_source": {
                    "id": c.id,
                    "doc_id": c.doc_id,
                    "text": c.text,
                    "granularity": c.granularity,
                    "metadata": c.metadata,
                },
            }
            for c in chunks
        )
        success, _ = helpers.bulk(self.client, actions, raise_on_error=False, request_timeout=60)
        return success

    def refresh(self) -> int:
        self.client.indices.refresh(index=self.index_name)
        return int(self.client.count(index=self.index_name)["count"])


# ---------------------------------------------------------------------------
# DualWriter orchestrator
# ---------------------------------------------------------------------------


def write_jsonl_metadata(path: str, chunks: list[Chunk]) -> None:
    """把 chunks 元数据落盘一份(便于后续 BM25 重建 / 调试)。"""
    with open(path, "w", encoding="utf-8") as fh:
        for c in chunks:
            fh.write(json.dumps(c.model_dump(), ensure_ascii=False) + "\n")
