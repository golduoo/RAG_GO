# 代码精读 02:`src/logger.py`

> 全局日志:配置一个 loguru logger,所有模块 `from src.logger import logger` 共用。

---

## 全文

```python
"""全局 logger 配置(loguru)。其他模块直接 ``from src.logger import logger``。"""
from __future__ import annotations
import sys
from loguru import logger
from src.config import settings

logger.remove()                  # 1. 移除 loguru 默认 handler
logger.add(                      # 2. 加一个我们自定义的 handler
    sys.stderr,                  #    输出到标准错误流
    level=settings.log_level,    #    级别从配置读(INFO)
    format=(                     #    自定义格式(带颜色)
        "<green>{time:YYYY-MM-DD HH:mm:ss}</green> "
        "| <level>{level: <8}</level> "
        "| <cyan>{name}:{function}:{line}</cyan> "
        "- <level>{message}</level>"
    ),
)
__all__ = ["logger"]             # 3. 控制 from src.logger import * 的导出
```

---

## 为什么用 loguru 而不是标准库 logging?

| | 标准库 logging | loguru |
|---|---|---|
| 配置 | 啰嗦(Handler/Formatter/Logger 三件套) | 一行 `logger.add()` |
| 颜色 | 要装插件 | 内置 |
| 用法 | `logging.getLogger(__name__)` 每个文件写 | `from loguru import logger` 直接用 |
| 异常追踪 | 手动 | `logger.exception()` 自动带 traceback |

loguru 的哲学:**一个全局 logger 走天下**,不用每个模块 `getLogger`。

---

## 逐块讲解

### `logger.remove()`
loguru 默认自带一个输出到 stderr 的 handler。我们要**自定义格式**,所以先把默认的删掉,避免日志打印两遍。

### `logger.add(sys.stderr, ...)`
加一个新 handler:
- **`sys.stderr`**:日志走标准错误流(不是 stdout)。为什么?约定:程序的"正常输出"(给用户/管道下游)走 stdout,"诊断信息"(日志)走 stderr,两者分开,便于 `program > output.txt` 时日志不污染结果。
- **`level=settings.log_level`**:从配置读。`.env` 里 `LOG_LEVEL=INFO`,则 DEBUG 级别的日志不显示。改成 `DEBUG` 能看到更多。
- **`format=...`**:loguru 的格式 DSL。
  - `{time:YYYY-MM-DD HH:mm:ss}` 时间戳
  - `{level: <8}` 级别名,左对齐占 8 字符(INFO/WARNING 对齐好看)
  - `{name}:{function}:{line}` 哪个模块、哪个函数、第几行打的(调试神器)
  - `{message}` 你写的内容
  - `<green>...</green>` `<cyan>...</cyan>` 是 loguru 的颜色标签

你跑脚本时见过的:
```
2026-05-13 01:41:06 | INFO     | __main__:main:104 - DONE: 10786 chunks ...
```
就是这个 format 渲染出来的。

### 日志级别(从低到高)
```
TRACE < DEBUG < INFO < SUCCESS < WARNING < ERROR < CRITICAL
```
设 `level=INFO` 意味着:INFO 及以上显示,DEBUG/TRACE 被过滤。
生产环境通常 INFO,排查问题临时调 DEBUG。

### `__all__ = ["logger"]`
控制 `from src.logger import *` 时导出什么。
这里声明只导出 `logger`,不导出 `sys`、`settings` 等被 import 进来的名字。
**良好习惯**:避免命名空间污染。

---

## 这个文件的"副作用"特性 ⚠️

注意:`logger.remove()` 和 `logger.add()` 是**模块级语句**,不是函数。
意味着 **`import src.logger` 的瞬间就执行了配置**。

这是 Python 里"import 即配置"的常见模式:
- 好处:任何模块只要 `from src.logger import logger`,配置已经生效
- 坏处:import 有副作用(一般不推荐,但 logger 这种全局单例是公认例外)

---

## 怎么用(其他模块)

```python
from src.logger import logger

logger.info("普通信息")
logger.warning("警告")
logger.error("出错了")
logger.debug("调试细节")            # level=INFO 时不显示
logger.exception("抓到异常")        # 在 except 块里用,自动带 traceback
```

你在 `indexer.py` / `dense.py` / `llm.py` 里都见过 `logger.info(...)`。

---

## 关键认知

1. **loguru = 极简日志**,一个全局 logger 走天下,不用 getLogger
2. **日志走 stderr**,跟程序正常输出(stdout)分流
3. **level 从配置读**,生产 INFO,排查临时 DEBUG
4. **import 即配置**:`from src.logger import logger` 时配置已生效

---

## 自测题

1. 为什么要先 `logger.remove()` 再 `logger.add()`?不 remove 会怎样?
2. 我想临时看 DEBUG 日志,改哪里?(提示:`.env`)
3. 日志为什么走 stderr 不走 stdout?举一个走 stdout 会出问题的场景。
4. `logger.exception()` 和 `logger.error()` 区别是什么?什么时候用前者?

---

## 可改进 / 生产实践

- 生产里通常再 `logger.add("app.log", rotation="100 MB", retention="7 days")` 加一个**文件 handler**,日志落盘 + 自动轮转
- 多进程 / 多机时,日志要带 trace_id 串起来(loguru 支持 `logger.bind(trace_id=...)`)
- 结构化日志(JSON 格式)便于 ELK/Grafana 收集:`logger.add(sink, serialize=True)`
