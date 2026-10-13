"""Reproducible synthetic retrieval benchmark (does not touch application data).

Run: python -m scripts.benchmark_search --records 5000 --queries 100
Reports retrieval only, not full investigation analysis or WAN latency.
"""
import argparse
import json
import statistics
import tempfile
from pathlib import Path
from time import perf_counter

from app.domain.enums import KnowledgeCollection
from app.engines.knowledge.sqlite_store import SqliteKnowledgeStore


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--records", type=int, default=5000)
    parser.add_argument("--queries", type=int, default=100)
    args = parser.parse_args()
    if args.records < 1 or args.queries < 1:
        parser.error("records and queries must be positive")
    with tempfile.TemporaryDirectory() as directory:
        store = SqliteKnowledgeStore(Path(directory) / "benchmark.db")
        for i in range(args.records):
            topic = ("Kafka consumer timeout", "SQL deadlock", "Meter collector connection", "IIS worker crash")[i % 4]
            store.upsert(KnowledgeCollection.DOCUMENTATION, str(i),
                f"{topic}. Investigation {i}. Check connection configuration and service logs.", topic, {})
        samples = []
        for _ in range(args.queries):
            started = perf_counter()
            assert store.query(KnowledgeCollection.DOCUMENTATION, "Kafka consumer timeout", 5)
            samples.append((perf_counter() - started) * 1000)
    print(json.dumps({"records": args.records, "queries": args.queries,
        "median_ms": round(statistics.median(samples), 2),
        "p95_ms": round(sorted(samples)[int((len(samples) - 1) * 0.95)], 2)}, indent=2))


if __name__ == "__main__":
    main()
