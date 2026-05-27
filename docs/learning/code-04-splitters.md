# 代码精读 04:`src/ingest/splitters.py`

> 把一篇长 `Document` 切成多个 `Chunk`。纯算法,无外部服务依赖。

---

## 为什么要切分(chunking)?

3 个原因:
1. **Embedding 模型有长度上限**:BGE-M3 最长 8192 token,超了被截断
2. **检索粒度**:整篇文章做一个向量太"糊",一句话又太"碎",要切到合适大小
3. **LLM context 成本**:检索回来的内容要塞进 prompt,chunk 太大浪费 token

**核心权衡**:chunk 太大 → 语义糊、召回不准;太小 → 上下文断裂、答案不全。
经验值:**300-500 token**。我们用 `chunk_size=400`。

---

## 文件结构

```
BaseSplitter(ABC)                    抽象基类:参数校验 + 通用方法
├── FixedTokenSplitter               按 token 数定长滑窗切
└── RecursiveCharacterSplitter       按分隔符层级递归切
```

---

## 1. BaseSplitter —— 抽象基类(ABC)

```python
from abc import ABC, abstractmethod

class BaseSplitter(ABC):
    def __init__(self, chunk_size=400, chunk_overlap=50, granularity="paragraph"):
        if chunk_size <= 0:
            raise ValueError(...)
        if chunk_overlap < 0:
            raise ValueError(...)
        if chunk_overlap >= chunk_size:
            raise ValueError(...)        # overlap 必须 < size,否则死循环
        ...

    @abstractmethod
    def split_text(self, text: str) -> list[str]:
        """子类必须实现。把字符串切成多段。"""

    def split_document(self, doc: Document) -> list[Chunk]:
        """通用:调 split_text 再包成 Chunk。"""
        ...
```

### ABC 是什么?
`ABC` = Abstract Base Class(抽象基类)。`@abstractmethod` 标记的方法**子类必须实现**,否则实例化报错。

**为什么用 ABC?**
- 定义"接口契约":任何 Splitter 都得有 `split_text`
- 通用逻辑(参数校验、`split_document` 包 Chunk)写一次,子类复用
- 这是**模板方法模式**:基类定骨架,子类填具体步骤

### 参数校验三连
```python
if chunk_overlap >= chunk_size:
    raise ValueError(...)
```
为什么 overlap 必须 < size?因为切分时每步前进 `size - overlap`,如果 overlap ≥ size,步长 ≤ 0,**死循环**。提前拦住。

### `split_document` —— 通用方法
```python
def split_document(self, doc: Document) -> list[Chunk]:
    pieces = self.split_text(doc.text)          # 子类的具体切法
    chunks = []
    for idx, piece in enumerate(pieces):
        chunks.append(Chunk(
            id=f"{doc.id}-{idx}",               # ← chunk id 格式
            doc_id=doc.id,
            text=piece,
            granularity=self.granularity,
            metadata={**doc.metadata, "chunk_idx": idx},   # 继承 doc 元数据 + 加序号
        ))
    return chunks
```
**关键**:`id=f"{doc.id}-{idx}"` 这个格式必须和评估集里的 `gold_doc_ids` 对得上(T1.9 就靠这个算 Recall)。

---

## 2. FixedTokenSplitter —— 定长滑窗

```python
class FixedTokenSplitter(BaseSplitter):
    def __init__(self, ..., encoding_name="cl100k_base"):
        super().__init__(...)
        import tiktoken
        self._enc = tiktoken.get_encoding(encoding_name)

    def split_text(self, text):
        if not text: return []
        tokens = self._enc.encode(text)            # 文字 -> token id 列表
        if len(tokens) <= self.chunk_size:
            return [text]                          # 短文本不切

        step = self.chunk_size - self.chunk_overlap   # 每次前进的步长
        pieces = []
        for start in range(0, len(tokens), step):
            window = tokens[start : start + self.chunk_size]
            if not window: break
            pieces.append(self._enc.decode(window))    # token -> 文字
            if start + self.chunk_size >= len(tokens):
                break
        return pieces
```

### token 是什么?
不是"字",是模型眼里的最小单位。`tiktoken` 用 BPE 算法,把文本切成 token id。
- 英文:大致 1 token ≈ 0.75 个词
- 中文:1 token ≈ 1-2 个字
- `cl100k_base` 是 GPT-3.5/4 的词表

### 滑窗 + overlap 图解
```
chunk_size=400, overlap=50, step=350

tokens: [0........400]
              [350........750]
                    [700........1100]
              ↑overlap 50↑
```
**为什么要 overlap?** 防止把一句话从中间切断后,两个 chunk 都丢失完整语义。重叠 50 token 让边界信息在两个 chunk 都保留一份。

---

## 3. RecursiveCharacterSplitter —— 递归切分(更聪明)

FixedToken 是"一刀切"(可能切碎句子)。Recursive 尽量**在自然边界**(段落 > 句子 > 词)切。

```python
DEFAULT_SEPARATORS = ("\n\n", "\n", "。", "!", "?", "！", "？", ";", "；", ",", "，", " ", "")
```
分隔符**按优先级排列**:先试段落分隔(`\n\n`),不行降级到句号,再不行降到逗号,最后字符级硬切(`""`)。

### 核心递归逻辑
```python
def _recursive_split(self, text, separators):
    if len(text) <= self.chunk_size or not separators:
        return [text]                       # 够短了 或 分隔符用完了,停
    sep = separators[0]                      # 当前级分隔符
    rest = separators[1:]                    # 剩下的(降级备用)
    if sep == "":
        # 字符级硬切兜底
        return [text[i:i+size] for i in range(0, len(text), size)]

    parts = text.split(sep)
    out = []
    for part in parts:
        piece = part + sep                   # 切的时候把分隔符加回去
        if len(piece) <= self.chunk_size:
            out.append(piece)                # 够短,留着
        else:
            out.extend(self._recursive_split(piece, rest))  # 还太长,用下一级分隔符再切
    return out
```

**直觉**:像剁排骨——先沿大骨缝(段落)剁,某块还太大就沿小骨缝(句子)剁,实在不行用刀硬切(字符)。

### merge 阶段:把碎片拼回接近 chunk_size
递归切完可能产生很多小碎片(比如一堆短句)。`_merge_with_overlap` 把相邻碎片**贪心合并**到接近 chunk_size,并在 chunk 间保留 overlap:
```python
def _merge_with_overlap(self, pieces):
    merged, buf = [], ""
    for p in pieces:
        if len(buf) + len(p) <= self.chunk_size:
            buf += p                         # 还装得下,继续攒
        else:
            merged.append(buf)               # 装满了,封一个 chunk
            tail = buf[-self.chunk_overlap:] # 取尾部做 overlap
            buf = tail + p                   # 下一个 chunk 用 overlap 开头
    if buf: merged.append(buf)
    return merged
```

---

## FixedToken vs Recursive 对比

| | FixedTokenSplitter | RecursiveCharacterSplitter |
|---|---|---|
| 切分依据 | token 数 | 自然边界(段落/句子) |
| 边界质量 | 可能切断句子 | 尽量保持完整 |
| 长度计量 | token(准确对齐模型) | 字符(中文≈token,英文偏差) |
| 速度 | 快 | 略慢(递归) |
| 我们 ingest 用 | ✅ baseline 用它 | 备选,Phase 2 多粒度可能用 |

> Phase 1 baseline 用 FixedToken(简单可复现)。Recursive 更适合做对照实验。

---

## 关键认知

1. **chunk_size 是权衡**:太大召回糊,太小语境断,400 token 是甜点
2. **overlap 防边界信息丢失**,代价是冗余存储
3. **ABC 模板方法**:基类管校验和包 Chunk,子类只管 `split_text`
4. **Recursive 按自然边界降级切分**,比一刀切更保语义
5. **chunk id 格式 `{doc_id}-{idx}`** 必须和评估集 gold_doc_ids 一致

---

## 自测题

1. `chunk_overlap=400, chunk_size=400` 会怎样?代码哪里拦住?
2. 一段 200 token 的短文本,FixedTokenSplitter 返回几个 chunk?
3. overlap 设太大(比如 300/400)有什么副作用?
4. Recursive 的 separators 里最后那个空串 `""` 是干嘛的?去掉会怎样?
5. 为什么 chunk id 要用 `{doc_id}-{idx}` 而不是随机 UUID?

---

## 可改进 / 生产实践

- **语义切分(semantic chunking)**:用 embedding 相似度找"语义断点"切,比规则更智能(但慢)
- **按 markdown 结构切**:技术文档按标题层级切,保留章节结构
- **chunk 带"标题前缀"**:每个 chunk 前面拼上所属章节标题,提升检索命中(small-to-big)
- **表格/代码块特殊处理**:别把表格从中间切断
