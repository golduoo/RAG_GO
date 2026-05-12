# Phase 3: Query 改写 + Rerank

> **目标**:Top-3 准确率冲到 82%+
> **预计**:1 周 / 30h
> **前置**:Phase 2 完成

---

## Phase 总 DoD
- [ ] 意图识别准确率 ≥ 85%(20 条标注样本)
- [ ] HyDE / Multi-Query 改写可配置启用
- [ ] Cross-Encoder rerank 集成,端到端延迟 ≤ 2s(GPU)或 ≤ 5s(CPU)
- [ ] 四列对比表:Baseline / +Hybrid / +Rewrite / +Rerank
- [ ] Top-3 准确率 ≥ 82%
- [ ] `docs/metrics.md` 多一节 "Phase 3"

---

## Tasks

### T3.1 意图识别
**目标**:把 query 路由到合适的处理链路
**步骤**:
1. `src/query/intent.py`:LLM 分类器
2. 输出枚举:`chat` / `single_hop` / `multi_hop` / `unknown`
3. Prompt 给 5-8 个 few-shot
4. 人工标 20 条,跑准确率 ≥ 85%

**DoD**:准确率达标,集成进 pipeline

---

### T3.2 HyDE
**目标**:让 LLM 先生成假设答案,用假设答案的向量检索
**步骤**:
1. `src/query/rewrite.py`:`HydeRewriter`
2. Prompt 限定:扮演物流专家,假设答案 ≤ 100 字
3. 单元测试覆盖
4. 集成到 pipeline,可通过 config 开关

**DoD**:启用 HyDE 后,在 single_hop 子集上 Recall@3 进一步提升

---

### T3.3 Multi-Query 扩展
**目标**:把 query 扩展成 3-5 条变体并行检索
**步骤**:
1. 同文件:`MultiQueryRewriter.rewrite(q) -> list[str]`
2. HybridRetriever 接受 query list,每条都跑一遍,然后 RRF
3. 注意成本:乘以变体数,latency 也会增加

**DoD**:接口可配置,默认关闭(Phase 4 评估时再启用对比)

---

### T3.4 Cross-Encoder Rerank ⭐ 核心
**目标**:召回 top-50 → rerank top-3
**步骤**:
1. `src/rerank/cross_encoder.py`:封装 `bge-reranker-v2-m3`
2. 支持 batch 推理,fp16
3. pipeline 改造:
   - 召回阶段:`top_k=50`
   - rerank 阶段:取 reranker 排序后的 top-3 给 LLM
4. 性能优化:
   - 提前 warmup
   - batch 至少 16 条同时推理

**DoD**:
- 端到端延迟:本地 GPU ≤ 2s,CPU ≤ 5s
- Recall 不下降,Precision@3 显著提升

---

### T3.5 Phase 3 评估
**步骤**:
1. 跑完整链路,生成四列对比表
2. 写入 `docs/metrics.md`

**DoD**:Top-3 准确率达 82%+

---

## Phase 3 结束动作
- 勾选 `progress.md`
- 写 `ADR-003-rerank-and-rewrite.md`,记录:
  - 为什么用 Cross-Encoder 不用 ColBERT
  - HyDE 在哪些 case 显著帮助、哪些没用
  - Rerank 的 latency 权衡
