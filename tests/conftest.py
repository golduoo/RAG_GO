"""共享 fixture。"""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

import pytest


@pytest.fixture
def mock_embedder() -> MagicMock:
    """伪 BGEEmbedder:返回固定 3 维向量。"""
    emb = MagicMock()
    emb.encode = MagicMock(side_effect=lambda texts, **kw: [[0.1, 0.2, 0.3] for _ in texts])
    return emb


@pytest.fixture
def mock_milvus_collection() -> MagicMock:
    """伪 Milvus Collection:search() 返回 3 个 hit。"""
    col = MagicMock()

    def make_hit(idx: int, score: float, payload: dict[str, Any]):
        h = MagicMock()
        h.score = score
        h.entity = payload
        return h

    sample_hits = [
        make_hit(
            0,
            0.95,
            {
                "id": "doc-1-0",
                "doc_id": "doc-1",
                "text": "顺丰特快从上海到北京一般 1 个工作日。",
                "granularity": "paragraph",
                "metadata": {"corpus": "test"},
            },
        ),
        make_hit(
            1,
            0.88,
            {
                "id": "doc-2-0",
                "doc_id": "doc-2",
                "text": "EMS 速度比顺丰慢,价格便宜。",
                "granularity": "paragraph",
                "metadata": {"corpus": "test"},
            },
        ),
        make_hit(
            2,
            0.72,
            {
                "id": "doc-3-0",
                "doc_id": "doc-3",
                "text": "京东物流次日达覆盖一二线城市。",
                "granularity": "paragraph",
                "metadata": {"corpus": "test"},
            },
        ),
    ]
    col.search = MagicMock(return_value=[sample_hits])
    col.load = MagicMock(return_value=None)
    return col
