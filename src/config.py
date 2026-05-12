"""项目全局配置。所有可变配置走环境变量(.env 加载),禁止硬编码。"""

from __future__ import annotations

import os
from dataclasses import dataclass

from dotenv import load_dotenv

load_dotenv()


def _env(key: str, default: str = "") -> str:
    return os.getenv(key, default)


def _env_bool(key: str, default: bool = False) -> bool:
    v = os.getenv(key, "").strip().lower()
    if not v:
        return default
    return v in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class Settings:
    # ---- LLM (DeepSeek, OpenAI 兼容) ----
    deepseek_api_key: str = _env("DEEPSEEK_API_KEY")
    deepseek_base_url: str = _env("DEEPSEEK_BASE_URL", "https://api.deepseek.com/v1")
    deepseek_model: str = _env("DEEPSEEK_MODEL", "deepseek-chat")

    # ---- Embedding / Reranker ----
    embedding_model: str = _env("EMBEDDING_MODEL", "BAAI/bge-m3")
    reranker_model: str = _env("RERANKER_MODEL", "BAAI/bge-reranker-v2-m3")
    embedding_device: str = _env("EMBEDDING_DEVICE", "auto")  # auto / cuda / cpu
    embedding_use_fp16: bool = _env_bool("EMBEDDING_USE_FP16", True)

    # ---- Milvus ----
    milvus_host: str = _env("MILVUS_HOST", "127.0.0.1")
    milvus_port: str = _env("MILVUS_PORT", "19530")
    milvus_collection: str = _env("MILVUS_COLLECTION", "chunks_v1")

    # ---- Elasticsearch ----
    es_host: str = _env("ES_HOST", "http://127.0.0.1:9200")
    es_index: str = _env("ES_INDEX", "chunks_v1")

    # ---- Neo4j ----
    neo4j_uri: str = _env("NEO4J_URI", "bolt://127.0.0.1:7687")
    neo4j_user: str = _env("NEO4J_USER", "neo4j")
    neo4j_password: str = _env("NEO4J_PASSWORD", "changeme-please")

    # ---- Redis ----
    redis_url: str = _env("REDIS_URL", "redis://127.0.0.1:6379/0")

    # ---- 日志 ----
    log_level: str = _env("LOG_LEVEL", "INFO")


settings = Settings()
