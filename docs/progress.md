# Progress

> **当前指针**:每次会话从这里开始读。完成 Task 后必须更新。

---

## 📍 当前位置

- **Active Phase**: `Phase 1 - Baseline`
- **Active Task**: `T1.3 - 数据下载与初步加工`(未开始)
- **下一步**:`view docs/tasks/phase-1.md`,从 T1.3 开始

---

## 阶段总览

| Phase | 主题 | 状态 | 完成日期 | 关键产出指标 |
|-------|------|------|---------|-------------|
| 1 | Baseline:基础设施 + Dense 检索 | ⏳ 进行中 | - | Recall@3 baseline |
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
- [ ] T1.3 数据下载与初步加工
- [ ] T1.4 文档解析与切分
- [ ] T1.5 Embedding 与入库
- [ ] T1.6 Dense 检索 Baseline
- [ ] T1.7 LLM 调用封装
- [ ] T1.8 Baseline End-to-End
- [ ] T1.9 评估集构造 + 初始指标

### Phase 2-6
任务清单在对应的 `docs/tasks/phase-N.md`,完成时来这里勾选。

---

## 最近指标

详见 `docs/metrics.md`。当前 baseline 未跑出,无数据。

---

## 决策记录

详见 `docs/decisions/`。每次重要技术决策写一份 ADR。

| ADR | 标题 | 日期 |
|-----|------|------|
| [001](decisions/ADR-001-pin-python-3.12.md) | 把项目 Python 钉到 3.12 | 2026-05-12 |
