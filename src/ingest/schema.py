"""核心数据结构定义(对齐 docs/rules/data-schemas.md §1)。"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class Document(BaseModel):
    """原始文档,数据集中的一条记录。"""

    id: str = Field(..., description="全局唯一 ID")
    text: str
    source: str = Field(..., description="文件路径或 URL")
    metadata: dict = Field(default_factory=dict)


Granularity = Literal["title", "paragraph", "sentence", "qa"]


class Chunk(BaseModel):
    """文档切分后的最小检索单元。"""

    id: str = Field(..., description='格式: "{doc_id}-{chunk_idx}"')
    doc_id: str
    text: str
    granularity: Granularity
    metadata: dict = Field(default_factory=dict)


RetrievalSource = Literal["dense", "bm25", "hybrid", "graph", "rerank"]


class RetrievedDoc(BaseModel):
    """检索结果。"""

    id: str
    text: str
    score: float
    source: RetrievalSource
    metadata: dict = Field(default_factory=dict)
    rank: int | None = None  # 在该路检索中的排名,0-indexed


class Answer(BaseModel):
    """RAG 生成的答案。"""

    query: str
    answer: str
    citations: list[RetrievedDoc] = Field(default_factory=list)
    confidence: float | None = None
    intent: str | None = None
