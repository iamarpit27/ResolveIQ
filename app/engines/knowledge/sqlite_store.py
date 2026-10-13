"""Fast lexical retrieval in the application's SQLite database; no model or vectors.

FTS5 supplies indexed candidate retrieval and BM25 ranking. Scores are query
term coverage, not semantic similarity or a probability of a correct diagnosis.
Every operation opens its own connection, safe for concurrent API requests.
"""

from __future__ import annotations

import json
import re
import sqlite3
from contextlib import contextmanager
from pathlib import Path

from app.domain.enums import KnowledgeCollection
from app.domain.recommendation import KnowledgeMatch

_STOPWORDS = set("a an and are as at be been by for from has have in is it of on or that the this to was were with tags root cause resolution none".split())


def _terms(text: str) -> list[str]:
    return list(dict.fromkeys(t for t in re.findall(r"\w+", text.casefold()) if t not in _STOPWORDS and len(t) > 1))


class SqliteKnowledgeStore:
    def __init__(self, path: Path) -> None:
        self._path = Path(path)
        self._path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as conn:
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("""CREATE VIRTUAL TABLE IF NOT EXISTS knowledge_fts USING fts5(
                collection UNINDEXED, record_id UNINDEXED, title, body,
                metadata UNINDEXED, imported_at UNINDEXED,
                tokenize='unicode61', prefix='2 3'
            )""")

    @contextmanager
    def _connect(self):
        conn = sqlite3.connect(self._path, timeout=10)
        conn.row_factory = sqlite3.Row
        try:
            with conn:
                yield conn
        finally:
            conn.close()

    def upsert(self, collection: KnowledgeCollection, record_id: str, text: str, title: str, metadata: dict) -> None:
        with self._connect() as conn:
            conn.execute("DELETE FROM knowledge_fts WHERE collection=? AND record_id=?", (collection.value, record_id))
            conn.execute("INSERT INTO knowledge_fts VALUES (?, ?, ?, ?, ?, ?)",
                         (collection.value, record_id, title, text, json.dumps(metadata), metadata.get("imported_at", "")))

    def query(self, collection: KnowledgeCollection, text: str, top_k: int = 5) -> list[KnowledgeMatch]:
        terms = _terms(text)[:64]
        if not terms or top_k <= 0:
            return []
        # Tokens contain only word characters; quote each to avoid interpreting
        # user input as FTS operators. OR allows incomplete evidence to match.
        expression = " OR ".join(f'"{term}"' for term in terms)
        with self._connect() as conn:
            rows = conn.execute("""SELECT *, bm25(knowledge_fts, 0, 0, 3, 1, 0, 0) AS rank
                FROM knowledge_fts WHERE knowledge_fts MATCH ? AND collection=?
                ORDER BY rank, record_id LIMIT ?""", (expression, collection.value, top_k)).fetchall()
        matches = []
        for row in rows:
            present = set(_terms(row["title"] + " " + row["body"]))
            coverage = len(set(terms) & present) / len(terms)
            match = self._match(row, coverage)
            match.metadata["search_backend"] = "sqlite_fts"
            match.reason = f"Matches {len(set(terms) & present)} of {len(terms)} search terms."
            matches.append(match)
        return matches

    @staticmethod
    def _match(row, score: float) -> KnowledgeMatch:
        return KnowledgeMatch(collection=row["collection"], record_id=row["record_id"],
                              title=row["title"], snippet=row["body"][:400], score=score,
                              metadata=json.loads(row["metadata"]))

    def count(self, collection: KnowledgeCollection) -> int:
        with self._connect() as conn:
            return conn.execute("SELECT count(*) FROM knowledge_fts WHERE collection=?", (collection.value,)).fetchone()[0]

    def delete(self, collection: KnowledgeCollection, record_id: str) -> None:
        with self._connect() as conn:
            conn.execute("DELETE FROM knowledge_fts WHERE collection=? AND record_id=?", (collection.value, record_id))

    def list_recent(self, collection: KnowledgeCollection, limit: int = 5) -> list[KnowledgeMatch]:
        if limit <= 0:
            return []
        with self._connect() as conn:
            rows = conn.execute("""SELECT * FROM knowledge_fts WHERE collection=?
                ORDER BY imported_at DESC, record_id LIMIT ?""", (collection.value, limit)).fetchall()
        return [self._match(row, 1.0) for row in rows]
