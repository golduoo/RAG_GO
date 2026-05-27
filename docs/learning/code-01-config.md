# 代码精读 01:`src/config.py`

> 配置中心:把 `.env` 文件里的值读进来,做成一个全局只读对象 `settings`。

---

## 全文结构

```
load_dotenv()           # 1. 把 .env 加载到环境变量
def _env(...)           # 2. os.getenv 的薄封装(默认空串)
def _env_bool(...)      # 3. 字符串 -> bool 的稳健转换
@dataclass(frozen=True) # 4. Settings 类:所有配置字段
class Settings: ...
settings = Settings()   # 5. 全局单例
```

---

## 逐块讲解

### `from __future__ import annotations`
开启后,类型注解被当字符串处理,不在运行时求值。好处:兼容旧 Python、避免 forward reference 报错、减少 import 顺序坑。3.12 可省,但保留是好习惯。

### `load_dotenv()` ⭐ 最关键的一行
读 `.env` 文件,把 `KEY=VALUE` 注入到环境变量。等价于在 shell 里 `export KEY=VALUE`。
- **必须在 `Settings` 类定义之前调用**(因为字段默认值在类定义时就执行 `_env()`)
- 删掉这行 → `.env` 全失效,`os.getenv` 返回 `None`

### `_env(key, default="")`
`os.getenv` 的封装,默认返回空串而非 `None`,保证 `Settings` 字段类型统一为 `str`。

### `_env_bool(key, default=False)`
环境变量**永远是字符串**。`.env` 写 `USE_FP16=true`,读出来是字符串 `"true"` 不是 `True`。
用白名单 `v in {"1","true","yes","on"}` 稳健转换。直接 `if "false":` 会判真(非空字符串恒真),是经典坑。

### `@dataclass(frozen=True)`
- `@dataclass`:自动生成 `__init__` / `__repr__` / `__eq__`,省 boilerplate
- `frozen=True`:实例不可变,改字段抛 `FrozenInstanceError`
- 为什么:配置全局只读 = 安全;不可变 = 线程安全 + 可 hash

### 字段默认值执行时机 ⚠️
```python
deepseek_api_key: str = _env("DEEPSEEK_API_KEY")
```
`_env(...)` 在**类定义时执行一次**。含义:
- `.env` 必须在 `import src.config` 之前准备好
- 运行时改 `.env`,**必须重启进程**才生效

### `settings = Settings()`
模块级单例。别的模块 `from src.config import settings` 即用。

---

## 关键认知

1. **链路**:`.env` 文件 → `load_dotenv()` → 环境变量 → `_env()` → `Settings` 字段
2. **顺序**:`load_dotenv()` 必须在类定义前
3. **不可变**:`frozen=True` 防止任何模块误改配置
4. **环境变量永远是字符串**:bool / int 都要手动转

---

## 自测题

1. 删掉 `load_dotenv()` 会怎样?
2. 运行中 `os.environ["X"]="new"`,`settings.x` 会变吗?为什么?
3. `.env` 写 `EMBEDDING_DEVICE=`(空),`settings.embedding_device` 得到啥?
4. `_env_bool("X", True)`,`.env` 写 `X=no`,返回什么?为什么不是 default?

---

## 可改进 / 生产实践

- 用 **Pydantic Settings**(`pydantic-settings` 包)能做类型校验 + 必填校验 + 嵌套配置,比 dataclass 更强。我们用 dataclass 是为了轻量。
- 敏感字段(api_key)可以加 `repr=False`,避免 `print(settings)` 时泄露到日志。
