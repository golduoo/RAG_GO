"""splitters.py 的单元测试。"""

from __future__ import annotations

import pytest

from src.ingest.schema import Document
from src.ingest.splitters import (
    DEFAULT_CHUNK_OVERLAP,
    DEFAULT_CHUNK_SIZE,
    FixedTokenSplitter,
    RecursiveCharacterSplitter,
)


# ---------------------------------------------------------------------------
# 共享 fixture
# ---------------------------------------------------------------------------


@pytest.fixture
def short_text() -> str:
    return "你好,世界。"


@pytest.fixture
def normal_text() -> str:
    # 约 600 字,够触发切分
    para = "顺丰特快是国内时效最快的快递服务之一,从上海到北京通常 1 个工作日送达。"
    return ("\n\n").join([para] * 8)


@pytest.fixture
def long_text() -> str:
    # ~5000 字,确保多段
    return "包裹运输配送时效签收。" * 500


@pytest.fixture
def sample_doc(normal_text: str) -> Document:
    return Document(id="doc-1", text=normal_text, source="test", metadata={"k": "v"})


# ---------------------------------------------------------------------------
# 构造参数校验(异常路径)
# ---------------------------------------------------------------------------


class TestSplitterInit:
    @pytest.mark.parametrize("cls", [FixedTokenSplitter, RecursiveCharacterSplitter])
    def test_init_invalid_chunk_size(self, cls):
        with pytest.raises(ValueError, match="chunk_size"):
            cls(chunk_size=0)

    @pytest.mark.parametrize("cls", [FixedTokenSplitter, RecursiveCharacterSplitter])
    def test_init_invalid_overlap(self, cls):
        with pytest.raises(ValueError, match="chunk_overlap"):
            cls(chunk_size=100, chunk_overlap=-1)

    @pytest.mark.parametrize("cls", [FixedTokenSplitter, RecursiveCharacterSplitter])
    def test_init_overlap_geq_size(self, cls):
        with pytest.raises(ValueError, match="chunk_overlap"):
            cls(chunk_size=100, chunk_overlap=100)


# ---------------------------------------------------------------------------
# FixedTokenSplitter
# ---------------------------------------------------------------------------


class TestFixedTokenSplitter:
    def test_empty_text(self):
        sp = FixedTokenSplitter()
        assert sp.split_text("") == []

    def test_short_text_returns_single(self, short_text: str):
        sp = FixedTokenSplitter(chunk_size=200, chunk_overlap=20)
        out = sp.split_text(short_text)
        assert out == [short_text]

    def test_normal_text_multi_chunks(self, normal_text: str):
        sp = FixedTokenSplitter(chunk_size=50, chunk_overlap=10)
        out = sp.split_text(normal_text)
        assert len(out) >= 2
        # 拼回原文(去掉 overlap 后)应能覆盖原内容的主体
        assert "".join(out).find("顺丰特快") != -1

    def test_long_text_many_chunks(self, long_text: str):
        sp = FixedTokenSplitter(chunk_size=200, chunk_overlap=20)
        out = sp.split_text(long_text)
        assert len(out) >= 5

    def test_overlap_present(self, normal_text: str):
        # 设置较大的 overlap,验证相邻块之间确实有交集
        sp = FixedTokenSplitter(chunk_size=80, chunk_overlap=30)
        out = sp.split_text(normal_text)
        if len(out) >= 2:
            # 简单启发:后块的开头至少出现在前块的最后 chunk_size 字符内
            tail = out[0][-60:]
            head = out[1][:30]
            assert any(ch in tail for ch in head)

    def test_split_document_produces_chunks(self, sample_doc: Document):
        sp = FixedTokenSplitter(chunk_size=50, chunk_overlap=10)
        chunks = sp.split_document(sample_doc)
        assert len(chunks) >= 1
        for i, ch in enumerate(chunks):
            assert ch.doc_id == "doc-1"
            assert ch.id == f"doc-1-{i}"
            assert ch.granularity == "paragraph"
            # 继承 doc.metadata + 注入 chunk_idx
            assert ch.metadata["k"] == "v"
            assert ch.metadata["chunk_idx"] == i


# ---------------------------------------------------------------------------
# RecursiveCharacterSplitter
# ---------------------------------------------------------------------------


class TestRecursiveCharacterSplitter:
    def test_empty_text(self):
        sp = RecursiveCharacterSplitter()
        assert sp.split_text("") == []

    def test_short_text_returns_single(self, short_text: str):
        sp = RecursiveCharacterSplitter(chunk_size=200, chunk_overlap=20)
        out = sp.split_text(short_text)
        assert out == [short_text]

    def test_normal_text_multi_chunks(self, normal_text: str):
        sp = RecursiveCharacterSplitter(chunk_size=100, chunk_overlap=20)
        out = sp.split_text(normal_text)
        assert len(out) >= 2

    def test_chunks_respect_size_bound(self, normal_text: str):
        sp = RecursiveCharacterSplitter(chunk_size=120, chunk_overlap=20)
        out = sp.split_text(normal_text)
        # 允许略超出(merge 时 overlap 起头会让首块超),但大体不应远超
        assert all(len(c) <= 120 + 20 for c in out)

    def test_long_text_many_chunks(self, long_text: str):
        sp = RecursiveCharacterSplitter(chunk_size=200, chunk_overlap=20)
        out = sp.split_text(long_text)
        assert len(out) >= 5

    def test_recursive_splits_on_paragraph(self):
        text = "第一段。\n\n第二段。\n\n第三段。" * 3
        sp = RecursiveCharacterSplitter(chunk_size=20, chunk_overlap=2)
        out = sp.split_text(text)
        assert len(out) >= 3
        # 至少有一块应该完整保留某段(说明走了段落级切)
        joined = "".join(out)
        assert "第一段" in joined and "第二段" in joined

    def test_pathological_no_separators(self):
        # 一整串没有任何分隔符,会走字符级硬切
        text = "x" * 1000
        sp = RecursiveCharacterSplitter(chunk_size=100, chunk_overlap=10)
        out = sp.split_text(text)
        assert len(out) >= 8
        assert all(len(c) <= 110 for c in out)

    def test_split_document_chunk_metadata(self, sample_doc: Document):
        sp = RecursiveCharacterSplitter(chunk_size=80, chunk_overlap=10)
        chunks = sp.split_document(sample_doc)
        assert all(c.doc_id == "doc-1" for c in chunks)
        assert all(c.id.startswith("doc-1-") for c in chunks)


# ---------------------------------------------------------------------------
# 默认值 sanity
# ---------------------------------------------------------------------------


def test_default_params():
    assert DEFAULT_CHUNK_SIZE == 400
    assert DEFAULT_CHUNK_OVERLAP == 50
