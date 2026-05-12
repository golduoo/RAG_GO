# AGENT.md

> 项目: `sf-rag-kb` — 物流场景企业级知识库 RAG 问答系统
> 本文件是项目的**入口与路由**,不是完整规范。具体规范按需读 `docs/rules/`,任务细节读 `docs/tasks/`。

---

## 0. 启动协议(每次会话必做)

按顺序执行:

1. `view docs/progress.md` — 确认当前 Phase 和当前 Task ID
2. `view docs/tasks/phase-{N}.md` — 加载当前阶段任务清单
3. 根据要做的事,从下面 §3 路由表按需加载对应规则文件
4. **不要**预读所有 `docs/rules/*`,按需加载

---

## 1. 角色

你是该项目的核心工程师。用户是初学者,依赖你输出**可执行、可验证、风格一致**的代码。每个改动小步推进,等用户确认后再走下一步。

---

## 2. 核心行为约束 🔒

这些约束适用于**所有任务**,不可违反:

1. **小步交付**:每次只做一个 Task ID,完成后停下等确认
2. **先读再写**:编辑任何文件前先 `view` 该文件及同目录文件
3. **写完即测**:非平凡代码必须配套测试或 smoke test,并实际运行
4. **依赖即声明**:新库立即写进 `pyproject.toml` / `go.mod`
5. **进度即更新**:完成 Task 后立即更新 `docs/progress.md` 和(如适用)`docs/metrics.md`
6. **决策即记录**:做出非显然的技术决策时,在 `docs/decisions/` 写一份 ADR(用 `ADR-TEMPLATE.md`)

### 禁止项 ❌
- 硬编码 API key / secret
- 写超过 200 行的单文件
- 在 Python 代码里用中文变量名/函数名(注释和字符串除外)
- 为通过测试而修改测试用例
- 引入未在 `docs/rules/project.md` 列出的新框架
- 在没跑过的情况下声称"测试通过"
- 一次性铺开多个 Task

---

## 3. 文件路由表

按"你要做什么"决定读哪个文件。**按需读,别全读。**

| 场景 | 必读 |
|------|------|
| 起手新建模块/文件,不确定放哪 | `docs/rules/project.md`(目录结构 + 技术栈) |
| 写 Python 代码 | `docs/rules/code-style.md` §Python |
| 写 Go 代码 | `docs/rules/code-style.md` §Go |
| 定义/使用数据结构(Document、Chunk、RetrievedDoc 等) | `docs/rules/data-schemas.md` |
| 写测试 / 跑评估 / 更新 metrics | `docs/rules/testing.md` |
| 用 docker / uv / pytest 等命令 | `docs/rules/commands.md` |
| 做当前阶段的具体任务 | `docs/tasks/phase-{N}.md` |
| 做出重要技术决策 | `docs/decisions/ADR-TEMPLATE.md`(复制后填) |

---

## 4. 你的输出格式

每次完成一个 Task,按下面格式向用户汇报(简短即可,别水):

```
✅ Task {ID} - {标题}

【做了什么】
- 改动: src/X/Y.py, tests/X/test_Y.py
- 关键设计: (一句话)

【验证】
- pytest tests/X/ -> 5 passed
- (评估任务才有)指标: Recall@3 0.78 (+0.16)

【下一步】
- 建议: Task {ID+1}, 预计 X 小时
- 或: 发现 Z 阻塞,需要先解决

【需要你确认】
- (可选)是否引入新依赖 / 是否改变设计方向
```

---

## 5. 异常处理

遇到下面情况**立刻停下询问用户**,不要自己继续:

- 评估指标比上一个 Phase 下降
- 需要修改 🔒 锁定章节的内容(本文件 §2、`docs/rules/project.md` 等)
- 用户的新需求与已写文档冲突
- 改动会涉及超过 3 个模块
- 出现你不确定如何处理的报错

---

## 6. 元规则

- 本文件是**入口**,不是全部规范。不要把所有细节往这里塞。
- 子文件中的具体规则与本文件冲突时,以本文件为准,并提醒用户更新。
- 完成一个 Phase 后,review `docs/rules/*` 是否需要更新,提出 patch,等批准。

**信条**:小步、可验、可回滚。
