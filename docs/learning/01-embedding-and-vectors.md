# 01. Embedding 与向量空间

> 关联代码:`src/ingest/indexer.py` 里的 `BGEEmbedder`
> 关联决策:Phase 1 全程

---

## 1. 直觉:文字怎么变成"距离"

**问题**:计算机怎么判断"顺丰多久到"和"顺丰特快几天能送到"是**同一件事**?

❌ **字符串比对**:两句话只共享 4 个字("顺丰"+"丰多到",更别说"几天"和"多久")。
❌ **关键词匹配**:同义词、句式变化全失效。

✅ **Embedding 思路**:把每句话变成**一组数字**,让"语义相近"的句子在数字空间里**距离近**。

```
"顺丰多久到"          → [0.12, -0.34, 0.87, ..., 0.05]   ← 1024 个数字
"顺丰特快几天能送到"   → [0.13, -0.33, 0.85, ..., 0.06]   ← 跟上面很像
"今天天气真好"         → [-0.42, 0.91, 0.03, ..., -0.77]  ← 跟上面差很远
```

这 1024 个数字就叫**向量**(vector),也叫 **embedding**(嵌入)。
"嵌入"的意思是:把语义信息"嵌入"到一个 1024 维的几何空间里。

**类比**:
- 一个城市的位置可以用 2 维(经纬度)表达,**距离**有物理意义
- 一句话的"语义"可以用 1024 维表达,**距离**就是"语义相似度"

---

## 2. 为什么是 1024 维?

BGE-M3 的设计者选了 1024,常见维度还有:

| 模型 | 维度 |
|---|---|
| OpenAI text-embedding-3-small | 1536 |
| OpenAI text-embedding-3-large | 3072 |
| bge-base-zh-v1.5 | 768 |
| **BGE-M3** | **1024** |
| sentence-bert | 768 |

**维度多少的权衡**:
- 维度越高 → 能表达的语义细节越丰富 → 但**存储 / 计算 / 内存**翻倍
- 维度越低 → 快但表达力弱

> 经验法则:768/1024 维是中文检索的甜点。我们的 10786 chunks × 1024 维 × 4 bytes = ~44 MB,够小。

---

## 3. 模型怎么学到的?(直觉,不深入)

模型本身就是个**神经网络**。训练目标用一句话讲:

> "**让训练数据里的相关文本对(query, passage)的向量距离 < 不相关对的距离**"

这叫 **contrastive learning**(对比学习)。BGE-M3 用了几亿条这样的 (query, positive, negative) 三元组训练出来的,所以拿来即用,**你不需要再训**。

```
训练时:
  query = "顺丰多久到"
  positive = "顺丰快递通常 1-2 个工作日"   ← 强迫这俩向量靠近
  negative = "今天股市大涨"                ← 强迫这俩向量拉远
```

---

## 4. 余弦相似度 vs 欧氏距离

把向量摆在 N 维空间里,有两种"近"的算法:

### 4.1 欧氏距离(Euclidean / L2)
直观:两个点的直线距离。
```
dist(A, B) = sqrt(Σ (A_i - B_i)²)
```
**坑**:向量长度(magnitude)会影响结果——但语义不应该取决于"句子长度感",只取决于"方向"。

### 4.2 余弦相似度(Cosine)
直观:两个向量的**夹角**,只看方向,不看长度。
```
cos(A, B) = (A · B) / (|A| × |B|)
```
取值 [-1, 1],越大越像。

**我们项目里 Milvus 配的是 COSINE**:
```python
# src/ingest/indexer.py
self.collection.create_index(
    field_name="vector",
    index_params={
        "index_type": "HNSW",
        "metric_type": "COSINE",   # ← 这里
        ...
    },
)
```

### 4.3 小窍门:Normalize 后,COSINE = 内积

如果你**先把所有向量除以自己的长度**(归一化到单位球面),那 `cos(A, B) = A · B`(点积),
计算更快。BGE-M3 输出的向量是**预归一化**的,直接用点积就行,但 Milvus 用 COSINE 参数处理对开发者是透明的。

---

## 5. fp16 / fp32 / 量化(精度与显存的权衡)

我们启动 BGE-M3 时:
```python
# src/ingest/indexer.py
BGEM3FlagModel(self.model_name, use_fp16=self.use_fp16, devices=self.device)
```

`use_fp16=True` 是什么意思?

### 5.1 浮点类型对照

| 类型 | 每个数字占多少 bit | 精度 | 显存 |
|---|---|---|---|
| **fp32**(float32) | 32 bit = 4 byte | 高 | 1× |
| **fp16**(float16) | 16 bit = 2 byte | 中 | 0.5× |
| **bf16**(bfloat16) | 16 bit = 2 byte | 中(动态范围更大) | 0.5× |
| **int8** | 8 bit = 1 byte | 低(需量化) | 0.25× |

### 5.2 BGE-M3 的内存账

模型本身参数量约 5.68 亿(568M):
- fp32 存储:568M × 4 byte = **2.27 GB**(你下的 `pytorch_model.bin` 就是这个大小)
- fp16 推理:加载时转成 fp16,显存占用 ~**1.2 GB**
- 加上一些激活和 batch 数据,实际 RTX 4060 8GB 占 ~1.5-2 GB,绰绰有余

### 5.3 fp16 的坑

- **数值不稳定**:fp16 范围小,某些极值场景(loss 计算、softmax)会下溢/上溢。**推理一般稳**,训练时容易爆。
- **CPU 上不一定快**:fp16 在 CPU 上反而可能慢,因为 CPU 没硬件加速。所以 `EMBEDDING_USE_FP16=True` 但 `device=cpu` 会被你的代码 fallback 为 fp32:
  ```python
  self.use_fp16 = use_fp16 and self.device != "cpu"
  ```

---

## 6. GPU 为什么快?(直觉)

Embedding 的核心计算是**矩阵乘法**。

- CPU(16 核)= 16 个会做复杂决策的工人,串行干活
- GPU(RTX 4060 = 3072 CUDA cores)= 3000+ 个只会做加减乘除的傻子,**同时**干活

矩阵乘法本质是一堆"互不依赖的乘加",傻子们一起干最适合 → GPU 完爆 CPU。

**我们实测**:
- RTX 4060 fp16 batch=64:**~52 chunks/s**
- 同样模型 CPU:大概 **2-5 chunks/s**(慢一个数量级)

---

## 7. 本项目里的 Embedding 链路(代码 walk)

打开 `src/ingest/indexer.py`,我标注关键行:

```python
class BGEEmbedder:
    def __init__(self, model_name=..., device=..., use_fp16=...):
        ...
        self.device = self._resolve_device(device)   # auto -> cuda/cpu
        self.use_fp16 = use_fp16 and self.device != "cpu"   # CPU 上禁 fp16
        self._model: Any = None                       # ← 延迟加载

    def _ensure_loaded(self) -> None:
        """首次调用 encode 时才真正加载权重。"""
        if self._model is not None:
            return
        from FlagEmbedding import BGEM3FlagModel
        self._model = BGEM3FlagModel(
            self.model_name,
            use_fp16=self.use_fp16,
            devices=self.device,
        )

    def encode(self, texts: list[str], batch_size: int = 32):
        self._ensure_loaded()
        out = self._model.encode(
            texts,
            batch_size=batch_size,
            return_dense=True,      # ← 我们只要 dense 1024 维向量
            return_sparse=False,    # ← BGE-M3 还能出稀疏 / colbert,本阶段不用
            return_colbert_vecs=False,
        )
        vecs = out["dense_vecs"]
        return [v.tolist() for v in vecs]   # numpy -> Python list (Milvus 接受 list)
```

**关键设计**:
1. **延迟加载**:`__init__` 不动模型,只有真要 encode 才加载。这样测试 mock / 配置错误时不会无意义吃 2GB 内存。
2. **依赖注入**:`device`、`use_fp16` 都从 settings 进来,**测试时可以轻松换 CPU**。
3. **BGE-M3 一模多用**:它能同时出 dense / sparse / colbert 三种向量,我们 Phase 1 只用 dense,Phase 2 可能引入 sparse 做混合。

---

## 8. 常见坑

| 坑 | 现象 | 解决 |
|---|---|---|
| 模型每次都重新下载 | 首次启动慢 / 网络断 | 设 `HF_HOME` 缓存目录,或本项目用 `models/bge-m3` 本地路径 |
| fp16 在 CPU 上变慢 | encode 比 fp32 还慢 | `use_fp16 and device != 'cpu'`(我们这么写的) |
| 显存爆 (OOM) | CUDA out of memory | 调小 `batch_size`,或换更小的模型(bge-base-zh) |
| query 长 > 8192 token | 模型截断,质量下降 | BGE-M3 max len 8192,够用;若文档更长,先 split |
| 向量没归一化就算点积 | 距离失真 | BGE-M3 输出已归一化,Milvus 用 COSINE 也透明处理 |

---

## 9. 自测题

不需要回答给我,自己心里答一下:

1. 如果换成 OpenAI 的 `text-embedding-3-large`(3072 维),Milvus collection 要改什么?
2. 你的 query 是英文,documents 全是中文,BGE-M3 还能用吗?为什么?
3. 假如你把 `use_fp16=False`,encode 速度会变慢多少?估算一下。
4. 为什么 Milvus 配 COSINE,但 BGE-M3 输出已经归一化了——这俩有没有冲突?
5. 如果有 1000 万个 chunk,1024 维 fp32 存储要多少 GB?换 fp16 呢?

---

## 10. 想再深入?推荐资料

- BGE 系列论文与文档:[BAAI/FlagEmbedding GitHub](https://github.com/FlagOpen/FlagEmbedding)
- 向量相似度直觉视频(中文):"3Blue1Brown - 线性代数本质"前 3 集
- 对比学习入门:SimCSE 原论文(简短易读)
- C-MTEB 中文 embedding 榜单(看模型选型怎么对比):https://huggingface.co/spaces/mteb/leaderboard

---

**这一站完成的标志**:你能给一个不懂的朋友讲清楚"为什么我们要先 embed 再检索,而不是直接关键词匹配"。
讲不顺的话回来再读一遍 §1 和 §4。
