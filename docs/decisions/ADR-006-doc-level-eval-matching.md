# ADR-006: 评估改为"文档级匹配"(doc-level matching)

- **状态**:Accepted
- **日期**:2026-05-28
- **决策者**:AI 建议 + 用户确认

---

## 1. 背景(Context)

Phase 1 的评估口径是 **chunk 级精确匹配**:`run_eval.py` 把检索到的 chunk id 与
`EvalSample.gold_doc_ids`(chunks_v1 用 FixedTokenSplitter 切出的 chunk id,形如
`{src_doc_id}-{N}`)做集合比较。

Phase 2 换成 `MultiGranularitySplitter` 重建了 `chunks_v2`:同一文档被切成
paragraph + sentence 多块,chunk id 的 `-N` 编号和文本边界**完全变了**。直接沿用旧
gold chunk id 在 chunks_v2 上评估会几乎全部 miss —— Phase 1 / Phase 2 不可比。

好在每条 eval 的 `metadata.src_doc_id` 保留了**原始文档 id**。

## 2. 决策(Decision)

评估"命中"的判定从 **chunk 级** 提升到 **文档级**:检索到的 chunk 只要属于 gold 那篇
文档(`RetrievedDoc.metadata["doc_id"] == EvalSample.metadata["src_doc_id"]`)即算命中。

实现:
- `run_eval.py` 加 `--match-level {chunk,doc}`,**默认 `doc`**(`chunk` 保留兼容旧口径)
- doc 级:把 chunk 排名**按 doc_id 去重**(保留首次出现的名次),折叠成"文档排名",
  再算 Recall/Hit/MRR。让多粒度(同文档多 chunk)与单粒度在 doc 空间公平对比
- 检索深度抬到 `max(top_k, max(ks), 50)`,保证去重后文档数够 @10

## 3. 理由(Rationale)

- 对"换切分策略"天然稳健:不依赖 chunk id 的具体编号
- 更符合召回本意:"有没有找到对的文档",而不是"找到第几块"
- `metadata.src_doc_id` 现成,零额外标注成本
- 去重折叠避免同文档多 chunk 把名次占满(否则多粒度被冗余 chunk 惩罚 MRR)

## 4. 代价 / 取舍(Consequences)

**好的**:
- Phase 1(chunks_v1)与 Phase 2(chunks_v2)可在同一口径下直接对比
- `recall_at_k` 顺手修了一个 bug(见 §6)

**不好的 / 注意**:
- doc 级下每条 eval 只有 1 个 gold 文档 → **Recall@k 恒等于 Hit@k**;区分排序质量要看
  MRR。这是单 gold 的必然结果,不是错误
- 与 chunk 级绝对值不可直接比(口径不同),metrics.md 两种口径分节记录

## 5. 影响范围

- **改动**:`scripts/run_eval.py`(加参数 + `build_pairs` 去重逻辑)、`src/eval/metrics.py`
  (`recall_at_k` 改集合交集)
- **不改**:`data-schemas.md` §2 EvalSample(gold_doc_ids 字段保留,chunk 级仍可用)

## 6. 验证 / 顺带修的 bug

首次按 doc 级跑出现 **Recall@3 = 1.13 / 2.16** 等 >1 的非法值。根因:`recall_at_k` 用
`sum(1 for r in retrieved[:k] if r in gold_set)`,doc 级下 retrieved 含同文档多个 chunk
(doc_id 重复)→ 重复计数。已改为集合交集 `len(set(retrieved[:k]) & gold_set)/|gold|`,
对 chunk 级(id 唯一)结果不变,对 doc 级封顶到 1。加回归测试
`test_recall_duplicate_retrieved_capped_at_one`。

doc 级口径基线(paraphrased eval,chunks_v1 dense):Recall@3=0.94 MRR=0.9151。

## 7. 后续

- Phase 4 起引入 RAGAS(不依赖 gold id)+ CRUD-RAG,与 doc 级 Recall 交叉验证
- 若将来需要"片段级"精度评估(rerank 阶段),可临时切回 `--match-level chunk`
