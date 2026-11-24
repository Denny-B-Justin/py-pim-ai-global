# PIM AI Global — Dash app for Posit Connect

Python 3.12.12 · Dash · Azure Databricks (Unity Catalog + AI Search) · Posit mAI Gateway

## Pages (`/?page=<name>`)

| Page | Purpose |
|---|---|
| `home` | Landing page |
| `query` | RAG search: collection (incl. **All PIM Documents**) + model selector, history, Word export |
| `registry` | Documents per collection and country (`&collection=<id>&country=<name>`) |
| `statistics` | Chunk/document statistics from `pim_ai_global_metadata` |
| `analytics`, `admin` | Admin only (sign-in required) |
| `release-notes`, `about` | Static pages |

Unknown `page` values show the not-found page.

## Structure

```
app.py              entrypoint (app:app), routing, Word-export route
constants.py        tables, indexes, models, limits, security settings
pages/              one module per page + pages_constants.py (page copy)
utils/              design.py, security.py, data.py, databricks_client.py, llm.py, rag.py, state.py, export.py, auth_ui.py
assets/             style.css, app.js, fonts, icons, images
manifest.json  requirements.txt  .env.sample
```

## Run locally

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.sample .env        # fill in values; set APP_ENV=development
python app.py              # http://127.0.0.1:8050/?page=home
```

Production-like local run: `gunicorn app:server -b 127.0.0.1:8050` (Connect itself uses `app:app`). Runtime state (rate limits, admin sessions, query results) is kept in a SQLite file in the temp directory, shared by workers on one host.

The mAI gateway only accepts calls from apps running on Posit Connect, so LLM answers work after deployment only. Registry/Statistics/Query retrieval work locally with Databricks credentials.

## Environment variables

| Variable | Required | Use |
|---|---|---|
| `APP_ENV` | yes | `production` (default) or `development` |
| `SECRET_KEY` | prod | ≥32 chars; signs sessions/CSRF. `python -c "import secrets;print(secrets.token_hex(32))"` |
| `ADMIN_USERNAME`, `ADMIN_PASSWORD_HASH` | for admin pages | Hash from `python -m utils.security`. Unset = admin pages disabled |
| `IP_HASH_SALT` | recommended | Salt for hashed client IPs in logs |
| `DATABRICKS_HOST` | yes | Workspace host (https enforced) |
| `DATABRICKS_HTTP_PATH` | yes | SQL warehouse HTTP path |
| `DATABRICKS_CLIENT_ID`, `DATABRICKS_CLIENT_SECRET` | yes | Service principal (OAuth M2M) |
| `MAI_BASE_URL` | yes | mAI gateway URL (trailing `/`) |
| `MAI_ENDPOINT_OPENAI`, `MAI_ENDPOINT_CLAUDE`, `MAI_ENDPOINT_GEMINI` | per provider | `mai-endpoint` value per provider |
| `MAI_MODEL` | no | Default model id |
| `ALLOWED_ORIGINS` | no | Comma-separated CORS allow-list; empty = CORS off |
| `TRUSTED_PROXY_HOPS` | no | Proxies in front of the app (default 1) |

Set these in Connect under **Settings → Runtime → Environment Variables**. `CONNECT_CONTENT_GUID` is set by Connect. Do not attach any Integration.

## Unity Catalog objects (`prd_mega.sgpbpi163`)

| Object | Name | Created by |
|---|---|---|
| Metadata table | `pim_ai_global_metadata` | chunking notebook |
| Registry table | `pim_ai_global_registry` | chunking notebook |
| Query log table | `pim_ai_global_query_logs` | **you (DDL below)** |
| AI Search endpoint | `pim-ai-global` | existing |
| Indexes | `pim_ai_global_all_documents_index`, `..._good_practices_chunks_index`, `..._pima_chunks_index`, `..._pfr_chunks_index`, `..._pefa_chunks_index` | existing |

```sql
CREATE TABLE IF NOT EXISTS prd_mega.sgpbpi163.pim_ai_global_query_logs (
  id            BIGINT GENERATED ALWAYS AS IDENTITY,
  created_at    TIMESTAMP,
  query_text    STRING,
  collection    STRING,
  model         STRING,
  provider      STRING,
  ip_hash       STRING,
  retrieval_ms  INT,
  llm_ms        INT,
  total_ms      INT,
  input_tokens  INT,
  output_tokens INT,
  chunk_count   INT,
  error         STRING
);
```

Grants for the service principal (verify index/endpoint permissions in your workspace):

```sql
GRANT USE CATALOG ON CATALOG prd_mega TO `<client-id>`;
GRANT USE SCHEMA  ON SCHEMA  prd_mega.sgpbpi163 TO `<client-id>`;
GRANT SELECT ON TABLE prd_mega.sgpbpi163.pim_ai_global_metadata TO `<client-id>`;
GRANT SELECT ON TABLE prd_mega.sgpbpi163.pim_ai_global_registry TO `<client-id>`;
GRANT SELECT, MODIFY ON TABLE prd_mega.sgpbpi163.pim_ai_global_query_logs TO `<client-id>`;
-- SELECT on the five indexes; CAN USE on the SQL warehouse.
```

## Migrating the data from Supabase

Source database: **Supabase = PostgreSQL + pgvector (SQL).** No NoSQL store is used. Only JSONB columns (`tags`, `metadata`, `sources`) are semi-structured: flatten them to typed columns (as done in the chunk tables: `country`, `year`, `section_heading`, …) or keep as `STRING`/`MAP` when needed.

| Supabase | Unity Catalog | How |
|---|---|---|
| `documents` | `pim_ai_global_registry` | Rebuilt by the notebook from the files — no export needed |
| `chunks` (+ embeddings) | `pim_ai_global_<slug>_chunks` + Delta Sync indexes | Rebuilt by the notebook; embeddings are computed by the index, so the 3072-dim vectors are **not** migrated |
| collection statistics RPCs | `pim_ai_global_metadata` | Rebuilt by the notebook |
| `query_logs` | `pim_ai_global_query_logs` | Optional: export CSV → upload to a Volume → `COPY INTO` (columns above; drop `embedding_ms`, `cache_hit`) |
| `embedding_cache`, `response_cache` | — | Dropped |
| `registry_refresh_log`, `collection_tag_classes` | — | Dropped (scrapers/tag filters removed) |

After new files arrive: run the notebook → run the `all_documents` cell → press **Sync now** on the five indexes.

## Deploy to Posit Connect

```bash
pip install rsconnect-python
rsconnect add --server https://<connect-host> --api-key <key> --name connect
rsconnect deploy dash --name connect --entrypoint app:app .
```

Then set the environment variables, restart the content, and open `…/content/<guid>/?page=home`. Regenerate the manifest after code changes: `rsconnect write-manifest dash --entrypoint app:app --overwrite -x .env -x .env.sample -x .gitignore .` and set `python.version` to `3.12.12` if needed.

## Security summary

- Admin sign-in: scrypt password hash, constant-time compare, username allow-list regex, lockout (5 failures / 15 min per IP and username), server-side sessions (8 h max, 30 min idle), HttpOnly + SameSite=Lax + Secure cookies.
- `analytics` and `admin` are checked on page render and in every callback.
- CSRF: signed token bound to the session on every callback request; JSON-only callbacks; request size cap; per-IP rate limits.
- SQL: only named parameters for values; table names come from validated constants; TLS-only Databricks and gateway URLs.
- XSS: Markdown without raw HTML, React-escaped text, `nh3` sanitising for Word export, CSP with script hashes, self-hosted fonts.
- Results are bound to the browser session (a job id from another session returns 404).
- Debug off, generic error responses, dotfiles/source/config paths blocked, CORS off unless `ALLOWED_ORIGINS` is set, no keys in code (`api_key="not-used"` for the gateway SDKs).

## Differences from the Next.js app

Removed: "latest reports only" filter, tag filters, scraper/ingest/cron admin tools (now the Databricks notebook), embedding/response caches, token-streamed answers (answers arrive when complete), similarity-% display. Added: **All PIM Documents** scope, five-model selector (Claude Haiku 5.5, GPT-6 Luna, GPT-5.6 Luna, Gemini 3.8 Flash, Gemini 3.7 Flash), PEFA collection, status console.
