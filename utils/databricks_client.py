"""Databricks access: SQL warehouse (named parameters) and AI Search (REST via SDK). TLS only."""
import logging
import threading
import time
from functools import lru_cache

from databricks import sql
from databricks.sdk import WorkspaceClient
from databricks.sdk.core import Config, oauth_service_principal

from constants import (
    DATABRICKS_CLIENT_ID,
    DATABRICKS_CLIENT_SECRET,
    DATABRICKS_HOST,
    DATABRICKS_HTTP_PATH,
    DB_TIMEOUT_S,
)
from utils.security import require_https

log = logging.getLogger("pim.databricks")
_lock = threading.Lock()
_conn = None


class DataError(Exception):
    """Raised for any Databricks failure; message is safe to show to users."""


def _host_url() -> str:
    host = DATABRICKS_HOST
    if not host or not DATABRICKS_CLIENT_ID or not DATABRICKS_CLIENT_SECRET:
        missing = [
            n
            for n, v in (
                ("DATABRICKS_HOST", host),
                ("DATABRICKS_CLIENT_ID", DATABRICKS_CLIENT_ID),
                ("DATABRICKS_CLIENT_SECRET", DATABRICKS_CLIENT_SECRET),
            )
            if not v
        ]
        log.error("databricks not configured; missing env vars: %s", ", ".join(missing))
        raise DataError("Databricks is not configured. Set the DATABRICKS_* environment variables.")
    return require_https(host if "://" in host else f"https://{host}", "DATABRICKS_HOST").rstrip("/")


def _connect():
    url = _host_url()
    if not DATABRICKS_HTTP_PATH:
        log.error("databricks not configured; missing env var: DATABRICKS_HTTP_PATH")
        raise DataError("DATABRICKS_HTTP_PATH is not set.")
    log.info("connecting to sql warehouse host=%s http_path=%s", url, DATABRICKS_HTTP_PATH)
    cfg = lambda: oauth_service_principal(  # noqa: E731
        Config(host=url, client_id=DATABRICKS_CLIENT_ID, client_secret=DATABRICKS_CLIENT_SECRET)
    )
    t0 = time.perf_counter()
    conn = sql.connect(
        server_hostname=url.split("://", 1)[1],
        http_path=DATABRICKS_HTTP_PATH,
        credentials_provider=cfg,
        _socket_timeout=DB_TIMEOUT_S * 10,
    )
    log.info("sql warehouse connected in %.0f ms", (time.perf_counter() - t0) * 1000)
    return conn


def _summary(statement: str) -> str:
    """Single-line, truncated statement for logs (values are bound parameters, never inlined)."""
    return " ".join(statement.split())[:200]


def _err(exc: BaseException) -> str:
    """Exception type plus message, flattened to one line for logs."""
    return f"{type(exc).__name__}: {' '.join(str(exc).split())[:1000]}"


def query(statement: str, params: dict | None = None, max_rows: int | None = None) -> list[dict]:
    """Run one statement with named parameters (:name) and return rows as dicts."""
    global _conn
    for attempt in (1, 2):
        t0 = time.perf_counter()
        try:
            with _lock:
                if _conn is None:
                    _conn = _connect()
                with _conn.cursor() as cur:
                    cur.execute(statement, params or {})
                    if cur.description is None:
                        return []
                    cols = [d[0] for d in cur.description]
                    rows = cur.fetchmany(max_rows) if max_rows else cur.fetchall()
            log.debug("sql ok rows=%d ms=%.0f stmt=%s", len(rows), (time.perf_counter() - t0) * 1000, _summary(statement))
            return [dict(zip(cols, r)) for r in rows]
        except DataError:
            raise
        except Exception as exc:
            with _lock:
                try:
                    if _conn is not None:
                        _conn.close()
                except Exception:
                    pass
                _conn = None
            log.warning(
                "sql attempt %s failed after %.0f ms: %s | stmt=%s",
                attempt,
                (time.perf_counter() - t0) * 1000,
                _err(exc),
                _summary(statement),
            )
            if attempt == 2:
                log.error("sql failed after retries: %s", _summary(statement), exc_info=exc)
                raise DataError("The data service is temporarily unavailable. Please try again.") from exc
    return []


@lru_cache(maxsize=1)
def workspace() -> WorkspaceClient:
    # databricks-sdk 0.163: the HTTP timeout is a Config attribute, not a WorkspaceClient argument.
    return WorkspaceClient(
        config=Config(
            host=_host_url(),
            client_id=DATABRICKS_CLIENT_ID,
            client_secret=DATABRICKS_CLIENT_SECRET,
            http_timeout_seconds=DB_TIMEOUT_S,
        )
    )


def ai_search(index: str, query_text: str, columns: tuple[str, ...], num_results: int) -> list[dict]:
    """Text query against an AI Search index; returns hits (best first) with a trailing `score`."""
    try:
        resp = workspace().vector_search_indexes.query_index(
            index_name=index, columns=list(columns), query_text=query_text, num_results=num_results
        )
    except DataError:
        raise
    except Exception as exc:
        log.warning("ai_search failed index=%s: %s", index, _err(exc))
        raise DataError("Search is temporarily unavailable. Please try again.") from exc
    names = [c.name for c in (resp.manifest.columns if resp.manifest and resp.manifest.columns else [])] or list(columns)
    hits = []
    for row in (resp.result.data_array if resp.result and resp.result.data_array else []):
        hit = dict(zip(names, row))
        if len(row) > len(names):
            hit["score"] = row[-1]
        hits.append(hit)
    return hits


def index_status(index: str) -> dict:
    try:
        idx = workspace().vector_search_indexes.get_index(index_name=index)
        st = idx.status
        return {
            "name": index,
            "ready": bool(getattr(st, "ready", False)),
            "rows": getattr(st, "indexed_row_count", None),
            "message": getattr(st, "message", "") or "",
            "type": getattr(idx.index_type, "value", str(idx.index_type or "")),
        }
    except Exception as exc:
        log.warning("index_status failed index=%s: %s", index, _err(exc))
        return {"name": index, "ready": False, "rows": None, "message": "Unavailable", "type": ""}


def endpoint_status(name: str) -> dict:
    try:
        ep = workspace().vector_search_endpoints.get_endpoint(endpoint_name=name)
        state = getattr(getattr(ep.endpoint_status, "state", None), "value", "")
        return {"name": name, "state": state, "type": getattr(ep.endpoint_type, "value", ""), "indexes": ep.num_indexes}
    except Exception as exc:
        log.warning("endpoint_status failed endpoint=%s: %s", name, _err(exc))
        return {"name": name, "state": "Unavailable", "type": "", "indexes": None}
