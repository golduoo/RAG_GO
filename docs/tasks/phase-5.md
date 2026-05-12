# Phase 5: 工程化 + Go 网关

> **目标**:把 pipeline 包装成可演示的服务,补齐 JD 要求的 Go/Docker
> **预计**:1 周 / 25h
> **前置**:Phase 4 完成

---

## Phase 总 DoD
- [ ] FastAPI 三个核心路由可用(`/chat` SSE / `/upload` / `/eval`)
- [ ] Streamlit Demo 可交互
- [ ] Go 网关(Gin)在 FastAPI 前面,实现鉴权 + 限流
- [ ] 全栈 `docker compose up` 一键起,从干净环境到 demo 可用 ≤ 5 分钟
- [ ] 增量更新接口:上传新文档后 30 秒内可被检索

---

## Tasks

### T5.1 FastAPI 后端
**步骤**:
1. `src/api/main.py` + `src/api/routes/`
2. 路由:
   - `POST /chat` — 接受 `{query, conversation_id?}`,SSE 流式返回
   - `POST /upload` — 接受文件,触发增量 ingest
   - `POST /eval` — 触发评估,异步返回 job_id
3. Pydantic schemas 放 `src/api/schemas.py`
4. CORS 配置允许 localhost

**DoD**:Swagger UI(`/docs`)能看到三个接口,能跑通

---

### T5.2 Streamlit Demo
**步骤**:
1. `app.py`:聊天界面
2. 显示答案 + 引用文档片段(可展开)
3. 显示检索结果的 score 和来源(dense/bm25/graph)
4. 历史对话保留在 session_state

**DoD**:`streamlit run app.py` 可用,演示效果良好

---

### T5.3 Go 网关 ⭐ JD 加分项
**步骤**:
1. `gateway/` 初始化 Go 模块
2. 用 Gin 实现:
   - 路径转发:`/api/*` → `http://api-backend:8000/*`
   - SSE 透传(注意 streaming 转发)
3. 中间件:
   - 简单 token 鉴权(`X-API-Key` header)
   - IP 限流(`golang.org/x/time/rate`,每秒 10 次)
   - 请求日志
4. 写 Dockerfile(multi-stage build)

**DoD**:
- `go run gateway/cmd/server/main.go` 起来
- `curl localhost:8080/api/chat ...` 能透传到 FastAPI
- 没 token 返回 401
- 超频返回 429

---

### T5.4 全栈 Docker Compose
**步骤**:
1. 把 `api-backend`(Python)和 `api-gateway`(Go)加进 compose
2. 各自 Dockerfile,用 `depends_on`
3. 健康检查链:gateway → backend → milvus/es

**DoD**:`docker compose down -v && docker compose up -d` 起来后,5 分钟内可访问 Streamlit demo,demo 端到端可用

---

### T5.5 增量更新接口
**步骤**:
1. `/upload` 接口接受文件
2. 异步任务:解析 → 切分 → embed → 同步写 Milvus + ES + Graph
3. 返回 task_id,可查状态
4. 新文档使用同一个 collection,直接 append

**DoD**:上传后 30 秒内能被 `/chat` 检索到

---

## Phase 5 结束动作
- 性能压测:
  - `locust` 或 `wrk` 压 `/chat`
  - 记录 P50 / P95 / P99 / QPS / 错误率
  - 写入 `docs/metrics.md`
- 勾选 `progress.md`
- 写 `ADR-005-engineering.md`,记录:
  - 为什么 Go 网关而不是 Python(单一职责、性能、JD 对齐)
  - 增量更新的一致性策略(目前是最终一致,理由)
