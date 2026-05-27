# 学习路径(Phase 1 复盘 + 技术栈讲解)

> 这是个人学习笔记,以**本项目实际用过的技术**为锚,按 RAG 主线一路讲下来。
> 配套 `docs/decisions/` 的 ADR 一起看,理论+决策双线。

---

## 📍 两套学习材料

### A. 主题概念篇(按 RAG 原理)
| # | 主题 | 状态 | 关联代码 |
|---|------|------|---------|
| 01 | [Embedding 与向量空间](01-embedding-and-vectors.md) | ✅ | `src/ingest/indexer.py` BGEEmbedder |
| 02 | [向量库 & HNSW 索引](02-vector-db-and-hnsw.md) | ✅ | `src/ingest/indexer.py` MilvusWriter |
| 03 | Chunking 策略 | ⬜ | `src/ingest/splitters.py` |
| 04 | 检索质量评估 | ⬜ | `src/eval/metrics.py` |
| 05 | LLM 调用工程(streaming / retry) | ⬜ | `src/generate/llm.py` |
| 06 | RAG Prompt 工程 | ⬜ | `src/generate/prompts.py` |

### B. 代码精读篇(逐文件逐行讲,**当前主用**)
| # | 文件 | 状态 |
|---|------|------|
| 01 | [src/config.py](code-01-config.md) | ✅ |
| 02 | [src/logger.py](code-02-logger.md) | ✅ |
| 03 | [src/ingest/schema.py](code-03-schema.md) | ✅ |
| 04 | src/ingest/splitters.py | ⬜ |
| 05 | src/ingest/indexer.py | ⬜ |
| 06 | scripts/ingest.py | ⬜ |
| 07 | src/retrieval/base.py + dense.py | ⬜ |
| 08 | src/generate/prompts.py + llm.py | ⬜ |
| 09 | src/generate/pipeline.py | ⬜ |
| 10 | src/eval/* + scripts/run_eval.py | ⬜ |

---

## 阅读约定

每一篇文档结构:
1. **直觉先行** — 先用类比讲清楚"在干嘛"
2. **技术细节** — 数学/参数/代码
3. **本项目落地** — 链回我们实际写的代码,逐行讲
4. **常见坑** — 生产环境会遇到的问题
5. **自测题** — 学完应该能回答的问题(没答案,逼你自己想清楚)

---

## 时间投入预估

每篇 30-60 分钟阅读 + 30 分钟在代码里查证,总共 6 篇,大约 1-2 个白天能过完。
**不要**一次性读完,**每读完一篇,在代码里实际打开对应文件对照一遍**,才会记得住。
