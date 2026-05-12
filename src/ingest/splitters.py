"""文档切分器:把 Document 切成 Chunk。

实现两种 baseline:
- ``FixedTokenSplitter``:按 token 数定长切分,带 overlap。tokenizer 用 ``tiktoken``
  的 ``cl100k_base``(GPT-3.5/4 词表,对中文按字节切但 chunk 边界稳定)。
- ``RecursiveCharacterSplitter``:沿一组分隔符递归切。优先在段落 → 句子 → 子句 → 字符
  级别切,尽量保持语义边界。

默认参数(对齐 ``docs/tasks/phase-1.md`` T1.4):``chunk_size=400, chunk_overlap=50``。
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Iterable

from src.ingest.schema import Chunk, Document, Granularity


DEFAULT_CHUNK_SIZE = 400
DEFAULT_CHUNK_OVERLAP = 50

# 中文优先 + 英文/通用 fallback
DEFAULT_SEPARATORS: tuple[str, ...] = (
    "\n\n",   # 段落
    "\n",     # 行
    "。",     # 中文句号
    "!",
    "?",
    "！",
    "？",
    ";",
    "；",
    ",",
    "，",
    " ",
    "",       # 字符级兜底
)


class BaseSplitter(ABC):
    """切分器基类。子类只需实现 ``split_text``,负责把字符串切成多段。"""

    def __init__(
        self,
        chunk_size: int = DEFAULT_CHUNK_SIZE,
        chunk_overlap: int = DEFAULT_CHUNK_OVERLAP,
        granularity: Granularity = "paragraph",
    ) -> None:
        if chunk_size <= 0:
            raise ValueError(f"chunk_size must be > 0, got {chunk_size}")
        if chunk_overlap < 0:
            raise ValueError(f"chunk_overlap must be >= 0, got {chunk_overlap}")
        if chunk_overlap >= chunk_size:
            raise ValueError(
                f"chunk_overlap ({chunk_overlap}) must be < chunk_size ({chunk_size})"
            )
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap
        self.granularity: Granularity = granularity

    @abstractmethod
    def split_text(self, text: str) -> list[str]:
        """把单段文本切成多段。空字符串返回空列表。"""

    def split_document(self, doc: Document) -> list[Chunk]:
        """把单个 Document 切成 Chunk 列表。"""
        pieces = self.split_text(doc.text)
        chunks: list[Chunk] = []
        for idx, piece in enumerate(pieces):
            chunks.append(
                Chunk(
                    id=f"{doc.id}-{idx}",
                    doc_id=doc.id,
                    text=piece,
                    granularity=self.granularity,
                    metadata={**doc.metadata, "chunk_idx": idx},
                )
            )
        return chunks

    def split_documents(self, docs: Iterable[Document]) -> list[Chunk]:
        out: list[Chunk] = []
        for d in docs:
            out.extend(self.split_document(d))
        return out


# ---------------------------------------------------------------------------
# Fixed-token splitter
# ---------------------------------------------------------------------------


class FixedTokenSplitter(BaseSplitter):
    """按固定 token 数切,带 overlap。默认用 ``cl100k_base``。"""

    def __init__(
        self,
        chunk_size: int = DEFAULT_CHUNK_SIZE,
        chunk_overlap: int = DEFAULT_CHUNK_OVERLAP,
        encoding_name: str = "cl100k_base",
        granularity: Granularity = "paragraph",
    ) -> None:
        super().__init__(chunk_size, chunk_overlap, granularity)
        # 延迟 import,tiktoken 体积小但避免顶层 import 影响别的模块
        import tiktoken

        self._enc = tiktoken.get_encoding(encoding_name)

    def split_text(self, text: str) -> list[str]:
        if not text:
            return []
        tokens = self._enc.encode(text)
        if len(tokens) <= self.chunk_size:
            return [text]

        step = self.chunk_size - self.chunk_overlap
        pieces: list[str] = []
        for start in range(0, len(tokens), step):
            window = tokens[start : start + self.chunk_size]
            if not window:
                break
            pieces.append(self._enc.decode(window))
            if start + self.chunk_size >= len(tokens):
                break
        return pieces


# ---------------------------------------------------------------------------
# Recursive character splitter
# ---------------------------------------------------------------------------


class RecursiveCharacterSplitter(BaseSplitter):
    """按一组分隔符递归切分,尽量保持语义边界。

    长度按"字符数"计;chunk_size/chunk_overlap 也理解为字符。
    对中文友好(1 字 1 单位),英文略宽松(单词长度变化)。
    """

    def __init__(
        self,
        chunk_size: int = DEFAULT_CHUNK_SIZE,
        chunk_overlap: int = DEFAULT_CHUNK_OVERLAP,
        separators: tuple[str, ...] = DEFAULT_SEPARATORS,
        granularity: Granularity = "paragraph",
    ) -> None:
        super().__init__(chunk_size, chunk_overlap, granularity)
        self.separators = separators

    def split_text(self, text: str) -> list[str]:
        if not text:
            return []
        if len(text) <= self.chunk_size:
            return [text]
        pieces = self._recursive_split(text, self.separators)
        return self._merge_with_overlap(pieces)

    def _recursive_split(self, text: str, separators: tuple[str, ...]) -> list[str]:
        """递归按分隔符切,直到所有片段 <= chunk_size 或用完分隔符。"""
        if len(text) <= self.chunk_size or not separators:
            return [text]
        sep = separators[0]
        rest = separators[1:]
        if sep == "":
            # 字符级硬切兜底
            return [text[i : i + self.chunk_size] for i in range(0, len(text), self.chunk_size)]

        parts = text.split(sep)
        out: list[str] = []
        for part in parts:
            piece = part + sep if part != parts[-1] else part
            if not piece:
                continue
            if len(piece) <= self.chunk_size:
                out.append(piece)
            else:
                out.extend(self._recursive_split(piece, rest))
        return out

    def _merge_with_overlap(self, pieces: list[str]) -> list[str]:
        """把小片段合并到接近 chunk_size,相邻 chunk 之间保留 overlap。"""
        if not pieces:
            return []
        merged: list[str] = []
        buf = ""
        for p in pieces:
            if not buf:
                buf = p
                continue
            if len(buf) + len(p) <= self.chunk_size:
                buf += p
            else:
                merged.append(buf)
                # 用 buf 的尾部 overlap 起头
                tail = buf[-self.chunk_overlap :] if self.chunk_overlap else ""
                buf = tail + p
        if buf:
            merged.append(buf)
        return merged
