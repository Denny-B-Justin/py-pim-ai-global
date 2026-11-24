"""Security: headers/CSP, CSRF, CORS, rate limits, sanitising, password hashing, admin session."""
import base64
import getpass
import hashlib
import hmac
import logging
import re
import secrets
import time
import unicodedata
from urllib.parse import urlparse

from flask import Response, after_this_request, jsonify, request, session

from constants import (
    ADMIN_IDLE_TIMEOUT_S,
    ADMIN_PASSWORD_HASH,
    ADMIN_SESSION_MAX_AGE_S,
    ADMIN_USERNAME,
    ALLOWED_ORIGINS,
    CSRF_COOKIE,
    CSRF_HEADER,
    FRAME_ANCESTORS,
    IP_HASH_SALT,
    IS_PROD,
    LOGIN_LOCK_WINDOW_S,
    LOGIN_MAX_FAILURES,
    MAX_BODY_BYTES,
    RATE_LIMIT_PAGE,
    SECRET_KEY,
    SESSION_COOKIE,
    TRUSTED_PROXY_HOPS,
)
from utils import state

log = logging.getLogger("pim.security")

# ── Password hashing (scrypt) ────────────────────────────────────────────
_N, _R, _P, _LEN = 2**15, 8, 1, 32
MAX_PASSWORD_LEN = 256
_b64 = lambda b: base64.urlsafe_b64encode(b).rstrip(b"=").decode()  # noqa: E731
_unb64 = lambda s: base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))  # noqa: E731


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    dk = hashlib.scrypt(password.encode(), salt=salt, n=_N, r=_R, p=_P, dklen=_LEN, maxmem=128 * 1024 * 1024)
    return f"scrypt:{_N}:{_R}:{_P}:{_b64(salt)}:{_b64(dk)}"


def verify_password(password: str, stored: str) -> bool:
    try:
        _, n, r, p, salt, expected = stored.split(":")
        dk = hashlib.scrypt(
            password.encode()[: MAX_PASSWORD_LEN * 4], salt=_unb64(salt), n=int(n), r=int(r), p=int(p),
            dklen=len(_unb64(expected)), maxmem=128 * 1024 * 1024,
        )
        return hmac.compare_digest(dk, _unb64(expected))
    except (ValueError, TypeError):
        return False


# ── Input sanitising ─────────────────────────────────────────────────────
_CTRL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f​-‏‪-‮⁦-⁩]")
_USERNAME = re.compile(r"^[A-Za-z0-9_.@-]{1,64}$")


def clean_text(value, max_len: int) -> str:
    text = unicodedata.normalize("NFC", str(value or ""))
    return _CTRL.sub("", text).strip()[:max_len]


def valid_username(value: str) -> bool:
    return bool(_USERNAME.match(value or ""))


def require_https(url: str, name: str) -> str:
    """Return `url` if it is https (http allowed only for localhost outside production)."""
    u = urlparse(url)
    local = u.hostname in ("localhost", "127.0.0.1")
    if not u.netloc or not (u.scheme == "https" or (u.scheme == "http" and local and not IS_PROD)):
        raise ValueError(f"{name} must be an https URL")
    return url


# ── Client identity ──────────────────────────────────────────────────────
def client_ip() -> str:
    parts = [p.strip() for p in request.headers.get("X-Forwarded-For", "").split(",") if p.strip()]
    if parts and TRUSTED_PROXY_HOPS > 0:
        return parts[max(0, len(parts) - TRUSTED_PROXY_HOPS)]
    return request.remote_addr or "unknown"


def ip_hash(ip: str | None = None) -> str:
    key = (IP_HASH_SALT or SECRET_KEY or "dev").encode()
    return hmac.new(key, (ip or client_ip()).encode(), hashlib.sha256).hexdigest()[:16]


def session_id() -> str:
    if "sid" not in session:
        session["sid"] = secrets.token_urlsafe(16)
    return session["sid"]


# ── CSRF (signed double-submit cookie, bound to the session) ─────────────
def _csrf_token(sid: str) -> str:
    nonce = secrets.token_urlsafe(16)
    sig = hmac.new(_key(), f"{sid}|{nonce}".encode(), hashlib.sha256).hexdigest()[:32]
    return f"{nonce}.{sig}"


def _csrf_valid(token: str, sid: str) -> bool:
    nonce, _, sig = (token or "").partition(".")
    good = hmac.new(_key(), f"{sid}|{nonce}".encode(), hashlib.sha256).hexdigest()[:32]
    return bool(nonce) and hmac.compare_digest(sig, good)


def _set_csrf_cookie(resp: Response) -> Response:
    resp.set_cookie(CSRF_COOKIE, _csrf_token(session_id()), secure=IS_PROD, httponly=False, samesite="Lax", path="/")
    return resp


_KEY = b""


def _key() -> bytes:
    return _KEY or b"dev"


# ── Admin auth ───────────────────────────────────────────────────────────
_dummy_hash = ""


def admin_configured() -> bool:
    return bool(ADMIN_PASSWORD_HASH)


def is_admin() -> bool:
    token, now = session.get("admin"), time.time()
    if not token or not admin_configured():
        return False
    rec = state.kv_get(f"admin:{token}")
    if not rec or now - rec["t"] > ADMIN_SESSION_MAX_AGE_S or now - rec["seen"] > ADMIN_IDLE_TIMEOUT_S:
        state.kv_del(f"admin:{token}")
        session.pop("admin", None)
        return False
    if now - rec["seen"] > 60:
        state.kv_set(f"admin:{token}", {**rec, "seen": now})
    return True


def admin_login(username: str, password: str) -> tuple[bool, str]:
    global _dummy_hash
    if not admin_configured():
        return False, "Admin access is not configured."
    username, password = clean_text(username, 64), (password or "")[:MAX_PASSWORD_LEN]
    keys = (f"login:ip:{ip_hash()}", f"login:user:{username.lower()}")
    if any(state.count(k, LOGIN_LOCK_WINDOW_S) >= LOGIN_MAX_FAILURES for k in keys):
        return False, "Too many failed attempts. Try again later."
    _dummy_hash = _dummy_hash or hash_password(secrets.token_hex(8))
    pw_ok = verify_password(password, ADMIN_PASSWORD_HASH if valid_username(username) else _dummy_hash)
    user_ok = valid_username(username) and hmac.compare_digest(username.encode(), ADMIN_USERNAME.encode())
    if not (user_ok and pw_ok):
        for k in keys:
            state.record(k)
        log.warning("admin login failed ip=%s", ip_hash())
        return False, "Invalid username or password."
    for k in keys:
        state.clear(k)
    session.clear()
    session_id()
    token, now = secrets.token_urlsafe(32), time.time()
    state.kv_set(f"admin:{token}", {"u": username, "t": now, "seen": now})
    session["admin"] = token
    after_this_request(_set_csrf_cookie)
    return True, ""


def admin_logout() -> None:
    if session.get("admin"):
        state.kv_del(f"admin:{session['admin']}")
    session.clear()
    session_id()
    after_this_request(_set_csrf_cookie)


# ── Hooks ────────────────────────────────────────────────────────────────
_BLOCKED = re.compile(r"(^|/)\.|\.(py|pyc|env|sample|md|toml|lock|sqlite3?)$|(^|/)(manifest\.json|requirements\.txt)$", re.I)
_CALLBACK_PATH = "_dash-update-component"


def _csp(html: str | None) -> str:
    scripts = ""
    if html:
        body = re.sub(r"<!--.*?-->", "", html, flags=re.S)
        for m in re.findall(r"<script(?![^>]*\bsrc=)(?![^>]*application/json)[^>]*>(.*?)</script>", body, flags=re.S):
            scripts += " 'sha256-" + base64.b64encode(hashlib.sha256(m.encode()).digest()).decode() + "'"
    return "; ".join(
        [
            "default-src 'self'",
            f"script-src 'self'{scripts}",
            "style-src 'self' 'unsafe-inline'",
            "img-src 'self' data:",
            "font-src 'self'",
            "connect-src 'self'",
            "object-src 'none'",
            "base-uri 'self'",
            "form-action 'self'",
            f"frame-ancestors {FRAME_ANCESTORS}",
        ]
    )


def init_security(app) -> None:
    global _KEY
    server = app.server
    if IS_PROD and len(SECRET_KEY) < 32:
        raise RuntimeError("SECRET_KEY (min 32 chars) is required when APP_ENV=production")
    server.secret_key = SECRET_KEY or secrets.token_hex(32)
    _KEY = server.secret_key.encode()
    server.debug = False
    server.config.update(
        SESSION_COOKIE_NAME=SESSION_COOKIE,
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax",
        SESSION_COOKIE_SECURE=IS_PROD,
        SESSION_COOKIE_PATH="/",
        MAX_CONTENT_LENGTH=MAX_BODY_BYTES,
        TESTING=False,
        PROPAGATE_EXCEPTIONS=False,
    )

    @server.before_request
    def _guard():
        if request.method not in ("GET", "HEAD", "POST", "OPTIONS"):
            return jsonify(error="Method not allowed"), 405
        if _BLOCKED.search(request.path):
            return jsonify(error="Not found"), 404
        origin = request.headers.get("Origin", "").rstrip("/")
        if request.method == "OPTIONS":
            return Response(status=204)
        if request.method == "POST":
            if request.path.rsplit("/", 1)[-1] == _CALLBACK_PATH:
                if not request.is_json:
                    return jsonify(error="Unsupported media type"), 415
                ok, _, retry = state.hit(f"page:{ip_hash()}", *RATE_LIMIT_PAGE)
                if not ok:
                    return _json_429(retry)
            if ALLOWED_ORIGINS and origin and origin not in ALLOWED_ORIGINS:
                return jsonify(error="Origin not allowed"), 403
            header, cookie = request.headers.get(CSRF_HEADER, ""), request.cookies.get(CSRF_COOKIE, "")
            if not (header and hmac.compare_digest(header, cookie) and _csrf_valid(cookie, session.get("sid", ""))):
                return jsonify(error="CSRF validation failed"), 403
        return None

    @server.after_request
    def _headers(resp: Response):
        origin = request.headers.get("Origin", "").rstrip("/")
        if origin and origin in ALLOWED_ORIGINS:
            resp.headers["Access-Control-Allow-Origin"] = origin
            resp.headers["Access-Control-Allow-Methods"] = "GET, POST"
            resp.headers["Access-Control-Allow-Headers"] = f"Content-Type, {CSRF_HEADER}"
            resp.headers.add("Vary", "Origin")
        is_html = resp.mimetype == "text/html"
        if is_html:
            session_id()
            if not request.cookies.get(CSRF_COOKIE) or not _csrf_valid(request.cookies.get(CSRF_COOKIE, ""), session["sid"]):
                _set_csrf_cookie(resp)
        resp.headers["Content-Security-Policy"] = (
            _csp(resp.get_data(as_text=True)) if is_html else f"default-src 'none'; frame-ancestors {FRAME_ANCESTORS}"
        )
        resp.headers["X-Content-Type-Options"] = "nosniff"
        resp.headers["X-Frame-Options"] = "SAMEORIGIN"
        resp.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        resp.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=(), payment=(), usb=()"
        resp.headers["Cross-Origin-Opener-Policy"] = "same-origin"
        resp.headers["Cross-Origin-Resource-Policy"] = "same-origin"
        if IS_PROD:
            resp.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
        if is_html or request.path.rsplit("/", 1)[-1].startswith("_dash-"):
            resp.headers["Cache-Control"] = "no-store"
        resp.headers.pop("Server", None)
        return resp

    @server.errorhandler(413)
    def _too_large(_):
        return jsonify(error="Request too large"), 413

    @server.errorhandler(Exception)
    def _unhandled(exc):
        from werkzeug.exceptions import HTTPException

        if isinstance(exc, HTTPException):
            return jsonify(error=exc.name), exc.code
        log.exception("unhandled error")
        return jsonify(error="Internal server error"), 500


def _json_429(retry: int):
    resp = jsonify(error="Too many requests. Please wait and try again.")
    resp.status_code = 429
    resp.headers["Retry-After"] = str(retry)
    return resp


def rate_limited(prefix: str, limit: int, window_s: int) -> tuple[bool, int]:
    """Per-client limit for an action; returns (blocked, retry_after_s)."""
    ok, _, retry = state.hit(f"{prefix}:{ip_hash()}", limit, window_s)
    return (not ok), retry


if __name__ == "__main__":
    pw = getpass.getpass("New admin password: ")
    if len(pw) < 12 or pw != getpass.getpass("Repeat: "):
        raise SystemExit("Passwords differ or are shorter than 12 characters.")
    print(hash_password(pw))
