from concurrent.futures import ThreadPoolExecutor

from app.domain.enums import KnowledgeCollection as C
from app.engines.knowledge.sqlite_store import SqliteKnowledgeStore


def test_search_is_persistent_scoped_and_safe(tmp_path):
    path = tmp_path / "knowledge.db"
    store = SqliteKnowledgeStore(path)
    store.upsert(C.DOCUMENTATION, "doc", "Kafka consumer timeout", "Kafka", {"source": "wiki"})
    store.upsert(C.KNOWN_BUGS, "bug", "Kafka consumer timeout", "Bug", {})
    reopened = SqliteKnowledgeStore(path)
    results = reopened.query(C.DOCUMENTATION, 'Kafka OR " consumer timeout')
    assert [m.record_id for m in results] == ["doc"]
    assert results[0].score == 1
    assert results[0].metadata["source"] == "wiki"
    assert results[0].metadata["search_backend"] == "sqlite_fts"
    assert reopened.query(C.DOCUMENTATION, "unrelated") == []
    assert reopened.query(C.DOCUMENTATION, "the and") == []
    assert reopened.query(C.DOCUMENTATION, "Kafka", 0) == []


def test_edits_and_archives_update_search_immediately(tmp_path):
    store = SqliteKnowledgeStore(tmp_path / "knowledge.db")
    store.upsert(C.DOCUMENTATION, "doc", "Kafka", "Kafka", {})
    store.upsert(C.DOCUMENTATION, "doc", "SQL deadlock", "SQL", {})
    assert store.count(C.DOCUMENTATION) == 1
    assert store.query(C.DOCUMENTATION, "Kafka") == []
    assert store.query(C.DOCUMENTATION, "deadlock")[0].record_id == "doc"
    store.delete(C.DOCUMENTATION, "doc")
    assert store.query(C.DOCUMENTATION, "deadlock") == []


def test_concurrent_writers_and_recent_limit(tmp_path):
    store = SqliteKnowledgeStore(tmp_path / "knowledge.db")
    def insert(i):
        store.upsert(C.DOCUMENTATION, str(i), "Kafka", "Kafka", {"imported_at": f"2026-10-{i:02}"})
    with ThreadPoolExecutor(max_workers=4) as pool:
        list(pool.map(insert, range(1, 13)))
    assert store.count(C.DOCUMENTATION) == 12
    assert [m.record_id for m in store.list_recent(C.DOCUMENTATION, 2)] == ["12", "11"]
    assert len(store.query(C.DOCUMENTATION, "Kafka", 3)) == 3


def test_default_wiring_does_not_load_vector_dependencies(tmp_path, monkeypatch):
    import sys
    from app.api import dependencies
    from app.config import Settings
    monkeypatch.setattr(dependencies, "get_settings", lambda: Settings(sqlite_path=tmp_path / "app.db"))
    dependencies._knowledge_store.cache_clear()
    try:
        assert isinstance(dependencies._knowledge_store(), SqliteKnowledgeStore)
        assert "chromadb" not in sys.modules
        assert "sentence_transformers" not in sys.modules
    finally:
        dependencies._knowledge_store.cache_clear()
