# ADR-{编号}: {简短标题}

> 复制此文件改名,如 `ADR-001-baseline-embedding.md`
> ADR = Architecture Decision Record,记录"为什么做了这个决策"

- **状态**:Proposed / Accepted / Deprecated / Superseded by ADR-XXX
- **日期**:YYYY-MM-DD
- **决策者**:用户 / AI 建议

---

## 1. 背景(Context)

(2-5 句话讲清楚:遇到了什么问题,有哪些可选方案,为什么需要做这个决策)

例:在 Phase 1 我们需要选择一个 Embedding 模型用于检索 baseline。选项包括 BGE-base-zh、BGE-large-zh、BGE-M3、OpenAI text-embedding-3-small。

---

## 2. 决策(Decision)

(明确做了什么决策,1-3 句话)

例:选择 BGE-M3 作为默认 Embedding 模型,fp16 加速。

---

## 3. 理由(Rationale)

(列出 3-5 条理由)

- 中文性能:在 C-MTEB 榜单上 BGE-M3 是开源模型 top 3
- 单模型多功能:支持 Dense + Sparse + ColBERT,后续 Phase 可平滑扩展
- 免费:不依赖 OpenAI API
- 1024 维:与 Milvus collection schema 对齐

---

## 4. 代价 / 取舍(Consequences)

**好的**:
- (列出预期收益)

**不好的**:
- (列出代价、风险、放弃的可能性)

例:
- 好的:中文检索效果好,免费
- 不好的:CPU 推理慢(~30ms/query),GPU 资源占用约 2GB

---

## 5. 影响范围

- 涉及代码:`src/ingest/indexer.py`, `src/retrieval/dense.py`
- 涉及配置:`EMBEDDING_MODEL`
- 涉及指标:Recall@K(直接影响)

---

## 6. 验证

(如何知道这个决策是对的?跑了什么实验?)

例:
- 在 100 条 eval set 上跑出 Recall@3 = 0.64
- 对比 BGE-base-zh 的 0.58,提升 6pp
- 详见 `docs/metrics.md` Phase 1 节

---

## 7. 后续

(这个决策接下来还可能调整吗?什么时候?)

例:
- Phase 4 引入 GraphRAG 时,需要评估是否需要专门的实体 embedding 模型
- 如果 GPU 资源紧张,可考虑 bge-base-zh-v1.5(512 维)
