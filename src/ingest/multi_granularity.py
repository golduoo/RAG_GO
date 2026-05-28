"""多粒度切分器:把一个 Document 切成多级 Chunk(对齐 phase-2.md T2.1)。

三级 + 两个特例:
- ``title``:正则识别标题行(markdown ``#`` 或``第N章/节/条``)
- ``paragraph``:复用 ``RecursiveCharacterSplitter``,粗粒度段落块
- ``sentence``:按中文句末标点切句,贪心合并到 ``sentence_max`` 字符,细粒度
- FAQ(``metadata["qa"]`` 为真):Question-as-Index,text 存 question 用于算向量,
  metadata 存 answer,granularity=``qa``
- 表格(``detect_table`` 命中):整块保留为 paragraph,并(若提供 summarizer)额外生成
  一条 LLM 摘要块,metadata 标 ``is_table_summary=True``

设计:同一 doc 内所有粒度共用一个自增计数,chunk id 形如 ``{doc_id}-{i}`` 保证唯一。
"""

from __future__ import annotations

import re
from collections.abc import Callable, Iterable

from src.ingest.schema import Chunk, Document, Granularity
from src.ingest.splitters import RecursiveCharacterSplitter

DEFAULT_PARAGRAPH_SIZE = 400
DEFAULT_PARAGRAPH_OVERLAP = 50
DEFAULT_SENTENCE_MAX = 150

# 句末标点(中英)。用 lookbehind 切分,保留标点在句尾。
_SENTENCE_SPLIT = re.compile(r"(?<=[。！？!?；;])")
# 标题行:markdown 标题,或中文“第X章/节/条”。
_TITLE_LINE = re.compile(
    r"^\s*(#{1,6}\s+\S.*|第[一二三四五六七八九十百\d]+[章节条]\b.*)$"
)
# 表格行:markdown 竖线表,或制表符分隔。
_TABLE_ROW = re.compile(r"^\s*\|.*\|\s*$|^[^\t\n]+(\t[^\t\n]+)+$")

Summarizer = Callable[[str], str]


def detect_titles(text: str) -> list[str]:
    """抽取文本中的标题行,去掉 markdown ``#`` 前缀。"""
    titles: list[str] = []
    for line in text.splitlines():
        m = _TITLE_LINE.match(line)
        if m:
            titles.append(re.sub(r"^\s*#{1,6}\s+", "", line).strip())
    return titles


def detect_table(text: str) -> bool:
    """判断文本是否像表格:连续两行及以上的表格行。"""
    rows = [ln for ln in text.splitlines() if _TABLE_ROW.match(ln)]
    return len(rows) >= 2


def split_sentences(text: str, max_len: int = DEFAULT_SENTENCE_MAX) -> list[str]:
    """按句末标点切句,贪心合并相邻句到 ``max_len`` 字符以内。"""
    if not text:
        return []
    parts = [p.strip() for p in _SENTENCE_SPLIT.split(text) if p.strip()]
    out: list[str] = []
    buf = ""
    for p in parts:
        if buf and len(buf) + len(p) > max_len:
            out.append(buf)
            buf = p
        else:
            buf += p
    if buf:
        out.append(buf)
    return out


class MultiGranularitySplitter:
    """把 Document 切成 title / paragraph / sentence(及 qa / 表格摘要)多级 Chunk。"""

    def __init__(
        self,
        paragraph_size: int = DEFAULT_PARAGRAPH_SIZE,
        paragraph_overlap: int = DEFAULT_PARAGRAPH_OVERLAP,
        sentence_max: int = DEFAULT_SENTENCE_MAX,
        levels: tuple[Granularity, ...] = ("title", "paragraph", "sentence"),
        table_summarizer: Summarizer | None = None,
    ) -> None:
        self.levels = levels
        self.sentence_max = sentence_max
        self.table_summarizer = table_summarizer
        self._para = RecursiveCharacterSplitter(
            chunk_size=paragraph_size,
            chunk_overlap=paragraph_overlap,
            granularity="paragraph",
        )

    def split_document(self, doc: Document) -> list[Chunk]:
        if not doc.text.strip():
            return []

        chunks: list[Chunk] = []
        counter = 0

        def emit(text: str, gran: Granularity, extra: dict | None = None) -> None:
            nonlocal counter
            if not text.strip():
                return
            md = {**doc.metadata, "chunk_idx": counter}
            if extra:
                md.update(extra)
            chunks.append(
                Chunk(
                    id=f"{doc.id}-{counter}",
                    doc_id=doc.id,
                    text=text,
                    granularity=gran,
                    metadata=md,
                )
            )
            counter += 1

        # FAQ:Question-as-Index,直接返回,不再做多粒度
        if doc.metadata.get("qa"):
            question = str(doc.metadata.get("question", "")).strip()
            answer = str(doc.metadata.get("answer", doc.text)).strip()
            emit(question or doc.text, "qa", {"answer": answer})
            return chunks

        if "title" in self.levels:
            for t in detect_titles(doc.text):
                emit(t, "title")

        # 表格:整块保留 + 可选摘要块
        if detect_table(doc.text):
            emit(doc.text, "paragraph", {"is_table": True})
            if self.table_summarizer is not None:
                summary = self.table_summarizer(doc.text).strip()
                emit(summary, "paragraph", {"is_table_summary": True})
        elif "paragraph" in self.levels:
            for piece in self._para.split_text(doc.text):
                emit(piece, "paragraph")

        if "sentence" in self.levels:
            for s in split_sentences(doc.text, self.sentence_max):
                emit(s, "sentence")

        return chunks

    def split_documents(self, docs: Iterable[Document]) -> list[Chunk]:
        out: list[Chunk] = []
        for d in docs:
            out.extend(self.split_document(d))
        return out
