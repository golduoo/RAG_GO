# Phase 2: 混合检索 + 多粒度切分

> **目标**:把 Recall@3 从 baseline 拉到 baseline + 8pp 以上
> **预计**:1 周 / 30h
> **前置**:Phase 1 已完成,`docs/metrics.md` 已有 baseline 行

---

## Phase 总 DoD
- [ ] 混合检索接口可与 Dense / BM25 互换
- [ ] 多粒度切分实现 3 级:title/paragraph/sentence + FAQ 专用 Question-as-Index
- [ ] 消融实验完成:Dense only / BM25 only / Hybrid 三列对比
- [ ] Recall@3 相对 baseline 提升 ≥ 8pp(不达标必须停下来分析)
- [ ] `docs/metrics.md` 多一节 "Phase 2 - Hybrid - {日期}"

---

## Tasks

### T2.1 多粒度切分
**目标**:把单一切分策略换成多粒度
**步骤**:
1. 在 `src/ingest/splitters.py` 新增 `MultiGranularitySplitter`
2. 三级切分:
   - title:按 `MarkdownHeaderTextSplitter` 或正则识别标题
   - paragraph:按段落
   - sentence:按句子(中文用 `；。!?` 切)
3. 表格保留完整 + 额外生成一条 LLM 摘要 chunk(granularity=`paragraph`,metadata 标 `is_table_summary=True`)
4. FAQ 类数据(metadata 有 `qa` 标记的)用 Question-as-Index:用 question 字段算向量,payload 存 answer
5. 重新 ingest 到新 collection `chunks_v2`

**DoD**:Milvus 中 `granularity` 字段分布合理,FAQ 类的 chunk granularity=`qa`

---

### T2.2 BM25 检索
**目标**:Sparse 检索器,接口与 DenseRetriever 兼容
**步骤**:
1. `src/retrieval/sparse.py`:`BM25Retriever`,基于 ES
2. 用 `ik_smart` 分词;如未装插件,fallback `standard` 并写 ADR
3. 测试:索引 10 条,query 命中 verifiable

**DoD**:接口签名与 `DenseRetriever` 完全一致,可热插拔

---

### T2.3 RRF 混合检索 ⭐ 核心
**目标**:并行 Dense + BM25,RRF 融合
**步骤**:
1. `src/retrieval/hybrid.py`:
   ```python
   def reciprocal_rank_fusion(
       rankings: Sequence[list[RetrievedDoc]],
       k: int = 60,
       top_k: int = 10,
   ) -> list[RetrievedDoc]: ...
   
   class HybridRetriever(Retriever):
       def __init__(self, retrievers: list[Retriever], k: int = 60): ...
       def search(self, query, top_k=10) -> list[RetrievedDoc]:
           # 并行调多路(用 asyncio.gather 或 concurrent.futures)
           # RRF 融合
   ```
2. 测试:
   - 正常多路融合
   - 单路输入(应等于原始排序)
   - 空路(应被跳过)
   - 重复 doc(分数累加)
   - 不同长度的 ranking

**DoD**:`tests/retrieval/test_hybrid.py` ≥ 5 个 case 全绿

---

### T2.4 Phase 2 评估
**目标**:量化提升,跑消融
**步骤**:
1. `python scripts/run_eval.py --phase 2 --collection chunks_v2 --retriever hybrid`
2. 同时跑消融:`--retriever dense_only`, `--retriever bm25_only`
3. 三组指标都写入 `docs/metrics.md`

**DoD**:
- Recall@3 提升 ≥ 8pp,否则:
  - 检查 chunk 切分是否合理(可能切碎了)
  - 检查 BM25 分词是否生效
  - 检查 RRF 实现是否正确
  - **停下来问用户,不要硬上 Phase 3**

---

## Phase 2 结束动作

1. `docs/progress.md` 勾选 Phase 2 完成
2. 写 `ADR-002-hybrid-retrieval.md`,关键内容:
   - RRF 为什么用 k=60(可参考微软 Azure Search 默认值)
   - Dense vs BM25 的命中差异分析(2-3 条典型 case)
   - Phase 2 vs Phase 1 各项指标对比
