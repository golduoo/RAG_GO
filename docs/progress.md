# Progress

> **当前指针**:每次会话从这里开始读。完成 Task 后必须更新。

---

## 📍 当前位置

- **Active Phase**: `Phase 2 - 混合检索 + 多粒度切分`(等用户确认进入)
- **Active Task**: `T2.0 - 装 ES ik 中文分词插件`(Phase 2 前置)
- **下一步**:用户 review ADR-004,确认 Phase 1 收尾;然后 `view docs/tasks/phase-2.md` 启动

---

## 阶段总览

| Phase | 主题 | 状态 | 完成日期 | 关键产出指标 |
|-------|------|------|---------|-------------|
| 1 | Baseline:基础设施 + Dense 检索 | ✅ 完成 | 2026-05-13 | Recall@3=0.931 (合成评估,见 ADR-004) |
| 2 | 混合检索 + 多粒度切分 | ⬜ 未开始 | - | Recall@3 ≥ baseline+8pp |
| 3 | Query 改写 + Rerank | ⬜ 未开始 | - | Top-3 准确率 ≥ 82% |
| 4 | 评估体系 + GraphRAG | ⬜ 未开始 | - | RAGAS faithfulness ≥ 0.8 |
| 5 | 工程化 + Go 网关 | ⬜ 未开始 | - | docker-compose 一键起 |
| 6 | 收尾 + 简历准备 | ⬜ 未开始 | - | README + Demo 视频 |

---

## Task 完成日志(追加式,每完成一个 Task 加一行)

模板:
```
- [x] T1.1 项目初始化 (2026-05-12) — 备注: 用 uv 初始化,目录结构对齐 §rules/project.md
```

### Phase 1
- [x] T1.1 项目初始化 (2026-05-12) — 备注: uv 0.11.13 + Python 3.12,目录结构对齐 §rules/project.md;`uv run python -c "import src"` OK
- [x] T1.2 基础设施 Docker Compose (2026-05-13) — 备注: 6 容器全 healthy;Milvus 2.4.15 / ES 8.15.3 / Neo4j 5.24.2 / Redis 7.4.9;新增 redis-py 客户端
- [x] T1.3 数据下载与初步加工 (2026-05-13) — 备注: ADR-002 pivot 通用 RAG;DuReader 100k → 分层采样 8000 (1816 logistics + 6184 other);hf-mirror 直链下载
- [x] T1.4 文档解析与切分 (2026-05-13) — 备注: FixedTokenSplitter (tiktoken cl100k_base) + RecursiveCharacterSplitter,默认 400/50;21 测试全绿
- [x] T1.5 Embedding 与入库 (2026-05-13) — 备注: BGE-M3 fp16 on RTX 4060,10786 chunks,221.8s 总耗时;Milvus=ES=10786;ADR-003 ES standard fallback
- [x] T1.6 Dense 检索 Baseline (2026-05-13) — 备注: Retriever ABC + DenseRetriever (BGE-M3 + Milvus HNSW),7 mock 测试全绿,CLI 真实查询返回相关段落
- [x] T1.7 LLM 调用封装 (2026-05-13) — 备注: DeepSeek OpenAI 兼容,tenacity 3x 指数退避只重试 5xx/限流,流式 + 非流式,12 测试全绿
- [x] T1.8 Baseline End-to-End (2026-05-13) — 备注: RagPipeline (Retriever + LLM),6 mock 测试全绿,真实 E2E 答案带 [N] 引用 + 区分顺丰标准/特惠
- [x] T1.9 评估集构造 + 初始指标 (2026-05-13) — 备注: 100 条 DeepSeek 合成 QA;Recall@3=0.931 Hit@5=1.0 MRR=0.976;指标高于预期(eval 泄漏,见 ADR-004 §4)

### Phase 2-6
任务清单在对应的 `docs/tasks/phase-N.md`,完成时来这里勾选。

---

## 最近指标

| Phase | Eval set | Recall@3 | Recall@5 | Recall@10 | MRR | 注 |
|-------|----------|----------|----------|-----------|-----|-----|
| 1 | eval_v1 (合成) | 0.9310 | 0.9572 | 0.9755 | 0.9758 | 有词面泄漏 |
| 1 | eval_v1_paraphrased | 0.8740 | 0.9152 | 0.9388 | 0.9116 | **抗泄漏对照,后续 Phase 主用** |

详见 `docs/metrics.md`。

---

## 决策记录

详见 `docs/decisions/`。每次重要技术决策写一份 ADR。

| ADR | 标题 | 日期 |
|-----|------|------|
| [001](decisions/ADR-001-pin-python-3.12.md) | 把项目 Python 钉到 3.12 | 2026-05-12 |
| [002](decisions/ADR-002-pivot-to-general-chinese-rag.md) | 项目定位 → 通用中文 RAG(物流作 demo) | 2026-05-13 |
| [003](decisions/ADR-003-es-analyzer-fallback.md) | Phase 1 ES 用 standard 分词器,Phase 2 切 ik_smart | 2026-05-13 |
| [004](decisions/ADR-004-phase1-baseline.md) | Phase 1 收尾总结(含合成评估集泄漏警讯) | 2026-05-13 |
