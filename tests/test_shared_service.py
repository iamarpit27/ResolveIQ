from fastapi.testclient import TestClient


def test_fresh_service_seeds_search_and_analyzes_without_vectors(tmp_path, monkeypatch):
    from app.api import dependencies, main
    from app.config import Settings
    settings = Settings(sqlite_path=tmp_path / "app.db", chroma_persist_dir=tmp_path / "chroma",
                        external_knowledge_enabled=False)
    monkeypatch.setattr(dependencies, "get_settings", lambda: settings)
    monkeypatch.setattr(main, "get_settings", lambda: settings)
    dependencies.reset_singletons()
    try:
        with TestClient(main.app) as client:
            assert client.get("/health").status_code == 200
            assert client.get("/settings").json()["knowledge_backend"] == "sqlite_fts"
            search = client.get("/knowledge/search", params={"q": "Kafka"})
            assert search.status_code == 200 and search.json()
            investigation = client.post("/investigations", json={
                "title": "Kafka consumer timeout", "description": "Kafka consumer timeout and connection errors"})
            assert investigation.status_code == 201
            result = client.get(f"/investigations/{investigation.json()['id']}/recommendations")
            assert result.status_code == 200
            assert result.json()["next_best_step"]
            assert not settings.chroma_persist_dir.exists()
    finally:
        if dependencies._external_knowledge_service.cache_info().currsize:
            dependencies._external_knowledge_service().close()
        dependencies.reset_singletons()
