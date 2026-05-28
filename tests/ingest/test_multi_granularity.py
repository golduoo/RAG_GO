"""multi_granularity.py 的单元测试。"""

from __future__ import annotations

from src.ingest.multi_granularity import (
    MultiGranularitySplitter,
    detect_table,
    detect_titles,
    split_sentences,
)
from src.ingest.schema import Document


# ---------------------------------------------------------------------------
# 纯函数:句子切分 / 标题 / 表格识别
# ---------------------------------------------------------------------------


class TestSplitSentences:
    def test_empty(self):
        assert split_sentences("") == []

    def test_splits_on_chinese_punct(self):
        out = split_sentences("第一句。第二句!第三句?", max_len=5)
        assert out == ["第一句。", "第二句!", "第三句?"]

    def test_merges_to_max_len(self):
        out = split_sentences("甲。乙。丙。丁。", max_len=100)
        # 都很短,应合并成一块
        assert out == ["甲。乙。丙。丁。"]

    def test_respects_max_len(self):
        text = "".join(f"句子{i}。" for i in range(20))
        out = split_sentences(text, max_len=12)
        assert len(out) >= 2
        assert all(len(c) <= 12 + 4 for c in out)  # 单句可能略超 max


class TestDetectTitles:
    def test_markdown_headers(self):
        text = "# 顺丰服务\n正文段落\n## 时效说明\n更多正文"
        assert detect_titles(text) == ["顺丰服务", "时效说明"]

    def test_chinese_chapter(self):
        text = "第一章 总则\n内容\n第二条 适用范围\n内容"
        titles = detect_titles(text)
        assert "第一章 总则" in titles and "第二条 适用范围" in titles

    def test_no_titles_in_plain_text(self):
        assert detect_titles("这是一段没有标题的普通文本。还有一句。") == []


class TestDetectTable:
    def test_markdown_table(self):
        text = "| 城市 | 时效 |\n| 上海 | 1天 |\n| 北京 | 2天 |"
        assert detect_table(text) is True

    def test_tab_separated(self):
        text = "城市\t时效\n上海\t1天\n北京\t2天"
        assert detect_table(text) is True

    def test_plain_text_not_table(self):
        assert detect_table("普通段落,没有表格结构。") is False


# ---------------------------------------------------------------------------
# MultiGranularitySplitter
# ---------------------------------------------------------------------------


def _doc(text: str, **md) -> Document:
    return Document(id="doc-1", text=text, source="test", metadata=md)


class TestMultiGranularitySplitter:
    def test_empty_doc_no_chunks(self):
        sp = MultiGranularitySplitter()
        assert sp.split_document(_doc("   ")) == []

    def test_plain_text_paragraph_and_sentence(self):
        text = "顺丰特快从上海到北京通常一天到。退货需在七天内申请。" * 10
        sp = MultiGranularitySplitter()
        chunks = sp.split_document(_doc(text))
        grans = {c.granularity for c in chunks}
        # 纯文本无标题,应有 paragraph 和 sentence 两级
        assert "paragraph" in grans
        assert "sentence" in grans
        assert "title" not in grans

    def test_chunk_ids_unique_and_formatted(self):
        text = "甲句。乙句。丙句。" * 20
        sp = MultiGranularitySplitter()
        chunks = sp.split_document(_doc(text))
        ids = [c.id for c in chunks]
        assert len(ids) == len(set(ids))
        assert all(c.id == f"doc-1-{c.metadata['chunk_idx']}" for c in chunks)
        assert all(c.doc_id == "doc-1" for c in chunks)

    def test_title_level(self):
        text = "# 时效政策\n顺丰特快当日达。次日达覆盖全国主要城市。"
        sp = MultiGranularitySplitter()
        chunks = sp.split_document(_doc(text))
        titles = [c for c in chunks if c.granularity == "title"]
        assert len(titles) == 1
        assert titles[0].text == "时效政策"

    def test_levels_filter(self):
        text = "甲句。乙句。丙句。" * 20
        sp = MultiGranularitySplitter(levels=("sentence",))
        chunks = sp.split_document(_doc(text))
        assert {c.granularity for c in chunks} == {"sentence"}

    def test_faq_question_as_index(self):
        sp = MultiGranularitySplitter()
        doc = _doc(
            "顺丰特快上海到北京通常一天到。",
            qa=True,
            question="顺丰从上海到北京要几天?",
            answer="通常 1 个工作日。",
        )
        chunks = sp.split_document(doc)
        assert len(chunks) == 1
        c = chunks[0]
        assert c.granularity == "qa"
        assert c.text == "顺丰从上海到北京要几天?"
        assert c.metadata["answer"] == "通常 1 个工作日。"

    def test_table_kept_whole_and_summarized(self):
        table = "| 城市 | 时效 |\n| 上海 | 1天 |\n| 北京 | 2天 |"
        sp = MultiGranularitySplitter(table_summarizer=lambda t: "上海1天北京2天")
        chunks = sp.split_document(_doc(table))
        kept = [c for c in chunks if c.metadata.get("is_table")]
        summary = [c for c in chunks if c.metadata.get("is_table_summary")]
        assert len(kept) == 1 and kept[0].text == table
        assert len(summary) == 1 and summary[0].text == "上海1天北京2天"
        assert summary[0].granularity == "paragraph"

    def test_table_without_summarizer(self):
        table = "| 城市 | 时效 |\n| 上海 | 1天 |\n| 北京 | 2天 |"
        sp = MultiGranularitySplitter(table_summarizer=None)
        chunks = sp.split_document(_doc(table))
        assert any(c.metadata.get("is_table") for c in chunks)
        assert not any(c.metadata.get("is_table_summary") for c in chunks)

    def test_split_documents_batch(self):
        docs = [_doc("一句话。两句话。") for _ in range(3)]
        # 不同 id 才能保证全局唯一;改 id
        for i, d in enumerate(docs):
            d.id = f"doc-{i}"
        sp = MultiGranularitySplitter()
        out = sp.split_documents(docs)
        assert len(out) >= 3
        assert len({c.id for c in out}) == len(out)
