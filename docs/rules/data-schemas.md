# Rules: Data Schemas 🔒

> **何时读**:定义或使用 Document / Chunk / RetrievedDoc / EvalSample 等数据结构。
> 🔒 = 锁定章节,变更必须先写 ADR。

---

## 1. 核心数据类型 🔒

所有数据类型用 Pydantic v2 BaseModel,定义在 `src/ingest/schema.py`。

```python
"""核心数据结构定义。"""

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
```

---

## 2. 评估集格式 🔒

`data/eval/*.jsonl`,每行一个 JSON 对象:

```json
{
  "qid": "q_001",
  "question": "顺丰特快从上海到北京一般几天到?",
  "gold_answer": "通常 1-2 个工作日。",
  "gold_doc_ids": ["doc_123", "doc_456"],
  "question_type": "single_hop",
  "metadata": {
    "category": "时效查询",
    "difficulty": "easy"
  }
}
```

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `qid` | str | ✓ | 全局唯一 |
| `question` | str | ✓ | |
| `gold_answer` | str | ✓ | 标准答案 |
| `gold_doc_ids` | list[str] | ✓ | 标准答案来源的 chunk ID 列表(可以多个) |
| `question_type` | Literal | ✓ | `single_hop` / `multi_hop` / `yesno` / `chat` |
| `metadata` | dict | | 自由字段 |

对应 Pydantic 模型放 `src/eval/schema.py`。

---

## 3. Milvus Collection Schema 🔒

```python
# Collection: chunks_v{version}
{
    "fields": [
        {"name": "id", "type": "VARCHAR", "max_length": 128, "is_primary": True},
        {"name": "doc_id", "type": "VARCHAR", "max_length": 128},
        {"name": "text", "type": "VARCHAR", "max_length": 65535},
        {"name": "vector", "type": "FLOAT_VECTOR", "dim": 1024},  # bge-m3 是 1024 维
        {"name": "granularity", "type": "VARCHAR", "max_length": 32},
        {"name": "metadata", "type": "JSON"},
    ],
    "index": {
        "field": "vector",
        "type": "HNSW",
        "params": {"M": 16, "efConstruction": 200},
        "metric": "COSINE",
    },
}
```

### Collection 命名约定
- 格式:`chunks_v{N}` 或 `chunks_{phase}_{N}`
- 不同切分策略或不同 embedding 模型 → **新建 collection**,不要覆盖
- 每次 ingest 在 `docs/metrics.md` 记录 collection 名 + 行数 + 配置

---

## 4. Elasticsearch Index Schema 🔒

```json
{
  "settings": {
    "analysis": {
      "analyzer": {
        "default": {"type": "ik_smart"}
      }
    }
  },
  "mappings": {
    "properties": {
      "id":          {"type": "keyword"},
      "doc_id":      {"type": "keyword"},
      "text":        {"type": "text", "analyzer": "ik_smart", "search_analyzer": "ik_smart"},
      "granularity": {"type": "keyword"},
      "metadata":    {"type": "object", "dynamic": true}
    }
  }
}
```

> 注:若 `ik_smart` 未安装,fallback 用 `standard` analyzer,但要在 ADR 中记录。

---

## 5. Neo4j 图谱 Schema 🔒(Phase 4)

### 节点类型
| Label | Properties | 示例 |
|-------|-----------|------|
| `Service` | `name, type, price_base` | 顺丰特快 |
| `City` | `name, level` | 上海 |
| `Rule` | `name, description, doc_id` | 偏远地区附加费 |
| `Penalty` | `name, amount, condition` | 延误赔付 |

### 关系类型
| Type | 起点 → 终点 | 含义 |
|------|------------|------|
| `COVERS` | Service → City | 服务覆盖城市 |
| `APPLIES_TO` | Rule → Service | 规则适用于服务 |
| `TRIGGERS` | Rule → Penalty | 规则触发赔付 |
| `CONNECTS` | City → City | 城市间运输线路 |

### 实体唯一性
- 每个节点用 `(label, name)` 唯一约束
- 创建用 `MERGE`,不要用 `CREATE`(避免重复)

---

## 6. 数据流约定

```
原始文件                  Document jsonl              Chunk + Milvus/ES
┌──────────┐  loaders   ┌──────────────┐  splitter+   ┌─────────────────┐
│ raw/*.pdf│ ─────────▶ │ processed/   │  indexer     │ Milvus collection│
│ raw/*.md │            │  *.jsonl     │ ───────────▶ │ ES index        │
└──────────┘            └──────────────┘              └─────────────────┘
                                                              │
                          Question + gold                     │ retrieve
                          ┌──────────────┐                    ▼
                          │ eval/*.jsonl │             RetrievedDoc[]
                          └──────────────┘                    │
                                                              │ rerank+gen
                                                              ▼
                                                          Answer
```

**强约定**:
- `data/raw/` 永远不修改,只读
- `data/processed/` 是中间产物,可重新生成
- 任何中间产物要可以从 raw 一键复现(`scripts/` 下有对应脚本)
