# ADR-001: 把项目 Python 钉到 3.12

- **状态**:Accepted
- **日期**:2026-05-12
- **决策者**:AI 建议 + 用户确认

---

## 1. 背景(Context)

`docs/rules/project.md` §1 规定主语言为 "Python 3.10+",未指定具体小版本。
开发机默认 Python 是 3.14.3。在 T1.1 执行 `uv sync` 时,`pymilvus==2.4.*` 的传递依赖 `grpcio==1.67.1` 在 Python 3.14 上**没有预编译 wheel**,uv 回退到源码编译,触发 MSVC `cl.exe` 失败。

候选方案:
- A. 升级 grpcio → 但 `pymilvus==2.4.*` 锁定依赖范围,且 §2 锁定了 pymilvus 版本,改动牵连大
- B. 把项目 Python 钉到 3.12(主流 LTS,所有锁定依赖均有 wheel)
- C. 装 Visual Studio Build Tools 让 grpcio 从源码编译 → 慢、脆、对初学者不友好

---

## 2. 决策(Decision)

通过 `uv python pin 3.12` 把项目 Python 版本钉为 3.12,写入 `.python-version`,纳入 git。

---

## 3. 理由(Rationale)

- 3.12 是当前所有锁定依赖(torch、grpcio、tokenizers、pymilvus、elasticsearch 等)都提供 wheel 的版本,**零编译**
- 仍满足 §1 的 ">=3.10" 要求,不破坏锁定规则
- 不引入新构建工具链(VS Build Tools 约 6GB)
- uv 会自动下载隔离的 CPython 3.12,不影响系统 3.14

---

## 4. 代价 / 取舍(Consequences)

**好的**:
- `uv sync` 一次成功,新开发者上手零门槛
- 与 LangChain / FlagEmbedding 等主流生态最广兼容

**不好的**:
- 用不到 Python 3.13 / 3.14 的新特性(JIT、free-threaded)——项目不需要
- 若后续要升 3.13,需先验证所有依赖 wheel

---

## 5. 影响范围

- 涉及文件:`.python-version`、`pyproject.toml`(`requires-python` 仍为 `>=3.10`,不改)
- 涉及流程:所有 `uv run` 命令自动走 3.12
- 涉及指标:无直接影响

---

## 6. 验证

- `uv run python --version` → Python 3.12.x
- `uv run python -c "import src"` → OK
- `uv sync` 全过,无 grpcio 源码编译

---

## 7. 后续

- 若 Phase 4/5 引入的库要求 >=3.13,届时重新评估
- 若团队加入 GPU 训练成员,确认 torch 2.11 + 3.12 + CUDA 兼容性
