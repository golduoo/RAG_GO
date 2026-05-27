# ADR-005: ES 安装 analysis-ik 中文分词插件(ik_smart)

- **状态**:Accepted
- **日期**:2026-05-28
- **决策者**:AI 建议 + 用户确认

---

## 1. 背景(Context)

ADR-003 决定 Phase 1 的 ES 索引先用 `standard` analyzer 兜底,并承诺"Phase 2 起始作为
前置步骤装 ik 插件"。Phase 2 要做 BM25 / 混合检索(T2.2、T2.3),关键词检索质量直接依赖
中文分词:`standard` analyzer 对中文是逐字切分,会把"物流""时效"等词拆成单字,严重
影响 BM25 的词项匹配。因此进 Phase 2 第一步(T2.0)必须先把 ik 插件接入。

ES 容器为官方原版 `docker.elastic.co/elasticsearch/elasticsearch:8.15.3`,未预装任何插件。

---

## 2. 决策(Decision)

在 ES 容器内安装 `analysis-ik` 插件(版本与 ES 对齐 = 8.15.3),重启激活。后续 Phase 2
的 BM25 / 混合检索索引默认使用 `ik_smart` analyzer。

安装命令(容器内):
```
bin/elasticsearch-plugin install -b https://get.infini.cloud/elasticsearch/analysis-ik/8.15.3
```
随后 `docker compose restart elasticsearch`。

---

## 3. 理由(Rationale)

- 版本严格对齐:ES 插件要求与内核同版本,8.15.3 插件直接匹配当前容器
- 直链来自 infinilabs(analysis-ik 官方维护方),绕开 HF 镜像不兼容问题(见 HANDOFF §2.3)
- `-b`(batch)自动接受插件 `SocketPermission` 权限提示,避免交互式卡住
- ik 提供 `ik_smart`(粗粒度)与 `ik_max_word`(细粒度)两种 analyzer,满足 BM25 召回需要

---

## 4. 代价 / 取舍(Consequences)

**好的**:
- 中文按词切分,BM25 词项匹配质量显著优于 `standard`(见 §6 验证)
- 为 T2.2(BM25Retriever)铺好分词基础,无需写入端 jieba 预切分的 fallback

**不好的**:
- 插件随容器走:若 ES 容器被 `docker compose down`(删容器)重建,需重新安装。
  插件装在容器层而非数据卷,这是已知运维点(记入 HANDOFF)
- ik 默认词典对部分专有名词(如"顺丰速运")仍逐字切分;如需可后续挂自定义词典,
  Phase 2 暂不做

---

## 5. 影响范围

- **基础设施**:仅 ES 容器,新增 `analysis-ik` 插件 + 一次重启
- **代码**:本任务无代码改动;后续 T2.2 的 BM25 索引 settings 会指定 `ik_smart`
- **索引**:本任务**不重建索引**;重建留到 T2.1 多粒度切分后统一 ingest 到 `chunks_v2`
- **不改**:`data-schemas.md` §4(已含 ik_smart 默认 + fallback 条款)

---

## 6. 验证

通过 ES `_analyze` API 对比(文本:`顺丰速运的物流时效和退货政策`):

| analyzer | 切分结果 |
|----------|----------|
| `ik_smart` | 顺 / 丰 / 速 / 运 / 的 / **物流** / **时效** / 和 / **退货** / **政策** |
| `standard` | 顺 / 丰 / 速 / 运 / 的 / 物 / 流 / 时 / 效 / 和 / 退 / 货 / 政 / 策 |

ik 正确把"物流/时效/退货/政策"识别为词,`standard` 全部逐字切分。
`bin/elasticsearch-plugin list` 输出 `analysis-ik`,插件加载成功。

---

## 7. 后续

- T2.1:多粒度切分后,新建索引 `chunks_v2` 时显式指定 `analyzer: ik_smart`
- T2.2:BM25Retriever 基于 `ik_smart` 索引;若需更高召回可试 `ik_max_word`
- 若专有名词召回不佳,可挂自定义词典(ik 的 `IKAnalyzer.cfg.xml`),Phase 2 视情况决定
- 运维:ES 容器重建后需重装插件,已记入 HANDOFF §2
