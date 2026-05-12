# Rules: Project Meta 🔒

> **何时读**:不确定模块放哪、要新增依赖、要新增顶层目录。
> 🔒 = 锁定章节,修改前必须征得用户同意。

---

## 1. 项目元信息 🔒

| 字段 | 值 |
|------|---|
| 项目名 | `sf-rag-kb` |
| 目标 | 物流场景企业级知识库 RAG 问答系统 |
| 主语言 | Python 3.10+ |
| 网关语言 | Go 1.21+(仅 Phase 5 用到) |
| 部署 | Docker Compose |
| 主数据集 | DuReader_retrieval(物流子集) |
| Benchmark | T2-Ranking + CRUD-RAG |
| 文档语言 | 中文(注释/字符串/markdown),代码标识符英文 |

---

## 2. 技术栈锁定 🔒

未经用户许可不得替换、新增、删除。如需变更,先在 `docs/decisions/` 写 ADR。

### Python 依赖(pyproject.toml)

```toml
[project]
name = "sf-rag-kb"
version = "0.1.0"
requires-python = ">=3.10"
dependencies = [
  # LLM 编排
  "langchain==0.3.*",
  "langchain-community==0.3.*",
  "langchain-openai==0.2.*",
  # Embedding & Rerank
  "FlagEmbedding>=1.3.0",
  "sentence-transformers>=3.0",
  # 存储
  "pymilvus==2.4.*",
  "elasticsearch==8.15.*",
  "neo4j>=5.20",
  # API
  "fastapi>=0.115",
  "uvicorn[standard]>=0.30",
  "pydantic>=2.8",
  # 工具
  "python-dotenv>=1.0",
  "tenacity>=9.0",
  "loguru>=0.7",
  "tqdm>=4.66",
  # 评估
  "ragas>=0.2.0",
  "datasets>=3.0",
  # 图相关
  "networkx>=3.3",
]

[dependency-groups]
dev = [
  "pytest>=8.3",
  "pytest-asyncio>=0.24",
  "ruff>=0.6",
  "ipykernel>=6.29",
]
```

### LLM 选型
- **默认 LLM**:DeepSeek API(`deepseek-chat`),OpenAI 兼容协议
- **Embedding**:`BAAI/bge-m3` 本地推理,fp16,必须支持 CPU fallback
- **Reranker**:`BAAI/bge-reranker-v2-m3` 本地推理

### 基础设施
- Milvus standalone 2.4.x(+ etcd + minio)
- Elasticsearch 8.15.x(单节点,禁用 security)
- Neo4j 5.x community
- Redis 7.x(可选,加缓存时用)

---

## 3. 目录结构 🔒

```
sf-rag-kb/
├── README.md                       # 项目说明(面向用户)
├── AGENT.md                        # AI 入口(本项目)
├── docker-compose.yml
├── pyproject.toml
├── .env.example                    # 入 git
├── .env                            # 不入 git
├── .gitignore
│
├── docs/
│   ├── progress.md                 # 当前进度
│   ├── metrics.md                  # 评估指标(追加)
│   ├── rules/                      # 规则,按需读
│   ├── tasks/                      # 各 Phase 任务清单
│   └── decisions/                  # ADR
│
├── data/
│   ├── raw/                        # 原始数据,gitignore
│   ├── processed/                  # 加工后中间产物
│   └── eval/                       # 评估集
│
├── src/
│   ├── __init__.py
│   ├── config.py                   # 配置,从 env 读
│   ├── logger.py                   # 全局 logger
│   │
│   ├── ingest/                     # 解析、切分、入库
│   │   ├── schema.py
│   │   ├── loaders.py
│   │   ├── splitters.py
│   │   └── indexer.py
│   │
│   ├── retrieval/                  # 检索
│   │   ├── base.py
│   │   ├── dense.py
│   │   ├── sparse.py
│   │   └── hybrid.py
│   │
│   ├── rerank/
│   │   └── cross_encoder.py
│   │
│   ├── query/
│   │   ├── intent.py
│   │   ├── rewrite.py
│   │   └── history.py
│   │
│   ├── generate/
│   │   ├── llm.py
│   │   ├── prompts.py
│   │   └── pipeline.py
│   │
│   ├── graph/                      # GraphRAG, Phase 4
│   │   ├── extractor.py
│   │   ├── store.py
│   │   └── retriever.py
│   │
│   ├── eval/
│   │   ├── ragas_runner.py
│   │   ├── crud_runner.py
│   │   └── metrics_logger.py
│   │
│   └── api/                        # FastAPI, Phase 5
│       ├── main.py
│       ├── routes/
│       └── schemas.py
│
├── gateway/                        # Go 网关, Phase 5
│   ├── go.mod
│   ├── cmd/server/main.go
│   └── internal/
│
├── scripts/                        # 一次性脚本
│   ├── download_data.sh
│   ├── filter_logistics.py
│   ├── ingest.py
│   ├── build_eval_set.py
│   └── run_eval.py
│
├── tests/                          # 单元测试,目录结构与 src/ 对齐
│   └── ...
│
└── notebooks/                      # 实验记录,允许中文,允许混乱
    └── ...
```

### 新增目录/模块的规则
- **顶层目录**:不得新增。如必须,写 ADR 并征求用户同意。
- **`src/` 下新模块**:允许新增,但必须遵循"一个职责一个子目录"。子目录里必须有 `__init__.py`。
- **`scripts/`**:一次性数据处理脚本放这里,**不要**在 `src/` 里写脚本风格代码。
- **`tests/`**:必须与 `src/` 目录结构对齐,即 `src/X/Y.py` 对应 `tests/X/test_Y.py`。
