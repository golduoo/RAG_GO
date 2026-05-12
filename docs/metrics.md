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
