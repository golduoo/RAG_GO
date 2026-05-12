# Metrics

> 所有评估结果按时间追加。**不要**修改历史记录。
> 写入由 `src/eval/metrics_logger.py` 的 `append_phase_report()` 完成,不要手写。

---

## 数据集说明

| 集合 | 文件 | 规模 | 用途 |
|------|------|------|------|
| 主语料 | `data/processed/logistics_corpus.jsonl` | (待填) | RAG 知识源 |
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
