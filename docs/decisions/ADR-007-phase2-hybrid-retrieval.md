# ADR-007: Phase 2 收尾 —— 混合检索 + 多粒度的实测结论与定位

- **状态**:Accepted
- **日期**:2026-05-28
- **决策者**:AI 起草 + 用户决策(A+ 方案)

---

## 1. 背景(Context)

Phase 2 目标:用 BM25 + 多粒度切分 + RRF 混合,把 Recall@3 相对 baseline 拉高
(phase-2.md 写 +8pp,HANDOFF 校准为 +1~3pp)。已完成:
- T2.0 ES 装 ik_smart(ADR-005)
- T2.1 `MultiGranularitySplitter` + `chunks_v2`(31900 chunks)
- T2.2 `BM25Retriever`(ES ik_smart)
- T2.3 `reciprocal_rank_fusion` + `HybridRetriever`(RRF k=60)
- T2.4 doc 级口径评估(ADR-006)+ 消融 + 诊断

## 2. 实测结果(doc 级口径,100 条 eval)

**抗泄漏集 eval_v1_paraphrased(主用)**:

| 配置 | Recall@3(=Hit@3) | Recall@10 | MRR |
|---|---|---|---|
| Dense baseline (chunks_v1) | **0.94** | 0.97 | **0.9151** |
| Dense only (chunks_v2 多粒度) | 0.94 | 0.98 | 0.8882 |
| BM25 only (chunks_v2) | 0.65 | 0.75 | 0.6051 |
| Hybrid RRF k=60 (chunks_v2) | 0.84 | 0.97 | 0.8036 |

**合成集 eval_v1(词面重叠高)**:

| 配置 | Recall@3 | Recall@10 | MRR |
|---|---|---|---|
| Dense baseline (v1) | 0.99 | 1.00 | 0.9758 |
| BM25 only (v2) | **1.00** | 1.00 | 0.9667 |
| Hybrid (v2) | 0.99 | 1.00 | **0.9920** |

**DoD 判定:未达成**(主用集上最好的 Phase 2 配置只追平 baseline,Hybrid 反而下降)。

## 3. 诊断(为什么没提升,见 scripts/analyze_phase2.py)

1. **error-case**:Dense 命中但 Hybrid 漏的 11 条里,8 条 BM25 连 gold 都没召回
   (top-50 None),且 Dense 多把 gold 排第 1。RRF 等权让 BM25"错而靠前"的文档挤掉
   只有 Dense 支持的 gold。
2. **加权 RRF ablation**:dense:bm25 从 1:1→10:1,Recall@3 单调上升(0.85→0.92)但
   **始终 < 纯 dense 0.94**;最优 BM25 权重 → 0。加权救不回。
3. **分 query_type**:single_hop / yesno 两类 Dense 均 > Hybrid,无一类 hybrid 占优。

**根因**:抗泄漏集刻意改写问题、消除词面重叠,抽掉了 BM25 唯一的能力;通用语料 +
BGE-M3 已接近召回上限(R@10=0.97),互补空间极小。这不是实现 bug,是 eval×语料特性。
对照合成集(词面重叠高)BM25 R@3=1.00、Hybrid MRR=0.992 全场最高 —— **hybrid 的价值
只在词面/精确查询上兑现**。

## 4. 关于 RRF k=60

沿用 Elasticsearch / Azure AI Search 默认值。k 越大,各路名次差异被压得越平,靠"多路
共识"而非"单路第一"取胜。本项目未单独调 k:既然 BM25 在主用集是噪声,调 k 不改变
"hybrid < dense"的结论(加权 ablation 已覆盖更强的干预手段)。

## 5. 决策(A+ 方案)

1. **Phase 2 标记完成**,但如实记录"主用集 Recall 未提升,根因已诊断"。
2. **Hybrid 定位为 Phase 3 的候选生成层**:其 Recall@10=0.97 不丢召回,top-3 排序问题
   交给 Phase 3 reranker 解决。
3. **Dense-only 保留为 baseline 与 fallback**。
4. **多粒度 chunks_v2 保留**为默认语料(对 dense 中性,为 reranker 提供更细候选)。
5. Phase 3 做**三路线对比**:
   - ① Dense top-k + reranker
   - ② Hybrid top-k + reranker
   - ③ Dense-only 无 reranker(baseline)

## 6. 取舍(Consequences)

**好的**:基础设施(BM25 / Hybrid / 多粒度 / doc 级评估)全部就绪且测试覆盖;诚实记录
负结果,简历叙事可讲"用消融+诊断证明了 hybrid 在该 eval 无增益,并据此决定靠 rerank
而非堆检索路数"——比假装 +8pp 更有说服力。

**不好的 / 风险**:
- 当前 eval 系统性低估 hybrid/BM25 价值(无词面/精确查询切片)。Phase 4 可补一小批
  精确查询 eval 再交叉验证。
- 多粒度让候选池含同文档多 chunk 冗余,reranker 输入需按 doc 去重或容忍冗余。

## 7. 后续

- Phase 3 T3.4 reranker 落地后,按 §5 三路线出对比表,判端到端 Top-3 准确率
- 若三路线显示 ②Hybrid+rerank 不优于 ①Dense+rerank,则默认栈定为 Dense+rerank,
  hybrid 降级为 opt-in
