"""Deployment constants. Secrets are read from environment variables only."""
import os
import re
import tempfile
from dataclasses import dataclass

from dotenv import load_dotenv

load_dotenv(override=False)


def _env(name: str, default: str = "") -> str:
    return os.environ.get(name, default).strip()


def _int(name: str, default: int) -> int:
    try:
        return int(_env(name, str(default)))
    except ValueError:
        return default


# ── App ──────────────────────────────────────────────────────────────────
APP_NAME = "PIM AI Global"
APP_TITLE = "PIM AI Global — Public Investment Management Intelligence"
APP_DESCRIPTION = (
    "AI-powered retrieval and analysis of global public investment management "
    "guidance, IMF PIMA reports, and World Bank public finance reviews."
)
APP_ENV = _env("APP_ENV", "production").lower()
IS_PROD = APP_ENV == "production"
HOST = _env("HOST", "127.0.0.1")
PORT = _int("PORT", 8050)

# ── Databricks (Azure) · Unity Catalog ───────────────────────────────────
DATABRICKS_HOST = _env("DATABRICKS_HOST")
DATABRICKS_HTTP_PATH = _env("DATABRICKS_HTTP_PATH")
DATABRICKS_CLIENT_ID = _env("DATABRICKS_CLIENT_ID")
DATABRICKS_CLIENT_SECRET = _env("DATABRICKS_CLIENT_SECRET")

CATALOG = "prd_mega"
SCHEMA = "sgpbpi163"
_PREFIX = f"{CATALOG}.{SCHEMA}.pim_ai_global_"

TABLE_METADATA = f"{_PREFIX}metadata"
TABLE_REGISTRY = f"{_PREFIX}registry"
TABLE_QUERY_LOGS = f"{_PREFIX}query_logs"
MANAGED_TABLES = (TABLE_METADATA, TABLE_REGISTRY, TABLE_QUERY_LOGS)

AI_SEARCH_ENDPOINT = "pim-ai-global"
INDEX_ALL = f"{_PREFIX}all_documents_index"

_IDENT = re.compile(r"^[A-Za-z0-9_]+(\.[A-Za-z0-9_]+){2}$")
for _name in (*MANAGED_TABLES, INDEX_ALL):
    assert _IDENT.match(_name), f"invalid identifier: {_name}"


# ── Collections ──────────────────────────────────────────────────────────
@dataclass(frozen=True)
class Collection:
    id: str
    label: str
    value: str | None  # value of the `collection` column; None = no filter
    index: str
    description: str
    domain: str = "pim"  # "pefa" selects the PEFA-aware system prompt


COLLECTIONS: tuple[Collection, ...] = (
    Collection(
        "all",
        "All PIM Documents",
        None,
        INDEX_ALL,
        "Search across all four collections at once.",
    ),
    Collection(
        "pim_literature",
        "Global PIM Good Practices",
        "Global PIM Good Practices",
        f"{_PREFIX}good_practices_chunks_index",
        "World Bank, IMF, EC, EIB, and JICA guidance on Public Investment Management best practices.",
    ),
    Collection(
        "pima_reports",
        "IMF PIMA Reports",
        "IMF PIMA Reports",
        f"{_PREFIX}pima_chunks_index",
        "IMF Public Investment Management Assessment reports for various countries.",
    ),
    Collection(
        "wbg_pers",
        "World Bank Public Finance Reviews",
        "World Bank Public Finance Reviews",
        f"{_PREFIX}pfr_chunks_index",
        "World Bank Public Expenditure Reviews (PERs) and Public Finance Reviews (PFRs) spanning 2015–2026.",
    ),
    Collection(
        "pefa_reports",
        "PEFA National Reports",
        "PEFA National Reports",
        f"{_PREFIX}pefa_chunks_index",
        "Public Expenditure and Financial Accountability assessments — final, publicly available country-level reports from the PEFA Secretariat.",
        domain="pefa",
    ),
)
COLLECTION_BY_ID = {c.id: c for c in COLLECTIONS}
REGISTRY_COLLECTIONS = tuple(c for c in COLLECTIONS if c.value)
DEFAULT_COLLECTION_ID = "all"
for _c in COLLECTIONS:
    assert _IDENT.match(_c.index), f"invalid index: {_c.index}"

# Columns requested from AI Search (embedding_text is never returned).
SEARCH_COLUMNS = (
    "chunk_id",
    "collection",
    "country",
    "year",
    "file_name",
    "page",
    "page_end",
    "section_heading",
    "content",
)

# ── Posit mAI Gateway ────────────────────────────────────────────────────
MAI_BASE_URL = _env("MAI_BASE_URL")
MAI_ENDPOINTS = {
    "openai": _env("MAI_ENDPOINT_OPENAI"),
    "claude": _env("MAI_ENDPOINT_CLAUDE"),
    "gemini": _env("MAI_ENDPOINT_GEMINI"),
}
LLM_TIMEOUT_S = 150


@dataclass(frozen=True)
class Model:
    id: str  # allowed mAI model id
    label: str
    provider: str  # openai | claude | gemini
    description: str


MODELS: tuple[Model, ...] = (
    Model("claude-haiku-5-5", "Claude Haiku 5.5", "claude", "Anthropic's fast model — low latency, lower cost."),
    Model("gpt-6-luna", "GPT-6 Luna", "openai", "OpenAI's latest tier — strong all-around reasoning."),
    Model("gpt-5.6-luna", "GPT-5.6 Luna", "openai", "OpenAI's previous tier — fast and reliable."),
    Model("gemini-3.8-flash", "Gemini 3.8 Flash", "gemini", "Google's latest fast tier — long context, low latency."),
    Model("gemini-3.7-flash", "Gemini 3.7 Flash", "gemini", "Google's previous fast tier — low latency, lower cost."),
)
MODEL_BY_ID = {m.id: m for m in MODELS}
_PROVIDER_LABEL = {"claude": "Anthropic", "openai": "OpenAI", "gemini": "Google"}
PROVIDER_LABEL = _PROVIDER_LABEL
DEFAULT_MODEL_ID = _env("MAI_MODEL") if _env("MAI_MODEL") in MODEL_BY_ID else MODELS[0].id

# ── RAG limits ───────────────────────────────────────────────────────────
MAX_QUERY_LENGTH = 2000
RETRIEVE_K = 20
CONTEXT_CHAR_BUDGET = 32000
MAX_OUTPUT_TOKENS = 6000
MAX_INVENTORY_DOCS = 800
EXCERPT_CHARS = 200

# ── Data / cache ─────────────────────────────────────────────────────────
CACHE_TTL_SECONDS = 60
REGISTRY_MAX_ROWS = 500
ANALYTICS_RECENT_LIMIT = 50
DB_TIMEOUT_S = 60

# ── Security ─────────────────────────────────────────────────────────────
SECRET_KEY = _env("SECRET_KEY")
ADMIN_USERNAME = _env("ADMIN_USERNAME", "admin")
ADMIN_PASSWORD_HASH = _env("ADMIN_PASSWORD_HASH")
IP_HASH_SALT = _env("IP_HASH_SALT")
ALLOWED_ORIGINS = tuple(o.strip().rstrip("/") for o in _env("ALLOWED_ORIGINS").split(",") if o.strip())
TRUSTED_PROXY_HOPS = _int("TRUSTED_PROXY_HOPS", 1)

_SUFFIX = _env("CONNECT_CONTENT_GUID")[:8]
SESSION_COOKIE = "pim_session" + (f"_{_SUFFIX}" if _SUFFIX else "")
CSRF_COOKIE = "pim_csrf" + (f"_{_SUFFIX}" if _SUFFIX else "")
CSRF_HEADER = "X-PIM-CSRF"
ADMIN_SESSION_MAX_AGE_S = 8 * 3600
ADMIN_IDLE_TIMEOUT_S = 30 * 60
LOGIN_MAX_FAILURES = 5
LOGIN_LOCK_WINDOW_S = 15 * 60
RATE_LIMIT_QUERY = (20, 60)  # requests, seconds
RATE_LIMIT_PAGE = (240, 60)
MAX_BODY_BYTES = 256 * 1024
FRAME_ANCESTORS = "'self'"
STATE_DB_PATH = os.path.join(tempfile.gettempdir(), "pim_ai_global_state.sqlite3")
JOB_TTL_SECONDS = 3600

# ── Posit Connect ────────────────────────────────────────────────────────
PYTHON_VERSION = "3.12.12"
ENTRYPOINT = "app:app"
