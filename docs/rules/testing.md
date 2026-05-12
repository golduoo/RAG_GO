# Rules: Testing & Evaluation

> **何时读**:写测试、跑评估、更新 `docs/metrics.md`。

---

## 1. 单元测试

### 文件组织
- `tests/{module}/test_{file}.py` 与 `src/{module}/{file}.py` 一一对应
- 测试函数命名:`test_{被测函数}_{场景}`
  - `test_rrf_normal_case`
  - `test_rrf_empty_input`
  - `test_rrf_single_ranking`

### 每个非平凡函数必须覆盖
- 1 个正常 case
- 1 个边界 case(空输入、最大/最小值、单元素等)
- 1 个异常 case(非法输入应抛指定异常)

### 不可做的事
- ❌ 不要为了让测试通过而改测试
- ❌ 不要 mock 掉被测函数本身的核心逻辑
- ❌ 不要写 `assert True` 这种空壳测试
- ❌ 不要让测试依赖外部服务(LLM、Milvus、ES)。需要时用 mock 或 fixture

### Mock 用 Pytest fixture
```python
# tests/conftest.py
import pytest
from unittest.mock import MagicMock

@pytest.fixture
def mock_milvus():
    client = MagicMock()
    client.search.return_value = [...]  # 模拟检索结果
    return client

@pytest.fixture
def sample_chunks():
    from src.ingest.schema import Chunk
    return [
        Chunk(id="d1-0", doc_id="d1", text="...", granularity="paragraph"),
        # ...
    ]
```

### 跑测试
```bash
pytest -q                          # 全部,精简输出
pytest tests/retrieval/ -v         # 单目录,详细
pytest -k "rrf"                    # 按关键词
pytest tests/retrieval/test_hybrid.py::test_rrf_normal_case  # 单条
pytest --lf                        # 只跑上次失败的
```

### Smoke test 不能替代单元测试
- `if __name__ == "__main__"` 块只用于调试,不算测试
- 真正的测试必须在 `tests/` 下,能被 `pytest` 收集

---

## 2. 集成测试(End-to-End)

### 范围
- 真实连 Milvus / ES / LLM API
- 数据量小(10-100 条样本)
- 频率低(只在 Phase 结束跑一次)

### 文件
- 放 `tests/integration/`
- 文件名 `test_e2e_{phase}.py`
- 用 `@pytest.mark.integration` 标记
- 默认不跑,需要 `pytest -m integration`

```python
# pyproject.toml 添加
[tool.pytest.ini_options]
markers = [
    "integration: 需要外部服务,默认不跑",
]
```

---

## 3. 评估流程

### 何时跑评估
- 每个 Phase 完成后
- 单次重要改动(比如换 Embedding 模型)前后

### 标准流程
```bash
# 1. 确保数据已 ingest
python scripts/ingest.py --collection chunks_v{N}

# 2. 跑评估
python scripts/run_eval.py \
  --phase {N} \
  --eval data/eval/eval_v1.jsonl \
  --collection chunks_v{N}

# 3. 自动写入 docs/metrics.md(由 src/eval/metrics_logger.py 完成)
```

### 必须报告的指标

**Phase 1-3(检索阶段)**:
- `Recall@3`, `Recall@5`, `Recall@10`
- `MRR`(Mean Reciprocal Rank)
- `Hit@K`

**Phase 4 后(端到端)**:
- 上面所有
- RAGAS 四件套:`faithfulness`, `answer_relevancy`, `context_recall`, `context_precision`
- 端到端准确率(人工抽查或 LLM-as-judge)

**Phase 5(性能)**:
- P50 / P95 / P99 延迟
- QPS
- 错误率

---

## 4. `docs/metrics.md` 写入格式 🔒

**追加式**:每次评估在文件末尾新增一节,不覆盖历史。

```markdown
## Phase {N} - {简短描述} - {YYYY-MM-DD}

**配置**:
- Embedding: `BAAI/bge-m3`
- Retriever: `Hybrid(Dense + BM25, RRF k=60)`
- Reranker: `none`
- LLM: `deepseek-chat`
- Eval set: `data/eval/eval_v1.jsonl` (100 条)

**主指标**:

| Metric | Value | Δ vs baseline |
|--------|-------|---------------|
| Recall@3 | 0.78 | +0.16 |
| Recall@5 | 0.85 | +0.13 |
| Recall@10 | 0.91 | +0.09 |
| MRR | 0.72 | +0.18 |

**消融**(可选):

| Setting | Recall@3 |
|---------|----------|
| Dense only | 0.64 |
| BM25 only | 0.58 |
| Hybrid (RRF) | 0.78 |

**备注**:
- (一两句话讲清楚关键发现或问题)
```

### 写入由代码完成
**不要手写**这部分,用 `src/eval/metrics_logger.py` 的 `append_phase_report()` 函数自动生成,保证格式一致。

---

## 5. 性能基准

每个 Phase 完成时,记录一组性能数据到 `docs/metrics.md`,格式:

```markdown
**性能**:

| Stage | Latency (P50/P95/P99) | Notes |
|-------|----------------------|-------|
| Query embedding | 15/30/45 ms | bge-m3 CPU |
| Milvus search | 8/15/25 ms | HNSW, top_k=50 |
| BM25 search | 20/40/60 ms | ES 单节点 |
| RRF fusion | <1 ms | 纯 Python |
| Rerank | 200/350/500 ms | bge-reranker, top_n=50 |
| LLM generate | 2.5/4.0/6.0 s | DeepSeek streaming first token |
```

---

## 6. 当指标下降时

**立刻停止**,按下面流程:

1. `git diff` 看最近改了什么
2. 跑一遍上一个 commit:`git stash && pytest && python scripts/run_eval.py`,确认 baseline 仍 OK
3. `git stash pop`,二分定位是哪个改动导致的
4. 在 `docs/decisions/` 写一份 ADR 记录问题和决策
5. 向用户报告,等指示

**禁止**:
- ❌ 自己继续"修补",改一堆地方
- ❌ 隐藏负面结果只报告正面
