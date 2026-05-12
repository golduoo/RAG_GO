"""基础设施健康检查:连接 Milvus / ES / Neo4j / Redis 并打印版本。

用法:
    uv run python scripts/check_infra.py

退出码:
    0 全部 OK,非 0 至少一个失败。
"""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from typing import Callable

from dotenv import load_dotenv

load_dotenv()


@dataclass
class CheckResult:
    name: str
    ok: bool
    version: str = ""
    error: str = ""


def check_milvus() -> CheckResult:
    host = os.getenv("MILVUS_HOST", "127.0.0.1")
    port = os.getenv("MILVUS_PORT", "19530")
    try:
        from pymilvus import MilvusClient, utility, connections

        connections.connect(alias="default", host=host, port=port)
        version = utility.get_server_version()
        connections.disconnect("default")
        # 顺手用一次 client 接口,确保完整 API 可用
        _ = MilvusClient(uri=f"http://{host}:{port}")
        return CheckResult("Milvus", True, version)
    except Exception as exc:  # noqa: BLE001  CLI 工具:容错聚合
        return CheckResult("Milvus", False, error=f"{type(exc).__name__}: {exc}")


def check_elasticsearch() -> CheckResult:
    host = os.getenv("ES_HOST", "http://127.0.0.1:9200")
    try:
        from elasticsearch import Elasticsearch

        es = Elasticsearch(host, request_timeout=10)
        info = es.info()
        version = info["version"]["number"]
        es.close()
        return CheckResult("Elasticsearch", True, version)
    except Exception as exc:  # noqa: BLE001
        return CheckResult("Elasticsearch", False, error=f"{type(exc).__name__}: {exc}")


def check_neo4j() -> CheckResult:
    uri = os.getenv("NEO4J_URI", "bolt://127.0.0.1:7687")
    user = os.getenv("NEO4J_USER", "neo4j")
    pwd = os.getenv("NEO4J_PASSWORD", "changeme-please")
    try:
        from neo4j import GraphDatabase

        driver = GraphDatabase.driver(uri, auth=(user, pwd))
        with driver.session() as sess:
            rec = sess.run(
                "CALL dbms.components() YIELD name, versions, edition "
                "RETURN name, versions[0] AS version, edition"
            ).single()
            version = f"{rec['version']} ({rec['edition']})" if rec else "?"
        driver.close()
        return CheckResult("Neo4j", True, version)
    except Exception as exc:  # noqa: BLE001
        return CheckResult("Neo4j", False, error=f"{type(exc).__name__}: {exc}")


def check_redis() -> CheckResult:
    url = os.getenv("REDIS_URL", "redis://127.0.0.1:6379/0")
    try:
        import redis

        r = redis.Redis.from_url(url, socket_connect_timeout=5)
        info = r.info("server")
        version = info.get("redis_version", "?")
        r.close()
        return CheckResult("Redis", True, version)
    except Exception as exc:  # noqa: BLE001
        return CheckResult("Redis", False, error=f"{type(exc).__name__}: {exc}")


CHECKS: list[Callable[[], CheckResult]] = [
    check_milvus,
    check_elasticsearch,
    check_neo4j,
    check_redis,
]


def main() -> int:
    print("=" * 60)
    print("sf-rag-kb 基础设施健康检查")
    print("=" * 60)

    results: list[CheckResult] = []
    for fn in CHECKS:
        res = fn()
        results.append(res)
        if res.ok:
            print(f"[ OK ] {res.name:<14} version={res.version}")
        else:
            print(f"[FAIL] {res.name:<14} {res.error}")

    print("=" * 60)
    failed = [r for r in results if not r.ok]
    if failed:
        print(f"FAILED: {len(failed)}/{len(results)} 服务不可用")
        return 1
    print(f"ALL OK: {len(results)}/{len(results)} 服务健康")
    return 0


if __name__ == "__main__":
    sys.exit(main())
