# 代码精读 03:`src/ingest/schema.py`

> 整个项目的"数据骨架"。用 Pydantic 定义 4 个核心数据类型,贯穿 ingest → retrieve → generate。

---

## 全文

```python
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
    rank: int | None = None


class Answer(BaseModel):
    """RAG 生成的答案。"""
    query: str
    answer: str
    citations: list[RetrievedDoc] = Field(default_factory=list)
    confidence: float | None = None
    intent: str | None = None
```

---

## 数据如何在系统里流动

```
原始语料        → Document   (id, text, source, metadata)
  │ splitter
  ▼
切分单元        → Chunk      (id="{doc_id}-{idx}", doc_id, text, granularity)
  │ embed + 入库 Milvus/ES
  ▼
检索            → RetrievedDoc (id, text, score, source, rank)
  │ LLM 生成
  ▼
最终答案        → Answer     (query, answer, citations=[RetrievedDoc])
```

**这就是为什么先讲 schema**:后面每个文件都在生产/消费这 4 个类型。

---

## Pydantic 是什么?为什么用它?

Pydantic = **数据验证 + 序列化**库。你声明字段类型,它自动:
1. **校验**:传错类型/缺字段直接报错,不会带病运行
2. **转换**:`"123"` 自动转 `int` 123(可配置)
3. **序列化**:`.model_dump()` → dict,`.model_dump_json()` → JSON 字符串

对比裸 dict:
```python
# 裸 dict:没人拦着你写错
d = {"id": "x", "txt": "..."}   # 拼错 text -> txt,运行时才炸

# Pydantic:定义即合同
Document(id="x", txt="...")     # 立刻报错:缺 text,多了 txt
```

---

## 逐字段讲解

### `Field(..., description=...)`
- **`...`(Ellipsis)** 表示**必填**。不传就报 `ValidationError`。
- `description` 是文档说明,生成 JSON Schema / OpenAPI 文档时会用到。

```python
id: str = Field(..., description="全局唯一 ID")  # 必填
text: str                                        # 也是必填(无默认值)
```
`text: str` 没写 `Field` 也是必填——**没有默认值 = 必填**。

### `Field(default_factory=dict)` ⚠️ 重要的坑
```python
metadata: dict = Field(default_factory=dict)
```
**为什么不直接写 `metadata: dict = {}`?**

因为 Python 的**可变默认参数陷阱**:`= {}` 会让**所有实例共享同一个 dict 对象**,一个实例改了,全都变。

```python
# 错误示范(裸 Python)
def f(x, items=[]):     # 所有调用共享同一个 list!
    items.append(x)
    return items
f(1)  # [1]
f(2)  # [1, 2]  ← 惊不惊喜

# 正确:default_factory 每次新建
metadata: dict = Field(default_factory=dict)  # 每个实例独立的 dict
```
`default_factory=dict` 意思是"每次创建实例时,调用 `dict()` 生成一个新空字典"。

### `Literal[...]` — 枚举式类型约束
```python
Granularity = Literal["title", "paragraph", "sentence", "qa"]
```
意思:`granularity` 字段**只能**是这 4 个字符串之一。传别的(如 `"word"`)直接 `ValidationError`。

好处:
- IDE 自动补全
- 防手滑拼错(`"paragaph"` 立刻报错)
- 比 `str` 更精确地表达意图

我们有两个这种枚举:
- `Granularity`:切分粒度(Phase 2 多粒度会用全)
- `RetrievalSource`:检索来源(`dense` 现在用,`bm25`/`hybrid` Phase 2 用)

### `int | None = None` — 可选字段
```python
rank: int | None = None
```
`int | None` 是 Python 3.10+ 的 union 语法(等价老写法 `Optional[int]`)。
意思:可以是 int,也可以是 None,默认 None。

`rank` 为什么可选?因为不是所有检索结果都关心排名,Dense 检索我们填了(0,1,2...),别的路可能不填。

### 嵌套模型
```python
class Answer(BaseModel):
    citations: list[RetrievedDoc] = Field(default_factory=list)
```
`Answer` 里嵌套了一个 `RetrievedDoc` 列表。Pydantic 会**递归校验**:列表里每个元素都必须是合法的 `RetrievedDoc`。

---

## 这些模型怎么用(对照你写过的代码)

```python
# splitters.py 里生产 Chunk
Chunk(id=f"{doc.id}-{idx}", doc_id=doc.id, text=piece, granularity="paragraph")

# dense.py 里生产 RetrievedDoc
RetrievedDoc(id=..., text=..., score=hit.score, source="dense", rank=rank)

# pipeline.py 里生产 Answer
Answer(query=query, answer=answer_text, citations=hits)

# 序列化:写 jsonl 时
json.dumps(doc.model_dump(), ensure_ascii=False)
```

### `model_dump()` vs `model_dump_json()`
- `model_dump()` → Python dict
- `model_dump_json()` → JSON 字符串(但不能加 `ensure_ascii` 参数,所以我们用 `json.dumps(model_dump(), ensure_ascii=False)` 来正确输出中文)

> 这正是 T1.3 写 filter 脚本时踩过的坑:`model_dump_json(ensure_ascii=False)` 报错,改成 `json.dumps(model_dump(), ...)`。

---

## 关键认知

1. **schema 是数据合同**:4 个类型贯穿全流程,改 schema = 改全局接口(所以 data-schemas.md 是 🔒 锁定章节)
2. **`Field(...)` = 必填,`default_factory` = 安全的可变默认值**
3. **`Literal` = 枚举约束**,防手滑 + IDE 补全
4. **Pydantic 递归校验嵌套模型**

---

## 自测题

1. `Document(id="x", text="hi")` 不传 source 会怎样?
2. 为什么 `metadata: dict = {}` 是 bug,`Field(default_factory=dict)` 不是?
3. `Chunk(..., granularity="word")` 会发生什么?
4. `Answer` 的 `citations` 里塞一个 `{"foo": 1}`(不是 RetrievedDoc),Pydantic 会接受吗?
5. 写 jsonl 时为什么用 `json.dumps(model_dump(), ensure_ascii=False)` 而不是 `model_dump_json()`?

---

## 可改进 / 生产实践

- 可以给字段加**校验器**:`@field_validator("score")` 限制 score 在 [0,1]
- `model_config = ConfigDict(frozen=True)` 让模型也不可变(适合 RetrievedDoc 这种检索结果)
- 大文本字段可以加 `Field(max_length=...)` 防止超长
- Pydantic v2 比 v1 快很多(核心用 Rust 重写),注意别混用两版 API
