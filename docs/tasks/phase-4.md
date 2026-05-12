# Phase 4: 评估体系 + GraphRAG

> **目标**:上 RAGAS 自动化评估,并用 GraphRAG 提升多跳问题准确率
> **预计**:1 周 / 35h
> **前置**:Phase 3 完成

---

## Phase 总 DoD
- [ ] RAGAS 四指标全部能跑通(faithfulness / answer_relevancy / context_recall / context_precision)
- [ ] 在 CRUD-RAG 子集上跑出结果
- [ ] Neo4j 中有不少于 1000 个节点 + 不少于 2000 条边的知识图谱
- [ ] GraphRAG retriever 可接入 pipeline,多跳 query 准确率显著提升
- [ ] faithfulness ≥ 0.8(LLM-as-judge)
- [ ] 幻觉率(人工抽样 50 条)< 5%

---

## Tasks

### T4.1 RAGAS 集成
**步骤**:
1. `src/eval/ragas_runner.py`:跑 RAGAS 四件套
2. 用 DeepSeek 作为 LLM-as-judge(自定义 LLM wrapper)
3. 输出 JSON 报告到 `data/eval/reports/ragas_phase4_{timestamp}.json`
4. 自动追加汇总到 `docs/metrics.md`

**DoD**:能稳定产出报告,RAGAS API 调用稳定(加 retry)

---

### T4.2 CRUD-RAG benchmark
**步骤**:
1. 接入 CRUD-RAG 的 single-doc QA 子集
2. 用本项目的 pipeline 跑通
3. 用论文里的指标算法(BLEU / ROUGE / 准确率)算分

**DoD**:`docs/metrics.md` 多一行 CRUD-RAG 分数(可对比论文 SOTA)

---

### T4.3 实体关系抽取
**目标**:从 corpus 抽出物流领域的三元组
**步骤**:
1. `src/graph/extractor.py`:
   - 实体类型:`Service` / `City` / `Rule` / `Penalty`
   - 关系:`COVERS` / `APPLIES_TO` / `TRIGGERS` / `CONNECTS`
   - 见 `docs/rules/data-schemas.md` §5
2. Prompt 设计(few-shot)
3. 输出 `data/processed/triples.jsonl`
4. 人工抽 30 条 check 准确率 ≥ 70%

**DoD**:三元组文件存在,质量达标

---

### T4.4 Neo4j 入库
**步骤**:
1. `src/graph/store.py`:Cypher 批量写
2. 用 `MERGE` 不用 `CREATE`(自动去重)
3. 在 `(label, name)` 上加 unique 约束

**DoD**:`docker exec neo4j cypher-shell` 能查到节点和关系,Browser UI 看到图谱

---

### T4.5 Graph 检索 + 融合 ⭐ 核心
**步骤**:
1. `src/graph/retriever.py`:
   - 从 query 抽实体(用 T4.3 的抽取器,但只抽实体)
   - 在 Neo4j 跑多跳 Cypher(2-3 跳)
   - 把子图转成文本(`{Service} 覆盖 {City},触发规则 {Rule},赔付 {Penalty}`)作为 context
2. pipeline 路由:
   - `single_hop` → hybrid + rerank
   - `multi_hop` → graph + hybrid + rerank,context 拼接
3. 准备 20 条多跳测试 query

**DoD**:多跳 query 准确率提升明显(典型场景下 30+pp)

---

### T4.6 Self-RAG 兜底
**目标**:基于 faithfulness 阈值兜底
**步骤**:
1. 生成答案后,跑一次 faithfulness 检查
2. 低于阈值(默认 0.7)→ 改为"知识库中未找到准确信息"或重新检索
3. 阈值通过 config 暴露

**DoD**:50 条抽样幻觉率显著下降

---

## Phase 4 结束动作
- 勾选 `progress.md`
- 写 `ADR-004-graphrag.md`,记录:
  - 实体/关系 schema 设计的取舍
  - 多跳问题的典型 case 分析
  - GraphRAG 的成本(extraction 阶段调用 LLM 的次数)
