# ADR-004: Phase 1 Baseline 收尾总结

- **状态**:Accepted
- **日期**:2026-05-13
- **决策者**:AI 起草 + 用户最终确认

---

## 1. 背景(Context)

Phase 1 目标:跑通 query → Dense 检索 → LLM 生成的最简闭环,记录 baseline 指标作为
后续 Phase 2/3 优化的对照组。T1.1 ~ T1.9 全部完成。

## 2. Phase 1 关键技术选型(实际落地)

| 组件 | 选择 | 备注 |
|------|------|------|
| Python | 3.12 (ADR-001) | 因 grpcio 在 3.14 无 wheel |
| 主语料 | C-MTEB/DuRetrieval 100k 段落,分层采样 8000 (ADR-002) | 通用中文 RAG + 物流软标签 |
| Splitter | FixedTokenSplitter(chunk_size=400, chunk_overlap=50) | tiktoken cl100k_base |
| Embedding | BAAI/bge-m3 fp16 on RTX 4060 Laptop | 1024 维,52 chunks/s |
| 向量库 | Milvus 2.4.15 standalone, HNSW (M=16, efConstruction=200), COSINE | |
| BM25 | ES 8.15.3 standard analyzer (ADR-003 fallback) | Phase 2 切 ik_smart |
| LLM | DeepSeek `deepseek-chat`,OpenAI 兼容,tenacity 3x 退避 | 只重试 5xx + 限流 |
| Prompt | RAG_USER_TEMPLATE(强约束"找不到要明说") | |
| 评估集 | eval_v1.jsonl,DeepSeek 从 100 条采样 doc 生成 QA | LLM 合成,有泄漏(见 §3) |

## 3. Baseline 指标(Phase 1 - Dense Baseline)

| Metric | Value |
|--------|-------|
| Recall@3 | 0.9310 |
| Hit@3 | 0.9900 |
| Recall@5 | 0.9572 |
| Hit@5 | 1.0000 |
| Recall@10 | 0.9755 |
| Hit@10 | 1.0000 |
| MRR | 0.9758 |

详见 `docs/metrics.md` 第一节。

## 4. 一个重要的警讯:评估泄漏(eval-set leakage)

**phase-1.md T1.9 预期 Recall@3 在 55–70%,实际 93%**。差距来源是合成评估集的方法学缺陷:

1. 评估集 100 条 QA 由 DeepSeek **直接基于源语料段落生成**
2. 生成的问题往往**复用原文词汇**(例如 "聚划算" 一词在 doc 和 question 里都明确出现)
3. BGE-M3 是强语义模型,但更强的是词面相似 → 容易"端到端循环"找回原 doc
4. 真实人类问答通常是口语化、概括化的,**词面相似度低于合成集**

因此 **Phase 1 的绝对值偏乐观**,但**相对值(Phase 间 Δ)仍有意义**——
只要保持同一份 eval_v1.jsonl 跨阶段对比,Phase 2 的 +0.02 Recall@3 仍然真实反映方法改进。

### 4.1 后续 Phase 应对

- Phase 2 / 3:继续用 eval_v1 看相对提升,**不**追求绝对数字突破
- Phase 4 起:除了 eval_v1,引入 RAGAS faithfulness / context_recall(不依赖 gold_doc_ids)+
  CRUD-RAG 学术 benchmark(人写的 Q)做交叉验证
- Phase 6(简历定稿):报告时同时给出 eval_v1 + 真实 benchmark,**不只**报告乐观的合成数

## 5. 发现的主要问题(为 Phase 2 铺垫)

| 问题 | 影响 | Phase 2 应对 |
|------|------|------------|
| ES 用 standard analyzer,中文几乎逐字 | BM25 召回质量差 | T2.1 装 ik 插件 + 重建索引 |
| Dense 单路检索,缺乏词面互补 | 长尾稀有词命中弱 | T2.2 BM25 + T2.3 RRF 融合 |
| 8000 docs 中只有 1.35x 切分膨胀,大量段落 < 400 token | 多粒度优势没体现 | T2.4 多粒度 chunk(sentence + paragraph) |
| 评估集合成泄漏,绝对指标乐观 | 不利于真实场景估计 | Phase 4 引入 RAGAS + CRUD-RAG |

## 6. 决策

1. **Phase 1 状态置为 ✅ Done**
2. eval_v1.jsonl **不重做**:接受其乐观偏差,后续 Phase 通过 Δ 比较即可,加 RAGAS 做交叉验证
3. Phase 2 启动前必须先做的"清洁工作":
   - 装 ES ik 中文分词插件(ADR-003 承诺)
   - 重建 ES index(可能升 chunks_v2,看 T2.4 多粒度方案)

## 7. 取舍(Consequences)

**好的**:
- 端到端通了,所有 Phase 2-6 的优化都在牢固地基上推进
- 测试覆盖完整(splitters / retriever / llm / pipeline / metrics 共 62 个 case 全绿)
- 4 份 ADR 记录了所有偏离规则的决策

**不好的**:
- 评估指标乐观,简历叙事时不能直接用 "93% Recall@3" 这种话(误导)
- ES 标准分词在 Phase 1 没有真用过 BM25 query,质量盲区延后到 Phase 2

## 8. 后续

- Phase 2 启动时第一步:装 ik 插件 + 重建索引
- 进入 Phase 2 之前等用户 review 本 ADR
