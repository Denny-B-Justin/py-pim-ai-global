"""Read access to the UC dashboard tables plus the query-log writer. All values are bound parameters."""
import logging
import threading
import time
from datetime import datetime

from constants import (
    ANALYTICS_RECENT_LIMIT,
    CACHE_TTL_SECONDS,
    MAX_INVENTORY_DOCS,
    REGISTRY_COLLECTIONS,
    REGISTRY_MAX_ROWS,
    TABLE_METADATA,
    TABLE_QUERY_LOGS,
    TABLE_REGISTRY,
)
from utils import databricks_client as db

log = logging.getLogger("pim.data")
_cache: dict[str, tuple[float, object]] = {}
_cache_lock = threading.Lock()


def cached(key: str, loader, force: bool = False):
    now = time.time()
    with _cache_lock:
        hit = _cache.get(key)
        if hit and not force and now - hit[0] < CACHE_TTL_SECONDS:
            return hit[1]
    log.debug("cache miss key=%s force=%s", key, force)
    try:
        value = loader()
    except Exception as exc:
        log.error("load failed key=%s: %s: %s", key, type(exc).__name__, exc)
        raise
    with _cache_lock:
        _cache[key] = (now, value)
    return value


def cache_clear(*keys: str) -> None:
    with _cache_lock:
        for k in keys:
            _cache.pop(k, None)


# ── Dashboard tables ─────────────────────────────────────────────────────
def get_metadata(force: bool = False) -> list[dict]:
    """One row per collection, in the display order of REGISTRY_COLLECTIONS."""

    def load():
        rows = db.query(
            f"SELECT collection, total_chunks, `text`, images, documents, avg_chunk_length FROM {TABLE_METADATA}"
        )
        log.info("metadata loaded from %s: %d rows", TABLE_METADATA, len(rows))
        if not rows:
            log.warning("metadata table %s returned no rows", TABLE_METADATA)
        order = {c.value: i for i, c in enumerate(REGISTRY_COLLECTIONS)}
        return sorted(rows, key=lambda r: order.get(r["collection"], 99))

    return cached("metadata", load, force)


def document_counts() -> dict[str, int]:
    """collection value -> embedded document count; empty dict if unavailable."""
    try:
        return {r["collection"]: int(r["documents"] or 0) for r in get_metadata()}
    except Exception:
        log.warning("document_counts unavailable", exc_info=True)
        return {}


def get_registry(collection_value: str, force: bool = False) -> dict:
    def load():
        rows = db.query(
            f"SELECT country, year, document, status, chunks FROM {TABLE_REGISTRY} "
            "WHERE collection = :collection ORDER BY year DESC NULLS LAST, country ASC NULLS LAST, document ASC",
            {"collection": collection_value},
            REGISTRY_MAX_ROWS + 1,
        )
        log.info("registry loaded from %s collection=%s: %d rows", TABLE_REGISTRY, collection_value, len(rows))
        return {"rows": rows[:REGISTRY_MAX_ROWS], "truncated": len(rows) > REGISTRY_MAX_ROWS}

    return cached(f"registry:{collection_value}", load, force)


def get_inventory(collection_value: str | None) -> list[dict]:
    """Embedded documents of one collection (or all) for the prompt inventory."""
    if collection_value is None:
        return db.query(
            f"SELECT collection, country, year, document FROM {TABLE_REGISTRY} WHERE status = :status "
            "ORDER BY collection ASC, country ASC NULLS LAST, year DESC NULLS LAST, document ASC",
            {"status": "Embedded"},
            MAX_INVENTORY_DOCS,
        )
    return db.query(
        f"SELECT collection, country, year, document FROM {TABLE_REGISTRY} WHERE status = :status AND collection = :collection "
        "ORDER BY country ASC NULLS LAST, year DESC NULLS LAST, document ASC",
        {"status": "Embedded", "collection": collection_value},
        MAX_INVENTORY_DOCS,
    )


def data_as_of() -> datetime | None:
    """Latest write time of the dashboard tables (DESCRIBE HISTORY)."""

    def load():
        stamps = []
        for table in (TABLE_METADATA, TABLE_REGISTRY):
            rows = db.query(f"DESCRIBE HISTORY {table} LIMIT 1")
            if rows:
                stamps.append(rows[0]["timestamp"])
        return max(stamps) if stamps else None

    try:
        return cached("asof", load)
    except Exception:
        log.warning("data_as_of unavailable", exc_info=True)
        return None


# ── Query log ────────────────────────────────────────────────────────────
def log_query(entry: dict) -> None:
    """Best effort: a logging failure never breaks an answer."""
    try:
        db.query(
            f"INSERT INTO {TABLE_QUERY_LOGS} (created_at, query_text, collection, model, provider, ip_hash, "
            "retrieval_ms, llm_ms, total_ms, input_tokens, output_tokens, chunk_count, error) VALUES "
            "(current_timestamp(), :query_text, :collection, :model, :provider, :ip_hash, "
            ":retrieval_ms, :llm_ms, :total_ms, :input_tokens, :output_tokens, :chunk_count, :error)",
            {
                "query_text": str(entry.get("query_text", ""))[:2000],
                "collection": str(entry.get("collection", "")),
                "model": str(entry.get("model", "")),
                "provider": str(entry.get("provider", "")),
                "ip_hash": str(entry.get("ip_hash", "")),
                "retrieval_ms": int(entry.get("retrieval_ms", 0)),
                "llm_ms": int(entry.get("llm_ms", 0)),
                "total_ms": int(entry.get("total_ms", 0)),
                "input_tokens": int(entry.get("input_tokens", 0)),
                "output_tokens": int(entry.get("output_tokens", 0)),
                "chunk_count": int(entry.get("chunk_count", 0)),
                "error": str(entry.get("error", ""))[:500],
            },
        )
    except Exception as exc:
        log.warning("query log write failed: %s: %s", type(exc).__name__, exc)


def get_analytics(force: bool = False) -> dict:
    def load():
        t = TABLE_QUERY_LOGS
        window = "created_at >= current_timestamp() - INTERVAL 24 HOURS"
        summary = db.query(
            "SELECT COUNT(*) AS total_queries, ROUND(AVG(total_ms)) AS avg_total_ms, "
            "ROUND(AVG(retrieval_ms)) AS avg_retrieval_ms, ROUND(AVG(llm_ms)) AS avg_llm_ms, "
            "ROUND(AVG(chunk_count), 1) AS avg_chunks, "
            "SUM(CASE WHEN error <> '' THEN 1 ELSE 0 END) AS errors, "
            f"SUM(input_tokens) AS input_tokens, SUM(output_tokens) AS output_tokens FROM {t} WHERE {window}"
        )[0]
        by_collection = db.query(f"SELECT collection AS name, COUNT(*) AS n FROM {t} WHERE {window} GROUP BY collection ORDER BY n DESC")
        by_model = db.query(f"SELECT model AS name, COUNT(*) AS n FROM {t} WHERE {window} GROUP BY model ORDER BY n DESC")
        recent = db.query(
            "SELECT id, query_text, collection, model, retrieval_ms, llm_ms, total_ms, input_tokens, output_tokens, "
            f"chunk_count, error, created_at FROM {t} ORDER BY created_at DESC LIMIT {int(ANALYTICS_RECENT_LIMIT)}"
        )
        return {"summary": summary, "by_collection": by_collection, "by_model": by_model, "recent": recent}

    return cached("analytics", load, force)
