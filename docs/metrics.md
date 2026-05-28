# Metrics

> 所有评估结果按时间追加。**不要**修改历史记录。
> 写入由 `src/eval/metrics_logger.py` 的 `append_phase_report()` 完成,不要手写。

---

## 数据集说明

| 集合 | 文件 | 规模 | 用途 |
|------|------|------|------|
| 主语料 | `data/processed/logistics_corpus.jsonl` | 8000 docs / 10786 chunks | RAG 知识源 |
| 评估集 v1 | `data/eval/eval_v1.jsonl` | 100 | Phase 1-3 主评估 |
| 评估集 v2 | `data/eval/eval_v2.jsonl` | (Phase 4 增加多跳) | Phase 4+ 评估 |
| CRUD-RAG | (外部 benchmark) | - | Phase 4 学术对比 |

---

## 记录格式参考

```markdown
## Phase {N} - {主题} - {YYYY-MM-DD}

**配置**:
- Embedding: ...
- Retriever: ...
- Reranker: ...
- LLM: ...
- Eval set: ...

**主指标**:

| Metric | Value | Δ vs baseline |
|--------|-------|---------------|
| Recall@3 | - | - |

**消融**(可选): ...

**性能**(可选): ...

**备注**:...
```

---

<!-- 评估结果从下面开始追加,最新的在最下面 -->

## Phase 1 - Ingest 性能基线 - 2026-05-13

> 这是入库阶段的耗时基线,不是检索/生成的质量指标。后续 T1.9 才会写第一份 Recall/MRR。

**配置**:
- Embedding: `BAAI/bge-m3` (fp16,本地权重 `models/bge-m3`)
- Splitter: `FixedTokenSplitter(chunk_size=400, chunk_overlap=50)`,tokenizer=`cl100k_base`
- Milvus: collection `chunks_v1`,HNSW `M=16 efConstruction=200` COSINE,1024 维
- ES: index `chunks_v1`,standard analyzer(Phase 1 fallback,见 ADR-003)
- 输入: 8000 Documents → 10786 Chunks
- Device: NVIDIA RTX 4060 Laptop 8GB,CUDA 12.8
- batch_size: 64

**性能**:

| Stage | Time | Notes |
|-------|------|-------|
| Document load + split | <1 s | 10786 chunks 切分 |
| Embedding (10786 × 1024-dim, fp16) | 208.0 s | GPU,~52 chunks/s |
| Dual write (Milvus + ES) | 5.8 s | bulk insert |
| **总耗时** | **221.8 s** | ~3.7 min |

**计数验证**:
- chunks 切分: 10786
- Milvus `chunks_v1.num_entities`: 10786 ✓
- ES `chunks_v1` doc count: 10786 ✓

**备注**:
- 8000 docs → 10786 chunks 比 = 1.35,说明大部分文档单段即可,部分长文被切多段
- BGE-M3 首次 load weights 约 0.2 s(权重已本地缓存),warmup 后稳定 52 chunks/s
- 此阶段不涉及检索质量,Recall/MRR 在 T1.9 评估集就绪后产出

## Phase 1 - Dense Baseline - 2026-05-13

**配置**:

- Embedding: `models/bge-m3`
- Retriever: `DenseRetriever(BGE-M3 + Milvus HNSW M=16 efC=200, ef=64)`
- Reranker: `none`
- LLM: `none (retrieval-only eval)`
- Eval set: `data\eval\eval_v1.jsonl (100 samples)`
- Collection: `chunks_v1`
- top_k: `10`

**主指标**:

| Metric | Value | Δ vs baseline |
|--------|-------|---------------|
| Recall@3 | 0.9310 | - |
| Hit@3 | 0.9900 | - |
| Recall@5 | 0.9572 | - |
| Hit@5 | 1.0000 | - |
| Recall@10 | 0.9755 | - |
| Hit@10 | 1.0000 | - |
| MRR | 0.9758 | - |

**备注**:

BGE-M3 + Milvus HNSW + FixedTokenSplitter(400/50) on chunks_v1 (10786 chunks)


## Phase 1 - Dense Baseline (paraphrased eval, leak-resistant) - 2026-05-13

**配置**:

- Embedding: `models/bge-m3`
- Retriever: `DenseRetriever(BGE-M3 + Milvus HNSW M=16 efC=200, ef=64)`
- Reranker: `none`
- LLM: `none (retrieval-only eval)`
- Eval set: `data\eval\eval_v1_paraphrased.jsonl (100 samples)`
- Collection: `chunks_v1`
- top_k: `10`

**主指标**:

| Metric | Value | Δ vs baseline |
|--------|-------|---------------|
| Recall@3 | 0.8740 | - |
| Hit@3 | 0.9300 | - |
| Recall@5 | 0.9152 | - |
| Hit@5 | 0.9600 | - |
| Recall@10 | 0.9388 | - |
| Hit@10 | 0.9700 | - |
| MRR | 0.9116 | - |

**备注**:

用 DeepSeek 改写 eval_v1 的 question(避开原文关键词,口语化),gold_doc_ids 不变。对比泄漏版本看 Δ


## Phase 2 - Ingest chunks_v2(多粒度 + ik) - 2026-05-28

> T2.1 入库记录(性能 + 计数 + 粒度分布),非检索质量。检索对比在 T2.4 产出。

**配置**:
- Embedding: `models/bge-m3` (fp16)
- Splitter: `MultiGranularitySplitter(paragraph_size=400, paragraph_overlap=50, sentence_max=150)`
- 粒度: title(正则识别)/ paragraph(复用 RecursiveCharacterSplitter)/ sentence(中文句末标点贪心合并)
- Milvus: collection `chunks_v2`,HNSW `M=16 efConstruction=200` COSINE,1024 维
- ES: index `chunks_v2`,**ik_smart** analyzer(ADR-005,插件已装)
- 输入: 8000 Documents → 31900 Chunks
- Device: NVIDIA RTX 4060 Laptop 8GB,CUDA 12.8;batch_size 32

**性能**:

| Stage | Time | Notes |
|-------|------|-------|
| Document load + split | <1 s | 31900 chunks 切分 |
| Embedding (31900 × 1024-dim, fp16) | 593.4 s | GPU,~54 chunks/s |
| Dual write (Milvus + ES) | 62.1 s | bulk insert |
| **总耗时** | **664.5 s** | ~11 min |

**计数验证**:
- chunks 切分: 31900
- Milvus `chunks_v2.num_entities`: 31900 ✓
- ES `chunks_v2` doc count: 31900 ✓

**粒度分布**:

| granularity | count | 占比 |
|-------------|-------|------|
| paragraph | 10126 | 31.7% |
| sentence | 21761 | 68.2% |
| title | 13 | 0.04% |

**备注**:
- 8000 docs → 31900 chunks(约 4.0×),paragraph 数(10126)与 chunks_v1(10786)同量级,sentence 是新增的细粒度层
- 语料为 DuReader 纯文本,**无 FAQ(qa)/ 表格数据**,故无 `qa` 粒度、无表格摘要块;title 仅 13 条(命中"第X章/节/条")
- chunks_v1 保留未动(10786),供 T2.4 同口径对比

