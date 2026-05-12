# ADR-002: 项目定位从"物流场景"调整为"通用中文 RAG(以物流为示例 demo)"

- **状态**:Accepted
- **日期**:2026-05-13
- **决策者**:用户主导 + AI 建议

---

## 1. 背景(Context)

`claude.md`、`docs/rules/project.md` §1、`docs/tasks/phase-1.md` T1.3 把项目定位为
"物流场景企业级知识库 RAG 系统",T1.3 指定关键词 `快递|物流|运输|包裹|寄送|海关|赔付|运单|时效|配送|签收` 从 DuReader 段落语料中筛出 5000–10000 条物流相关段落。

T1.3 实际执行结果:DuReader 100,001 条段落中,11 个关键词只命中 **1,816** 条,远低于 DoD 下限 5000。
DuReader 是通用百科 QA 语料,物流密度本就低,扩充关键词最多到 4000–5000,仍不够稳定。

更重要的是:**用户的核心诉求是用本项目展示 RAG 优化能力**(chunk 策略、混合检索、Query 改写、rerank、GraphRAG、评估闭环),这些技能与"是否物流领域"无关。把领域硬绑死反而增加数据获取摩擦。

## 2. 决策(Decision)

项目定位调整为 **"通用中文知识库 RAG 系统,以物流问答作为示例 demo"**。

具体落地:
1. **数据获取改为随机采样**:从 DuReader 段落语料随机采 **8000** 条(seed=42 固定),不做硬过滤
2. **保留物流软标签**:每条 Document 在 `metadata` 里加 `is_logistics: bool` 字段,便于后续做领域切片分析
3. **评估集(T1.9)不限领域**:LLM 直接从采样段落生成 QA,不强制物流主题
4. **项目名 `sf-rag-kb` 保留**:避免大规模重命名;简历层面解释为通用 RAG,以顺丰物流场景做 demo
5. **Phase 4 GraphRAG schema**(`data-schemas.md` §5 的 Service/City/Rule)**暂留**,进入 Phase 4 时再决定是否换成通用实体类型——不影响 Phase 1–3

## 3. 理由(Rationale)

- 简历价值在 RAG 优化方法论,不在数据领域
- DuReader 是中文 RAG 标准语料,通用领域反而更能体现方法的迁移性
- 不改主语料(DuReader)、不改技术栈、不改目录结构,改动面最小
- 软标签 `is_logistics` 让物流子集后续仍可单独评估,demo 故事讲得通

## 4. 代价 / 取舍(Consequences)

**好的**:
- T1.3 立即解锁(8000 条样本稳定)
- Phase 1–3 完全不受影响,所有 RAG 优化照常推进
- 评估覆盖面更广(通用中文 QA 比纯物流子集统计学意义更强)

**不好的**:
- 简历"专注物流知识库"叙事弱化为"以物流为示例"
- Phase 4 GraphRAG 的实体 schema(Service/City/Rule)在通用语料上召回率会下降,届时可能需要二次调整
- `docs/rules/project.md` §1 "目标"字段措辞过期,但本 ADR 已覆盖,不强求改 §1(锁定章节,避免连锁修改)

## 5. 影响范围

- **改动**:
  - `docs/tasks/phase-1.md` T1.3 步骤 2 改"关键词过滤"为"随机采样,关键词作为软标签"
  - `scripts/filter_logistics.py` 默认行为改为随机采样
- **不改**:
  - `claude.md`(标题"物流场景"保留作为 demo 定位)
  - `docs/rules/project.md` §1(锁定章节,本 ADR 覆盖)
  - `docs/rules/data-schemas.md`(Document/Chunk 模型未变;Phase 4 GraphRAG 暂留)
  - 目录结构、技术栈、所有 RAG 算法相关 task

## 6. 验证

- 采样后 jsonl 行数 ≈ 8000(在 DoD 区间 5000–10000 内)
- 抽 10 条人工 check,内容多样(不限物流)
- `is_logistics: true` 的子集约 1800 条,与 T1.3 关键词命中数对齐

## 7. 后续

- Phase 4 启动前 review GraphRAG schema 是否需要改通用实体类型(`Entity, Concept, Event` 等)
- 若简历环节用户更倾向纯物流叙事,可在 Phase 6 收尾时把通用语料替换为更聚焦的物流语料(届时只改 T1.3 一处)
