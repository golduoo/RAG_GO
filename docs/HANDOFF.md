# 会话交接文档（SESSION HANDOFF）

> 新对话接手前先读这份，再按 claude.md §0 启动协议走。
> 记录"代码和 ADR 里没写、但接手必须知道"的环境与状态。
> 最后更新：2026-05-28（Phase 2 完成，等确认进 Phase 3）

## 1. 当前状态
- Phase 1 已完成（T1.1~T1.9），见 ADR-004
- **Phase 2 已完成（T2.0~T2.4，全量 105 测试绿）**：ik 插件(ADR-005) + 多粒度 chunks_v2 + BM25 + RRF Hybrid + doc 级评估(ADR-006)
- chunks_v2：Milvus=ES=31900（para 10126 / sent 21761 / title 13），ES ik_smart；chunks_v1 保留作 baseline
- **Phase 2 结论(ADR-007)**：doc 级抗泄漏集上 Hybrid R@3=0.84 < Dense 0.94，加权RRF/分型都救不回，根因=eval刻意去词面重叠+BGE-M3近上限；合成集上 Hybrid 最佳。**A+ 决策**：Hybrid 作 Phase 3 候选生成层，Dense-only 留作 baseline/fallback
- 评估口径已切 doc 级（ADR-006）：`run_eval.py --match-level doc`(默认) + `--retriever {dense,bm25,hybrid}`；诊断脚本 `scripts/analyze_phase2.py`
- 下一步 Phase 3：三路线对比 ①Dense+rerank ②Hybrid+rerank ③Dense-only，见 phase-3.md
- GitHub: https://github.com/golduoo/RAG_GO (main)
- baseline: Recall@3=0.931（合成 eval）/ 0.874（抗泄漏 paraphrased eval）

## 2. ⚠️ 环境坑（务必照做）
### 2.1 uv 不在默认 PATH
每次命令前：$env:Path = "C:\Users\95459\.local\bin;$env:Path"
### 2.2 PowerShell 中文乱码
跑打印中文的脚本前：$env:PYTHONIOENCODING="utf-8"
### 2.3 HuggingFace 下载：hf_hub 1.x 与镜像不兼容 ⭐
snapshot_download / transformers 自动下载会失败。改用我们的直链脚本：
  scripts/download_data.py（数据集）
  scripts/download_model.py BAAI/xxx --outdir models/xxx（模型）
默认走 HF_ENDPOINT=https://hf-mirror.com（脚本内置）
### 2.4 模型权重不在 git 里
models/ 已 gitignore。当前机器有 models/bge-m3。
Phase 2 要 reranker，先下：
  uv run python scripts/download_model.py BAAI/bge-reranker-v2-m3 --outdir models/bge-reranker-v2-m3
然后改 .env 的 RERANKER_MODEL=models/bge-reranker-v2-m3
### 2.5 .env 有真实 DeepSeek key，勿 commit（已 gitignore）
注意 .env 里 EMBEDDING_MODEL=models/bge-m3（本地路径）
### 2.6 Python 3.12 + torch CUDA(cu128)，GPU=RTX 4060 8GB
### 2.7 ES ik 插件装在容器层，非数据卷 ⭐
T2.0 已装 analysis-ik 8.15.3。若 `docker compose down`（删容器）重建 ES，需重装：
  docker exec sf-rag-kb-es bin/elasticsearch-plugin install -b https://get.infini.cloud/elasticsearch/analysis-ik/8.15.3
  docker compose restart elasticsearch
`docker compose stop/start` 不删容器，插件保留，无需重装。
### 2.8 Neo4j 端口 7474 在本机绑定失败 ⚠️
`docker compose up -d` 起 neo4j 报 “bind 7474: 访问被禁止”（Windows 保留端口段）。
neo4j 是 Phase 4 GraphRAG 才用，Phase 2 不需要，暂忽略。
Phase 2 只起：docker compose up -d milvus elasticsearch redis
要修可改 docker-compose.yml 把 7474 换成 17474（待 Phase 4 处理）。

## 3. 每次开工恢复环境
$env:Path = "C:\Users\95459\.local\bin;$env:Path"
$env:PYTHONIOENCODING="utf-8"
cd <项目目录>
docker compose start            # 容器上次 stop 了，数据卷还在；若报不存在用 up -d
uv run python scripts/check_infra.py   # 确认 Milvus/ES/Neo4j/Redis OK

## 4. Phase 2 注意（文档与现实的出入）
1. ADR 编号：phase-2.md 说写 ADR-002，但 002 已被占用。Phase 2 的 ADR 从 ADR-005 起。
   已有：001 Python3.12 / 002 通用RAG定位 / 003 ES分词fallback / 004 Phase1总结
2. ik 分词：ADR-003 已承诺 Phase 2 装 ik 插件+重建 ES 索引，这应是 Phase 2 第一步
3. "Recall@3 +8pp" 的 DoD 偏乐观（ADR-004 §4.2）：baseline 抗泄漏 eval 已 87%，
   建议用 eval_v1_paraphrased.jsonl 做主对比，+1~3pp 即算成功
4. Phase 2 建新 collection chunks_v2，别覆盖 chunks_v1

## 5. 已有资产
- 语料 data/processed/logistics_corpus.jsonl（8000，gitignored）
- 评估集 data/eval/eval_v1.jsonl（合成）+ eval_v1_paraphrased.jsonl（抗泄漏，主用）
- 模型 models/bge-m3（gitignored）
- Milvus chunks_v1 / ES chunks_v1：各 10786（Docker volume）
- 学习笔记 docs/learning/

## 6. 测试现状
62 个全绿。跑全部：uv run pytest -q