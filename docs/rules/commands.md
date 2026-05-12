# Rules: Commands

> **何时读**:用 uv / docker / pytest / 评估等命令时,或者忘了怎么操作时。

---

## 环境管理(uv)

```bash
uv sync                            # 按 pyproject.toml 同步依赖
uv sync --dev                      # 含 dev 依赖
uv add <pkg>                       # 加新依赖
uv add --dev <pkg>                 # 加 dev 依赖
uv remove <pkg>                    # 删依赖
uv run python -m src.X             # 在虚拟环境里跑
uv run pytest -q
source .venv/bin/activate          # 激活虚拟环境(也可以不激活,全用 uv run)
```

加新依赖的规则:
1. 必须先检查 `docs/rules/project.md` §2 是否允许
2. 用具体版本约束(`==X.Y.*` 或 `>=X.Y`),不要用 `>=0.0.1` 这种空泛的
3. `uv add` 后立即试 `uv sync` 确认无冲突

---

## 基础设施(Docker Compose)

```bash
docker compose up -d                       # 起所有服务
docker compose up -d milvus elasticsearch  # 起指定服务
docker compose down                        # 停并删容器
docker compose down -v                     # 停并删数据卷(谨慎)
docker compose ps                          # 查状态
docker compose logs -f milvus              # 跟踪日志
docker compose restart milvus              # 重启单个

# 检查服务健康
python scripts/check_infra.py
```

### 各服务的默认端口(开发环境)
| 服务 | 端口 | 用途 |
|------|------|------|
| Milvus | 19530 | gRPC |
| Milvus | 9091 | metrics |
| Etcd | 2379 | Milvus 依赖 |
| MinIO | 9000 | Milvus 依赖 |
| Elasticsearch | 9200 | HTTP API |
| Neo4j | 7474 | Browser UI |
| Neo4j | 7687 | Bolt 协议 |
| Redis | 6379 | |
| FastAPI | 8000 | 主后端 |
| Go Gateway | 8080 | 网关 |
| Streamlit | 8501 | Demo UI |

---

## 测试

```bash
uv run pytest -q                                   # 全部
uv run pytest tests/retrieval/ -v                  # 单目录
uv run pytest -k "rrf"                             # 按关键词
uv run pytest --lf                                 # 只跑上次失败
uv run pytest -m integration                       # 跑集成测试
uv run pytest --cov=src --cov-report=html          # 带覆盖率(需要 pytest-cov)
```

---

## 代码质量

```bash
uv run ruff format src/ tests/ scripts/             # 格式化
uv run ruff check src/ --fix                        # lint + 自动修
uv run ruff check src/                              # 只 lint
```

提交前的检查清单:
```bash
uv run ruff format . && uv run ruff check . --fix && uv run pytest -q
```

---

## 数据流水线

```bash
# Phase 1
bash scripts/download_data.sh                       # 下 DuReader 等
python scripts/filter_logistics.py                  # 关键词筛选,输出 logistics_corpus.jsonl
python scripts/ingest.py --collection chunks_v1     # 切分 + 入 Milvus + 入 ES

# 评估
python scripts/build_eval_set.py \
  --source data/processed/logistics_corpus.jsonl \
  --output data/eval/eval_v1.jsonl \
  --n 100

python scripts/run_eval.py \
  --phase 1 \
  --eval data/eval/eval_v1.jsonl \
  --collection chunks_v1
```

---

## 运行服务

```bash
# 开发模式跑后端
uv run uvicorn src.api.main:app --reload --port 8000

# 跑 Streamlit demo
uv run streamlit run app.py --server.port 8501

# 跑 Go 网关(Phase 5)
cd gateway && go run cmd/server/main.go
```

---

## Git

```bash
# 一个 Task 完成时
git add -A
git commit -m "feat(retrieval): implement RRF fusion (T2.3)"

# 改动 🔒 锁定章节
git commit -m "[BREAKING] refactor: change Chunk schema, add granularity field"

# 看本周改了多少
git log --since="1 week ago" --oneline
```

### Conventional Commits 类型
- `feat`: 新功能
- `fix`: bug 修复
- `chore`: 杂项(依赖更新等)
- `docs`: 文档
- `refactor`: 重构(不改功能)
- `test`: 测试
- `perf`: 性能优化
- `style`: 格式调整

---

## 故障排查

```bash
# 进容器看日志
docker exec -it sf-rag-kb-milvus-1 bash
cat /var/log/milvus.log

# 看 Python 进程
ps aux | grep python
lsof -i:8000             # 看 8000 端口被谁占用
kill -9 <pid>

# 看磁盘
df -h
du -sh data/             # 看数据目录大小
du -sh ~/.cache/         # HuggingFace 缓存可能很大

# 清缓存(谨慎)
docker system prune -af  # 删未使用的镜像和容器
```

### 常见报错

| 报错 | 原因 | 解决 |
|------|------|------|
| `MilvusException: connect failed` | Milvus 未起或还在启动 | `docker compose ps`,等 healthy |
| `Connection refused (ES)` | ES 未起或端口冲突 | `lsof -i:9200`,检查容器 |
| `OutOfMemoryError` (BGE) | 显存/内存不够 | 改 `use_fp16=True`,或退到 bge-base |
| `RateLimitError` (LLM) | API 调用太快 | 降并发,加 retry 间隔 |
| `Token limit exceeded` | prompt 太长 | 减 top_k,或先压缩 context |
