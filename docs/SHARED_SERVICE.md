# One service for the whole team

Run the API and UI on a company-managed server accessible over VPN. Everyone
uses the same browser URL and the same knowledge and investigation data.
SQLite and its FTS index stay on that server's local persistent disk; never
put the live database on a shared network drive or sync it through OneDrive.

## Start with Docker

From the repository root, run `docker compose up --build -d`.
The UI is available on the server at `http://127.0.0.1:8501`; the API is private
to the container network. Configure your company HTTPS reverse proxy with
SSO/access restrictions and WebSocket support to forward to this UI port.
Give teammates that proxy URL. The compose file deliberately does not expose
the unauthenticated API or UI directly to the Internet.

The application still has no per-user authorization or trustworthy actor
identity. Proxy access restricts admission, but all admitted users currently
have the same administrative powers. Use a trusted pilot group until roles
are implemented. Docker startup has not been validated on your server.

The named volume `resolveiq-data` persists knowledge, investigations, uploads,
and the FTS index across container replacement. Do not run `down -v` unless
intentionally deleting that data. Use one API instance for this SQLite pilot.
For larger deployments or several replicas, migrate the relational database
and retrieval adapter to PostgreSQL full-text search.

## Start on Windows without Docker

Use Python 3.11 or later, create a virtual environment, and install
`pip install -r requirements.txt`. Run `uvicorn app.api.main:app` and
`streamlit run ui/Home.py --server.address=127.0.0.1` on the server. Place the
same authenticated HTTPS proxy in front of the UI. The default UI API address
is `http://localhost:8000`. If UI and API are on different hosts, set
`RESOLVEIQ_API_URL` in the UI process environment to the API's private URL;
this setting is read from the environment, not the API's `.env` file.

## Existing data and migration

Back up the existing server data first. Keep `data/resolveiq.db` and
`data/uploads`; the governed SQLite tables are the source of truth.
Set `RESOLVEIQ_KNOWLEDGE_BACKEND=sqlite_fts` and leave
`RESOLVEIQ_AUTO_SEED_KNOWLEDGE=true` for the initial startup. Empty FTS
collections are populated from those tables, including published documents.
No Chroma-to-FTS conversion or embedding download is required. Retain the old
Chroma directory for rollback; it is not read in FTS mode.

To move into Docker, stop the old application and copy its SQLite database
and uploads into the named volume before starting the API. Do not copy a live
WAL database with ordinary file copying: stop all writers and use SQLite's
backup API, or a managed consistent volume snapshot. Keep regular tested backups.

For a first import or explicit reindex, run
`python -m scripts.seed_knowledge --force`. This upserts governed records;
it is not a cleanup of stale index entries left by manual database edits.
Use the application lifecycle actions for edits and archives.

## Speed controls and tradeoffs

Local validation: 472 suite tests passed, plus the new fresh-service integration
test and a final targeted regression run. A 5,000-record synthetic benchmark
with 100 searches measured 13.54 ms median retrieval and 25.54 ms p95 on the
development machine. This is not a before/after comparison, a production
load test, or a full-response guarantee. Reproduce with
`python -m scripts.benchmark_search --records 5000 --queries 100`.

* `RESOLVEIQ_KNOWLEDGE_BACKEND=sqlite_fts`: indexed keyword retrieval, default.
* `RESOLVEIQ_EXTERNAL_KNOWLEDGE_RESPONSE_BUDGET_SECONDS=3`: maximum wait shared
  by both live connectors. Late results populate the in-memory cache; retry
  Analyze to see them. HTTP calls can continue up to their own request timeout.
* `RESOLVEIQ_EXTERNAL_KNOWLEDGE_TIMEOUT_SECONDS=20`: per HTTP request timeout.
* `RESOLVEIQ_EXTERNAL_KNOWLEDGE_ENABLED=false`: skip live connectors entirely
  for consistently local retrieval. This is the compose default.
* `RESOLVEIQ_EXTERNAL_KNOWLEDGE_CACHE_TTL_SECONDS=900`: repeated external
  searches reuse ranked results for 15 minutes. Cache keys include context.

FTS uses up to the first 64 unique non-stopword query terms, exact word
matching, and BM25 candidate ordering. It can miss synonyms and paraphrases.
Validate representative support tickets before relying on recommendation
scores. Parsing large archives and OCR can still take time; this change does
not make those jobs asynchronous or add upload size limits.

To restore semantic search, install `requirements-semantic.txt` in addition
to the base requirements and set `RESOLVEIQ_KNOWLEDGE_BACKEND=chroma`.
Use Python 3.11 for that older optional dependency stack. The vector database
still belongs only to the shared server, never to each teammate's machine.
