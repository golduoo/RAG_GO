# 代码精读 05:`src/ingest/indexer.py`

> ingest 的心脏:把 Chunk 变成向量(BGE-M3),双写进 Milvus(向量)+ ES(全文)。

---

## 文件全貌

```
BGEEmbedder        文字 → 1024 维向量(GPU/CPU)
_milvus_schema()   定义 Milvus collection 的字段结构
MilvusWriter       建 collection + 建索引 + 插入 + flush
_es_index_body()   定义 ES index 的 mapping
ESWriter           建 index + bulk 插入 + refresh
write_jsonl_metadata()  把 chunks 落盘备份
```

为什么 Milvus 和 ES 都写?**双路检索铺垫**:Milvus 做向量(语义)检索,ES 做 BM25(关键词)检索,Phase 2 融合两者。Phase 1 只用 Milvus,但入库时一起写好。

---

## 1. BGEEmbedder(Station 01 已细讲,这里只点关键)

```python
class BGEEmbedder:
    def __init__(self, ...):
        self.device = self._resolve_device(device)   # auto → cuda/cpu
        self.use_fp16 = use_fp16 and self.device != "cpu"
        self._model = None                            # ← 延迟加载

    def _ensure_loaded(self):
        if self._model is not None: return
        from FlagEmbedding import BGEM3FlagModel
        self._model = BGEM3FlagModel(self.model_name, use_fp16=..., devices=...)

    def encode(self, texts, batch_size=32):
        self._ensure_loaded()                         # 首次调用才加载
        out = self._model.encode(texts, return_dense=True, ...)
        return [v.tolist() for v in out["dense_vecs"]]
```

**延迟加载(lazy load)**:`__init__` 不碰模型,第一次 `encode` 才加载 2.3GB 权重。
好处:配置错误/测试 mock 时不会白白吃 2GB 内存和几秒加载时间。

---

## 2. _milvus_schema():定义"表结构"

```python
def _milvus_schema():
    fields = [
        FieldSchema("id",          DataType.VARCHAR,      max_length=128, is_primary=True),
        FieldSchema("doc_id",      DataType.VARCHAR,      max_length=128),
        FieldSchema("text",        DataType.VARCHAR,      max_length=65535),
        FieldSchema("vector",      DataType.FLOAT_VECTOR, dim=1024),
        FieldSchema("granularity", DataType.VARCHAR,      max_length=32),
        FieldSchema("metadata",    DataType.JSON),
    ]
    return CollectionSchema(fields, description="sf-rag-kb chunks")
```

类比 SQL 的 `CREATE TABLE`。关键:
- `is_primary=True`:`id` 是主键(唯一)
- `dim=1024`:必须和 BGE-M3 输出维度一致,**写错了插入直接报错**
- `JSON` 类型:metadata 灵活存任意结构

---

## 3. MilvusWriter —— 重点

```python
@dataclass
class MilvusWriter:
    collection_name: str = settings.milvus_collection
    host: str = settings.milvus_host
    port: str = settings.milvus_port
    drop_existing: bool = False

    def __post_init__(self):
        connections.connect(alias="default", host=self.host, port=self.port)
        if utility.has_collection(self.collection_name):
            if self.drop_existing:
                utility.drop_collection(self.collection_name)
            else:
                logger.info("reusing")
        if not utility.has_collection(self.collection_name):
            self.collection = Collection(self.collection_name, _milvus_schema())
            self.collection.create_index(
                field_name="vector",
                index_params={"index_type":"HNSW","metric_type":"COSINE",
                              "params":{"M":16,"efConstruction":200}},
            )
        else:
            self.collection = Collection(self.collection_name)
        self.collection.load()           # ← 查询前必须 load
```

### `@dataclass` + `__post_init__`
`@dataclass` 自动生成 `__init__`。但我们还要在初始化后做"连数据库、建集合"这些动作——这放在 `__post_init__`,它在自动生成的 `__init__` 跑完后被调用。

### 初始化逻辑(幂等设计)
```
连接 Milvus
  → collection 存在?
     → drop_existing=True:删掉重建
     → 否则:复用
  → 不存在:建 collection + 建 HNSW 索引
  → load 到内存
```
这叫**幂等**:跑一次和跑多次结果一致(配合 `--drop` 控制要不要清空)。

### insert + flush
```python
def insert(self, chunks, vectors):
    rows = [{"id":c.id, "doc_id":c.doc_id, "text":c.text[:65535],
             "vector":v, "granularity":c.granularity, "metadata":c.metadata}
            for c, v in zip(chunks, vectors)]
    self.collection.insert(rows)
    return len(rows)

def flush(self):
    self.collection.flush()              # ← 不调,数据查不到!
    return self.collection.num_entities
```
- `text[:65535]`:截断防超过 VARCHAR 上限
- `zip(chunks, vectors)`:一一配对(第 i 个 chunk 配第 i 个向量)
- **`flush()` 是关键**:把内存里的"growing segment"封成"sealed segment"并建索引,不调的话新数据查不到(Station 02 讲过)

---

## 4. ESWriter —— 全文检索入库

```python
def _es_index_body(use_ik=False):
    if use_ik:
        text_field = {"type":"text", "analyzer":"ik_smart", ...}
    else:
        text_field = {"type":"text", "analyzer":"standard"}   # ADR-003 Phase 1 fallback
    return {"settings":..., "mappings":{"properties":{
        "id":{"type":"keyword"}, "text":text_field, ...}}}
```

### `keyword` vs `text` 的区别(ES 核心概念)
- **`keyword`**:整体精确匹配,不分词。`id`、`doc_id` 用它(要精确查)
- **`text`**:分词后做全文检索。`text` 字段用它(要模糊搜)

中文分词:`ik_smart`(中文分词器)vs `standard`(基本按字切)。我们 Phase 1 用 standard(ADR-003),Phase 2 装 ik。

### bulk 批量插入
```python
def insert(self, chunks):
    actions = ({"_index":self.index_name, "_id":c.id, "_source":{...}} for c in chunks)
    success, _ = helpers.bulk(self.client, actions, raise_on_error=False, ...)
    return success
```
- `helpers.bulk`:ES 的批量写 API,比一条条 insert 快几十倍
- `_id=c.id`:用 chunk id 做 ES 文档 id,**幂等**(重复写同 id 是覆盖,不会重复)
- 生成器表达式 `(... for c in chunks)`:惰性产生,省内存

### refresh
```python
def refresh(self):
    self.client.indices.refresh(index=self.index_name)   # 让刚写的立即可搜
    return int(self.client.count(index=self.index_name)["count"])
```
ES 默认每 1 秒刷新一次(near real-time)。`refresh()` 强制立即刷新,确保 count 准确。类似 Milvus 的 flush。

---

## 5. 双写模式总览

```
chunk + vector
   ├──→ Milvus.insert  (id, doc_id, text, vector, granularity, metadata)
   └──→ ES.insert      (id, doc_id, text, granularity, metadata)  ← 没 vector
```
**同一份 chunk,用同一个 id,写两个库**。检索时:
- 语义检索走 Milvus(拿 vector 算近邻)
- 关键词检索走 ES(BM25 算词频)
- 用 id 对齐两边结果

---

## 关键认知

1. **延迟加载**:重资源(模型)推迟到真用时才初始化
2. **`@dataclass + __post_init__`**:自动构造 + 自定义初始化动作
3. **幂等设计**:`drop_existing` + 用 chunk id 做主键,重复跑安全
4. **flush / refresh 不可省**:Milvus flush、ES refresh,不调新数据查不到
5. **双写**:Milvus 管向量,ES 管全文,同 id 对齐,为 Phase 2 混合检索铺路
6. **keyword vs text**:ES 里精确字段用 keyword,模糊搜字段用 text

---

## 自测题

1. `_ensure_loaded` 的延迟加载,对单元测试有什么好处?
2. 插入完忘了 `flush()`,`num_entities` 返回什么?查询能查到吗?
3. 同一个 chunk id 写两次进 ES,会有两条还是一条?为什么?
4. Milvus 的 `dim=1024` 改成 768 但 BGE-M3 还是输出 1024,会怎样?
5. ES 里 `id` 字段为什么用 `keyword` 不用 `text`?

---

## 可改进 / 生产实践

- **批量 embed + 批量 insert**:目前一个 batch embed 完就插,可以攒大批再插,减少网络往返
- **失败重试 / 断点续传**:大规模 ingest 中途失败,应记录进度可续跑
- **事务性**:Milvus 写成功但 ES 失败 → 数据不一致。生产要加补偿/对账
- **异步并发**:embed(GPU)和 写库(IO)可以 pipeline 并行,提升吞吐
