# Phase 1: Baseline 基础设施 + Dense 检索

> **目标**:跑通 query → 检索 → 生成的最简单流程,记录初始指标作为后续优化的对照组。
> **预计时间**:1 周(约 25 小时)
> **结束标志**:能跑出 baseline 评估指标,写入 `docs/metrics.md`,并且 `docker compose up -d` 起来所有服务健康。

---

## Phase 总 DoD

完成本 Phase 时,以下全部满足:
- [ ] `python -c "import src"` 成功,目录结构符合 `docs/rules/project.md` §3
- [ ] `docker compose up -d` 起来 Milvus + ES + Neo4j + Redis 全部健康
- [ ] `data/processed/logistics_corpus.jsonl` 存在,行数 5000-10000
- [ ] Milvus collection `chunks_v1` 行数等于 jsonl 行数
- [ ] CLI `python -m src.generate.pipeline --query "顺丰特快多久到"` 能返回带引用的答案
- [ ] `docs/metrics.md` 第一节存在,标题为 "Phase 1 - Baseline - {日期}"
- [ ] `docs/progress.md` 中 Phase 1 所有 Task 勾选

---

## Tasks

### T1.1 项目初始化
**输入**:无
**产出**:符合 `docs/rules/project.md` §3 的目录骨架 + 可工作的 Python 环境
**步骤**:
1. 按 `docs/rules/project.md` §3 创建所有目录,空 `__init__.py`,占位 README
2. 写 `pyproject.toml`(完全照搬 `docs/rules/project.md` §2)
3. 写 `.env.example`,列所有需要的环境变量
4. 写 `.gitignore`(Python + Go + 数据 + IDE)
5. `uv sync` 安装通过
6. 初始化 git,首次 commit `chore: project init`

**DoD**:`uv run python -c "import src"` 成功

---

### T1.2 基础设施 Docker Compose
**输入**:无
**产出**:`docker-compose.yml` + `scripts/check_infra.py`
**步骤**:
1. 写 `docker-compose.yml`,包含:
   - Milvus standalone(+ etcd + minio,参考 [官方 yml](https://milvus.io/docs/install_standalone-docker-compose.md))
   - Elasticsearch 8.15.x 单节点,禁用 security(`xpack.security.enabled=false`)
   - Neo4j 5.x community
   - Redis 7
2. 健康检查:每个服务配置 `healthcheck`
3. 写 `scripts/check_infra.py`,逐个连接四个服务并打印版本

**DoD**:
- `docker compose up -d` 起来,`docker compose ps` 全部 healthy
- `uv run python scripts/check_infra.py` 全部 OK

---

### T1.3 数据下载与初步加工
**输入**:无
**产出**:`data/processed/logistics_corpus.jsonl`

> **变更说明(ADR-002)**:项目定位调整为"通用中文 RAG,以物流为示例 demo",
> 因此本步骤改为"随机采样 + 物流软标签",而非硬关键词过滤。

**步骤**:
1. 写 `scripts/download_data.py`(+ `.sh` 薄封装),从 HuggingFace 拉 `C-MTEB/DuRetrieval` 的 corpus parquet(国内走 hf-mirror 镜像)
2. 写 `scripts/filter_logistics.py`:
   - 从 corpus 随机采样 ~8000 条(seed=42 固定,可 `--target-size` 调整)
   - 长度过滤:`min_len=20`, `max_len=2000`
   - 关键词作为**软标签**写入 metadata:`is_logistics: bool`,关键词列表 `快递|物流|运输|包裹|寄送|海关|赔付|运单|时效|配送|签收`
   - 输出格式:`Document` 模型的 jsonl(见 `docs/rules/data-schemas.md` §1)
3. (可选)补充几份国家邮政局公开规章手动放 `data/raw/regulations/`,数量 5-10 份——demo 阶段做即可,非阻塞

**DoD**:
- `wc -l data/processed/logistics_corpus.jsonl` 在 [5000, 10000] 之间
- 随机抽 10 条人工 check,内容多样,字段格式符合 Document schema
- metadata 里 `is_logistics: true` 的子集行数约 1500–2500(便于后续物流子集评估)

---

### T1.4 文档解析与切分
**输入**:`data/processed/logistics_corpus.jsonl` + raw 目录的 PDF
**产出**:`src/ingest/splitters.py` + 测试
**步骤**:
1. 实现 `FixedTokenSplitter`(baseline):按固定 token 数切,带 overlap
2. 实现 `RecursiveCharacterSplitter`:按段落 → 句子 → 词递归切
3. 默认参数:`chunk_size=400`, `chunk_overlap=50`
4. 输出 `Chunk` 模型(见 `docs/rules/data-schemas.md` §1)
5. 写 `tests/ingest/test_splitters.py`,覆盖:正常文本、超短文本、超长文本、空文本

**DoD**:
- `uv run pytest tests/ingest/test_splitters.py -v` 全绿
- 测试至少包含 3 个 case

---

### T1.5 Embedding 与入库
**输入**:T1.4 的 Chunk + 一个 collection 名(`chunks_v1`)
**产出**:`src/ingest/indexer.py` + `scripts/ingest.py`
**步骤**:
1. `src/ingest/indexer.py`:
   - 加载 `BAAI/bge-m3`,fp16,支持 CPU fallback
   - 批量 embed(batch_size=32)
   - 写 Milvus collection(schema 见 `docs/rules/data-schemas.md` §3)
   - HNSW 索引,`M=16, efConstruction=200`,COSINE metric
2. 同步写 ES(schema 见 `docs/rules/data-schemas.md` §4)
3. `scripts/ingest.py` 编排:读 jsonl → 切分 → embed → 双写
4. 记录耗时(写 `docs/metrics.md` 的"备注"部分)

**DoD**:
- Milvus collection 行数 == ES 文档数 == jsonl 切分后的 chunk 数
- Milvus 索引 `M=16, efConstruction=200` 已建好
- 跑完时间记录下来

---

### T1.6 Dense 检索 Baseline
**输入**:`chunks_v1` collection
**产出**:`src/retrieval/base.py` + `src/retrieval/dense.py` + 测试
**步骤**:
1. `src/retrieval/base.py`:定义 `Retriever` 抽象基类
   ```python
   class Retriever(ABC):
       @abstractmethod
       def search(self, query: str, top_k: int = 10) -> list[RetrievedDoc]: ...
   ```
2. `src/retrieval/dense.py`:实现 `DenseRetriever`
3. CLI:`python -m src.retrieval.dense --query "..." --top-k 5`
4. 测试用 mock_milvus fixture,验证 query embedding 和 search 调用

**DoD**:
- CLI 能返回 top-5,打印 score 和片段
- 测试通过

---

### T1.7 LLM 调用封装
**输入**:无
**产出**:`src/generate/llm.py` + `src/generate/prompts.py`
**步骤**:
1. `src/generate/llm.py`:
   - 封装 OpenAI 兼容客户端,从 `settings` 读配置
   - 支持流式(`generator`)和非流式
   - 用 `tenacity` 加 retry:最多 3 次,指数退避,只重试 5xx 和限流
2. `src/generate/prompts.py`:写 baseline RAG prompt 模板
   ```python
   RAG_PROMPT = """你是物流知识问答助手。基于下面的资料回答问题。

   资料:
   {context}

   问题:{query}

   要求:
   - 仅根据资料作答,不要编造
   - 引用资料时用 [1][2] 标注
   - 资料中找不到答案时,明确说明"知识库中未找到相关信息"
   """
   ```

**DoD**:
- `uv run python -m src.generate.llm --prompt "你好"` 流式输出
- 测试覆盖正常调用和 retry 路径

---

### T1.8 Baseline End-to-End
**输入**:T1.6 + T1.7
**产出**:`src/generate/pipeline.py`
**步骤**:
1. 实现 `RagPipeline`:
   ```python
   class RagPipeline:
       def __init__(self, retriever, llm, top_k=5): ...
       def ask(self, query: str) -> Answer: ...
   ```
2. CLI:`python -m src.generate.pipeline --query "..."`
3. 输出 `Answer` 模型,带 citations

**DoD**:
- CLI 能跑通,输出格式:答案文本 + [1][2] 引用 + 来源列表

---

### T1.9 评估集构造 + 初始指标
**输入**:T1.3 的 logistics_corpus
**产出**:`data/eval/eval_v1.jsonl` + 第一行 `docs/metrics.md`
**步骤**:
1. `scripts/build_eval_set.py`:
   - 从 corpus 随机采 100 条
   - 对每条让 LLM 生成 question + answer + gold_doc_ids
   - 输出按 `docs/rules/data-schemas.md` §2 格式
   - LLM 用 DeepSeek
2. `src/eval/metrics_logger.py`:
   - 实现 Recall@K, MRR, Hit@K
   - 实现 `append_phase_report(phase, config, metrics, notes)` 写入 `docs/metrics.md`
3. `scripts/run_eval.py --phase 1`:跑 baseline,自动写指标

**DoD**:
- `data/eval/eval_v1.jsonl` 有 100 行,格式符合 schema
- `docs/metrics.md` 第一节已写,包含 Recall@3/5/10、MRR 至少 4 个指标
- baseline Recall@3 通常在 55-70% 之间(如果远低于 50% 说明出问题了,停下来 debug)

---

## Phase 1 结束动作

完成 T1.1 ~ T1.9 全部后:
1. 在 `docs/progress.md` 把 Phase 1 状态改为 ✅,填完成日期
2. 在 `docs/decisions/` 写一份 ADR:`ADR-001-phase1-baseline.md`,记录:
   - 用了什么 Embedding / chunk size / 索引参数
   - baseline 指标多少
   - 发现的主要问题(为 Phase 2 铺垫)
3. 向用户汇报,等用户确认才进 Phase 2
