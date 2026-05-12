# Rules: Code Style

> **何时读**:写 Python 或 Go 代码前。

---

## Python

### 工具链
- 格式化:`ruff format`
- Lint:`ruff check --fix`,提交前必须无 warning
- 包管理:`uv`(不要用 pip / poetry / conda)
- 类型检查:函数签名必须类型注解

### 风格
- 行宽:100
- 缩进:4 空格
- 字符串:双引号优先
- import 顺序:标准库 → 第三方 → 本项目,组间空一行
- 禁止 `from X import *`
- 禁止裸 `except:`,必须指定异常
- 禁止 `print`(测试和 CLI 脚本除外),用 `loguru` logger

### Docstring
模块开头必须有:
```python
"""模块用途简述。"""
```

公开函数/类用 Google 风格,关键函数必写:
```python
def reciprocal_rank_fusion(
    rankings: Sequence[list[RetrievedDoc]],
    k: int = 60,
    top_k: int = 10,
) -> list[RetrievedDoc]:
    """RRF 融合多路检索结果。

    Args:
        rankings: 多路检索结果列表,每路按相关性降序。
        k: RRF 平滑常数,通常 60。
        top_k: 返回前 K 个结果。

    Returns:
        按 RRF score 降序的 top_k 个 RetrievedDoc。

    Raises:
        ValueError: 当 rankings 为空时。
    """
```

### 命名
- 模块/包:`snake_case`
- 类:`PascalCase`
- 函数/变量:`snake_case`
- 常量:`UPPER_SNAKE`
- 私有:前缀 `_`
- 禁止中文标识符(注释、字符串里可以用中文)

### 错误处理
- 自定义异常放各模块的 `exceptions.py`
- 日志记录异常用 `logger.exception()`(自动带 traceback)
- 不要捕获后只 `pass`,要么处理要么 re-raise

### 配置和密钥
- 所有可变配置走 `src/config.py`
- 配置从环境变量读,用 `python-dotenv` 加载 `.env`
- **禁止**在代码里硬编码 API key、URL、端口

参考实现:
```python
# src/config.py
import os
from dataclasses import dataclass
from dotenv import load_dotenv

load_dotenv()

@dataclass(frozen=True)
class Settings:
    llm_api_key: str = os.getenv("LLM_API_KEY", "")
    llm_base_url: str = os.getenv("LLM_BASE_URL", "https://api.deepseek.com")
    llm_model: str = os.getenv("LLM_MODEL", "deepseek-chat")
    milvus_uri: str = os.getenv("MILVUS_URI", "http://localhost:19530")
    es_url: str = os.getenv("ES_URL", "http://localhost:9200")
    embedding_model: str = os.getenv("EMBEDDING_MODEL", "BAAI/bge-m3")
    rerank_model: str = os.getenv("RERANK_MODEL", "BAAI/bge-reranker-v2-m3")

settings = Settings()
```

### 日志
```python
# src/logger.py
import sys
from loguru import logger

logger.remove()
logger.add(sys.stderr, level="INFO", format="<g>{time:HH:mm:ss}</g> | <level>{level: <8}</level> | <c>{name}</c>:<c>{function}</c>:{line} - {message}")
logger.add("logs/app.log", rotation="10 MB", retention="7 days", level="DEBUG")

# 各模块用:
# from src.logger import logger
```

### 异步
- I/O 密集型(LLM 调用、数据库读写)优先用 `async`
- 一个调用链要么全 sync 要么全 async,不混用
- 测试用 `pytest-asyncio`,标记 `@pytest.mark.asyncio`

---

## Go(Phase 5 才用)

### 工具链
- 格式化:`gofmt -s`
- Lint:`golangci-lint run`
- 项目布局参考 [golang-standards/project-layout](https://github.com/golang-standards/project-layout)

### 风格
- 错误处理:不忽略任何 err,处理或返回
- 日志:`log/slog`
- 包名:全小写、单数、简洁
- 文件名:`snake_case.go`

### 项目结构
```
gateway/
├── go.mod
├── cmd/
│   └── server/
│       └── main.go            # 入口,只做依赖注入
├── internal/
│   ├── handler/               # HTTP handler
│   ├── middleware/            # 鉴权、限流
│   └── proxy/                 # 转发到 FastAPI
└── pkg/                       # 可被外部引用的(本项目暂不需要)
```

### 错误处理范式
```go
func DoSomething(ctx context.Context, req Request) (*Response, error) {
    if err := req.Validate(); err != nil {
        return nil, fmt.Errorf("validate request: %w", err)
    }
    resp, err := callBackend(ctx, req)
    if err != nil {
        return nil, fmt.Errorf("call backend: %w", err)
    }
    return resp, nil
}
```

### 并发
- 不要在 handler 里启动 goroutine 而不管理它的生命周期
- 用 `context.Context` 控制超时和取消
- channel 关闭由发送方负责

---

## 提交规范

- commit message 用 Conventional Commits:`feat:`, `fix:`, `chore:`, `docs:`, `refactor:`, `test:`
- 一次 commit 一个逻辑改动,不要把 10 个 Task 揉一起
- 改动 `🔒` 锁定章节前必须在 commit message 里写 `[BREAKING]`
