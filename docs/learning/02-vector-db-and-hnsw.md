# 02. 向量库 & HNSW 索引

> 关联代码:`src/ingest/indexer.py` 的 `MilvusWriter` / `_milvus_schema`
> 关联代码:`src/retrieval/dense.py` 的 `DenseRetriever.search`
> 关联决策:Phase 1 全程

---

## 1. 直觉:为什么不能直接用 Python list?

Station 01 学完了:我们有 10786 个 chunk,每个一个 1024 维向量。
一个最朴素的检索方案——**遍历**:

```python
def search(query_vec, all_vecs, top_k=5):
    sims = [cosine(query_vec, v) for v in all_vecs]   # 算 10786 次
    return sorted(zip(sims, ids), reverse=True)[:top_k]
```

10786 条用 numpy,大约 10-30 ms,能跑。但:

- 100 万条 → 几秒
- 1 亿条 → 分钟级
- 还要并发查询 → 单机崩

而且你要面对:
- 增量插入 / 删除 / 更新
- 多机扩展(主从、分片)
- 持久化、崩溃恢复
- 元数据过滤(只在 `granularity=paragraph` 里查)
- 跟其他存储(对象存储 / 元信息库)协作

**这就是向量数据库要解决的事**。Milvus、Pinecone、Weaviate、Qdrant、Chroma、Vespa 都属此类。
本质都是:**ANN 索引 + 工程化的存储和服务层**。

---

## 2. ANN vs KNN(为什么"近似"反而是聪明的)

| | KNN(Brute Force) | ANN(Approximate) |
|---|---|---|
| 找的结果 | **真**最近的 K 个 | **大概率**是最近的 K 个 |
| 复杂度 | O(N) 每次查询 | O(log N) 或更好 |
| 召回率 | 100% | 95-99%(可调) |
| 适用 | 小数据 / 离线测试 | 生产 / 大规模 |

**为什么愿意接受"近似"?**

因为 query 本身就是含糊的。"顺丰多久到" 跟 "顺丰快件几天" 的余弦相似度可能是 0.91 和 0.90 —— 你拿到 0.90 那条也不影响最终答案质量,但**速度从秒级到毫秒级**。

> 现实经验:99% recall 跟 100% recall,人体感受不出差别。

---

## 3. HNSW 算法直觉(最关键的一节)

HNSW = **H**ierarchical **N**avigable **S**mall **W**orld(分层可导航小世界图)。
听起来玄,讲完你就懂。

### 3.1 想象一个"分层地图"

类比**找朋友的过程**:
- 你在中国南方,要找北京一个人
- 第 0 层(最详细):你只认识同小区的几个人 — 慢
- 第 1 层(中等):每个市的几个"枢纽人"互相认识 — 跨城快
- 第 2 层(粗略):每个省一个"代理人",代理人之间认识 — 跨省超快

**找人流程**:从最高层的某个点出发 → 在该层跳到离目标最近的点 → 下到下一层 → 继续跳 → ... → 最底层精确找到。

每次跳跃 O(1),层数 O(log N),所以**总复杂度 O(log N)**。

### 3.2 在向量空间里

每个 chunk 向量就是图上一个**节点**。HNSW 在插入时给每个节点:
1. **随机**分配一个"层数"(指数衰减:越高层越少节点)
2. 在每一层,跟附近的 M 个邻居建边

查询时:
1. 从最高层一个入口点(entry point)开始
2. 在当前层贪心:看邻居谁离 query 更近,跳过去
3. 跳不动了(局部最优)→ 下一层
4. 重复直到最底层
5. 在最底层做一次精细搜索,返回 top_k

### 3.3 三个核心参数

| 参数 | 作用 | 典型值 | 调大会怎样 |
|---|---|---|---|
| **M** | 每个节点的邻居数 | 8-64 | 内存涨,召回↑,查询略慢 |
| **efConstruction** | **建索引**时候选池大小 | 100-500 | 建索引慢,质量好 |
| **ef**(或 efSearch) | **查询**时候选池大小 | 16-512 | 查询慢,召回↑ |

**调参直觉**:
- M 是**结构性**参数,索引建好就定了,改不了
- efConstruction 是**建索引一次性投入**,大点没事
- ef 是**查询时**实时调,你可以为不同业务给不同 ef(线上低延迟用 16,后台离线用 256)

### 3.4 我们项目的配置

```python
# src/ingest/indexer.py
self.collection.create_index(
    field_name="vector",
    index_params={
        "index_type": "HNSW",
        "metric_type": "COSINE",
        "params": {"M": 16, "efConstruction": 200},
    },
)
```

```python
# src/retrieval/dense.py
DEFAULT_SEARCH_PARAMS = {"metric_type": "COSINE", "params": {"ef": 64}}
```

| 参数 | 我们的值 | 解读 |
|---|---|---|
| M=16 | 中等 | 每个节点 16 个邻居,10k 量级足够 |
| efConstruction=200 | 中偏大 | 索引建得仔细,我们建一次用很久 |
| ef=64 | 中等 | 查询时 64 个候选,够 top-10 检索且快 |

**Phase 2 进 BM25 混合后可以做的实验**:把 ef 从 64 加到 256,看 Recall@10 提升多少 / 延迟涨多少。

---

## 4. 除了 HNSW 还有什么?(科普,不深入)

| 索引类型 | 适用 | 我们为什么不用 |
|---|---|---|
| **FLAT** | 暴力,< 100k | 数据再大就慢 |
| **IVF**(Inverted File) | 中等规模,有聚类倾向 | HNSW 召回更好 |
| **IVF_PQ** | 大规模 + 压缩 | 内存够,不需压缩 |
| **HNSW** ✓ | 10k-千万级,默认首选 | 我们的场景 |
| **DiskANN** | 上亿级,装 SSD | 我们没那么多数据 |
| **SCANN**(Google) | TPU 大规模 | Milvus 不支持 |

**记一个**:**默认首选 HNSW,纠结再换**。

---

## 5. Milvus 内部架构(简略)

启动时你的 `docker compose up -d` 起了三个相关容器:

```
┌──────────────────────────────────────────────┐
│  milvus  (主服务)                              │
│  - 接收 SDK 请求(gRPC 19530)                  │
│  - 内存里持有 HNSW 索引                         │
│  - 查询、插入                                   │
└─────────┬──────────────────────┬─────────────┘
          │ 元数据                │ 对象存储
          ▼                      ▼
   ┌─────────────┐         ┌──────────────┐
   │   etcd      │         │   MinIO      │
   │ (集合/索引   │         │ (向量数据、   │
   │  元数据)     │         │  segment 文件) │
   └─────────────┘         └──────────────┘
```

为什么要 etcd + MinIO?
- **etcd**:存"哪些 collection 存在 / 索引参数 / schema"。Milvus 重启后从这恢复。
- **MinIO**:实际向量数据按 "segment"(段)存成文件。Milvus 内存里跑,定期 flush 到 MinIO。

这就是为什么你 `docker compose up -d` 看到 3 个容器一起起,而且 milvus 要 `depends_on: etcd healthy + minio healthy`(我们 yml 里写了)。

### 5.1 Collection / Segment / Partition

```
Collection (chunks_v1)
├── Partition (默认 _default,可分多个)
│   ├── Segment (写满或 flush 后产生)
│   │   ├── Sealed segment(只读,带 HNSW 索引)
│   │   └── Growing segment(还在写,无索引,brute force 查)
```

**flush() 的意义**:把 growing segment 封成 sealed,触发索引构建。**没 flush 的数据查不出**(或慢)。
我们代码里:
```python
def flush(self) -> int:
    self.collection.flush()        # ← 必须调,不然新插入的查不到
    return self.collection.num_entities
```

### 5.2 load 是什么?

Milvus 默认**数据在 MinIO**,查询前需要先 **load 到内存**:
```python
self.collection.load()
```
没 load 之前查会失败。`DenseRetriever.__init__` 里我们做了这一步。

> **生产坑**:load 大集合占内存。8GB 内存的机器装不下 1 亿向量的 collection,要分片或换大机器。

---

## 6. Schema 设计(回看代码)

```python
# src/ingest/indexer.py
def _milvus_schema():
    fields = [
        FieldSchema("id",          DataType.VARCHAR,      max_length=128, is_primary=True),
        FieldSchema("doc_id",      DataType.VARCHAR,      max_length=128),
        FieldSchema("text",        DataType.VARCHAR,      max_length=65535),
        FieldSchema("vector",      DataType.FLOAT_VECTOR, dim=1024),
        FieldSchema("granularity", DataType.VARCHAR,      max_length=32),
        FieldSchema("metadata",    DataType.JSON),
    ]
```

**设计取舍**:
- `id` 主键用字符串(`{doc_id}-{chunk_idx}`),好调试。如果追求性能可以用 INT64。
- `text` 直接存进 Milvus(冗余,本质 ES 也存了)。好处:返回时不用回 ES 拉,坏处:Milvus 收缩慢、容量贵。生产里有人只在 Milvus 存 `id`,文本另外存 PostgreSQL。
- `metadata` 用 JSON:灵活,但**不能精确 schema 校验**。Milvus 2.4 起支持 JSON 上建索引,可以过滤"只查 metadata.is_logistics=true 的"。
- `granularity` 单独字段:为了 Phase 2 多粒度做准备(届时一个 collection 里混 sentence 和 paragraph)。

---

## 7. 搜索的完整链路(代码 walk)

```python
# src/retrieval/dense.py
def search(self, query, top_k=10):
    if not query or not query.strip(): return []
    if top_k <= 0: return []

    vec = self.embedder.encode([query])[0]      # ← Station 01 学过
    results = self.collection.search(
        data=[vec],                              # 一次可以批量,这里 1 个
        anns_field="vector",                     # 在哪个字段做 ANN
        param=self.search_params,                # {"params": {"ef": 64}}
        limit=top_k,                             # top_k
        output_fields=["id","doc_id","text",...] # 想拿哪些字段返回
    )
    # results[0] 是第一个 query 的 hit 列表,按 score 降序
    for rank, hit in enumerate(results[0]):
        ...
```

**关键点**:
- `data=[vec]` 是 list of list:支持一次查多个 query(batch_search)
- `output_fields`:不指定的话只返回 id + score,要文本得显式写
- `hit.score` 是 COSINE 相似度(归一化后 [-1, 1],我们这都是正的,因为向量经过归一化)

---

## 8. 常见坑

| 坑 | 现象 | 解决 |
|---|---|---|
| 插入了但查不到 | num_entities 是 0 | 忘了 `collection.flush()` |
| 查询报 "collection not loaded" | search 抛错 | 漏 `collection.load()` |
| 索引参数想改 | 改不了 | 已建索引的 collection,要 drop_index → create_index 重建 |
| ef 加到 1000 | 查询变慢 10 倍 | ef 不要超过 top_k × 10 |
| metadata 过滤 | 慢 | 需要在 JSON 字段上建二级索引(Milvus 2.4+) |
| chunks_v1 已存在,改 schema | 报错 | drop_collection 再建 |
| RTX 4060 内存够吗 | 我们 10k 向量,远远够 | 估算:N × dim × 4byte,1 亿×1024×4 = 400GB,需分片 |

---

## 9. 自测题

1. 我们 chunks_v1 现在 10786 条 1024 维向量,占多少 MB?(纯向量,不算元数据)
2. 如果 ef 从 64 降到 16,会发生什么?延迟和召回怎么变?
3. 你新加了 1000 个 chunk 但没调 flush,会发生什么?
4. 为什么 HNSW 要分层?如果只有一层(就是一个普通图)会怎样?
5. 现在 Milvus 容器 stop 了,数据还在吗?重启后数据还能用吗?(提示:看 docker volume)
6. 假设要支持"只检索 is_logistics=true 的 chunk",要怎么改代码?

---

## 10. 想再深入?推荐资料

- HNSW 原论文(看图就够了,数学可跳):Malkov & Yashunin, 2018
- Milvus 官方架构图:https://milvus.io/docs/architecture_overview.md
- Pinecone 写的 ANN 教程(英文,直觉好):https://www.pinecone.io/learn/series/faiss/hnsw/
- 推荐书:**《向量数据库通识》**(Zilliz/Milvus 官方,中文,免费 PDF)

---

**这一站完成的标志**:你能在白板上画出 HNSW 的分层结构,并解释一次查询从最高层一路跳到最底层的过程。
讲不顺的话回去看 §3,**画 5 分钟图**比读 5 分钟字管用。
