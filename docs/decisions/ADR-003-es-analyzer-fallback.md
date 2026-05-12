# ADR-003: Phase 1 ES 分词器使用 standard,Phase 2 引入 ik_smart

- **状态**:Accepted
- **日期**:2026-05-13
- **决策者**:AI 建议 + 用户后续确认(默认采纳)

---

## 1. 背景(Context)

`docs/rules/data-schemas.md` §4 规定 ES index 默认 analyzer 为 `ik_smart`(中文分词),
并注明:"若 ik_smart 未安装,fallback 用 standard analyzer,但要在 ADR 中记录"。

T1.5 阶段:Elasticsearch 8.15.3 容器是官方原版,**未预装 ik 中文分词插件**。
要装 `elasticsearch-analysis-ik` 需要:
- 进容器跑 `elasticsearch-plugin install`(网络下 plugin 包)
- 重启 ES 容器使其生效

Phase 1 baseline 暂时**不依赖 BM25 / 关键词检索**(T1.6 只做 Dense),所以 ES 入库
的 analyzer 不影响 baseline 指标。Phase 2(混合检索 + BM25)才真正需要中文分词。

## 2. 决策(Decision)

- **Phase 1**:ES index 用 **standard analyzer**(按 Unicode 字符切分,中文几乎等于
  逐字),T1.5 indexer 不强求 ik
- **Phase 2 起始**:作为 T2.1(BM25 检索)的前置步骤,装 ik 插件 + 重建索引

## 3. 理由(Rationale)

- T1.5 DoD 只要求 "ES 文档数 == jsonl 切分后的 chunk 数",对召回质量无要求
- 装 ik 需要重启 ES,可能影响其他容器(虽然依赖关系上 Milvus/Neo4j/Redis 独立)
- Phase 2 必然要重建索引(混合检索方案会涉及 ES schema 微调),一起做更经济
- 避免 ADR-002 之后再连环改基础设施

## 4. 代价 / 取舍(Consequences)

**好的**:
- T1.5 一次成功,不引入 ik 插件下载和容器重启
- 把 ik 切换收敛到 Phase 2,影响面清晰

**不好的**:
- 万一在 Phase 1 想做 quick BM25 对照(标准建议是做),效果会差
- Phase 2 启动时必须先做 ik 接入,T2.1 增加一个前置步骤

## 5. 影响范围

- **改动**:无新增代码,只是 indexer 默认 settings 用 standard
- **新增 Phase 2 前置**:T2.1 开头加"装 ik 插件 + 重建 chunks_v? index"
- **不改**:`data-schemas.md` §4 文本(已包含 fallback 条款)

## 6. 验证

- T1.5 完成后:`GET /chunks_v1/_settings` 应看到 standard analyzer
- Phase 2 开始时,可通过 `_analyze` API 对比 ik_smart vs standard 切分效果

## 7. 后续

- T2.1 第一步:容器内装 ik 插件,重建索引 `chunks_v1`(或新版本号 `chunks_v2`)
- 若 ik 安装失败,fallback 用 jieba 在写入端预切分,空格拼接后存 text 字段
