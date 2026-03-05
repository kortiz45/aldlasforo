from __future__ import annotations

import mimetypes
import os
import re
import time
import uuid
import json
import importlib
import hashlib
import hmac
import secrets
import ssl
from collections import defaultdict, deque
from contextlib import closing
from datetime import datetime, timedelta, timezone
from pathlib import Path
from threading import Lock
from typing import Optional
from urllib.parse import parse_qsl, quote, unquote, urlparse

import httpx
from passlib.context import CryptContext
from fastapi import Body, FastAPI, File, Form, HTTPException, Request, Response, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.responses import FileResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

postgres_dbapi = None
POSTGRES_DRIVER = "none"
for module_name, driver_name in (
    ("psycopg2", "psycopg2"),
    ("psycopg", "psycopg"),
    ("pg8000.dbapi", "pg8000"),
):
    try:
        postgres_dbapi = importlib.import_module(module_name)
        POSTGRES_DRIVER = driver_name
        break
    except Exception:
        continue

app = FastAPI()

BASE_DIR = Path(__file__).resolve().parents[1]
ASSETS_DIR = BASE_DIR / "assets"
UPLOADS_DIR = ASSETS_DIR / "uploads"
IMAGES_DIR = UPLOADS_DIR / "images"
VIDEOS_DIR = UPLOADS_DIR / "videos"
# Use /tmp for temporary uploads in Vercel/serverless environments
TMP_UPLOADS_DIR = Path("/tmp") / "uploads"
DATA_DIR = BASE_DIR / "data"
VIP_PAYMENT_QR_FILE = DATA_DIR / "vip-payment-qr.json"
USERS_FILE = DATA_DIR / "users.json"
WALLETS_FILE = DATA_DIR / "wallets.json"
GIFTS_FILE = DATA_DIR / "gifts.json"
SETTINGS_FILE = DATA_DIR / "settings.json"
MEDIA_PUBLIC_BASE_URL = (
    os.getenv("MEDIA_PUBLIC_BASE_URL", "").strip()
    or os.getenv("HOSTGATOR_BASE_URL", "").strip()
    or os.getenv("PUBLIC_BASE_URL", "").strip()
).rstrip("/")
MEDIA_STORAGE_MODE = os.getenv("MEDIA_STORAGE_MODE", "local").strip().lower() or "local"

# Only /tmp is writable in Vercel. Never attempt to create local static directories.
# Always ensure /tmp/uploads exists (this is the ONLY directory creation allowed)
try:
    TMP_UPLOADS_DIR.mkdir(parents=True, exist_ok=True)
except (OSError, PermissionError):
    pass

def _load_env_file(path: Path) -> None:
    if not path.exists():
        return
    try:
        content = path.read_text(encoding="utf-8")
    except Exception:
        return
    for raw_line in content.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip()
        if not key:
            continue
        if len(value) >= 2 and value[0] == value[-1] and value[0] in ("'", '"'):
            value = value[1:-1]
        if key not in os.environ:
            os.environ[key] = value

_load_env_file(BASE_DIR / ".env")

MAX_IMAGE_MB = int(os.getenv("MAX_IMAGE_MB", "10"))
MAX_VIDEO_MB = int(os.getenv("MAX_VIDEO_MB", "2048"))
MAX_IMAGE_BYTES = MAX_IMAGE_MB * 1024 * 1024
MAX_VIDEO_BYTES = MAX_VIDEO_MB * 1024 * 1024
CHUNK_SIZE = 1024 * 1024

ALLOWED_IMAGE_TYPES = {
    "image/jpeg",
    "image/png",
    "image/webp",
    "image/gif",
    "image/avif",
}
ALLOWED_VIDEO_TYPES = {
    "video/mp4",
    "video/webm",
    "video/quicktime",
    "video/x-matroska",
}
CONTENT_TYPE_EXTENSION_MAP = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
    "image/gif": ".gif",
    "image/avif": ".avif",
    "video/mp4": ".mp4",
    "video/webm": ".webm",
    "video/quicktime": ".mov",
    "video/x-matroska": ".mkv",
}

SUPABASE_URL = os.getenv("SUPABASE_URL", "").strip().rstrip("/")
SUPABASE_SERVICE_ROLE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "").strip()
SUPABASE_BUCKET = os.getenv("SUPABASE_BUCKET", "foro-media").strip() or "foro-media"
DATABASE_URL = os.getenv("DATABASE_URL", "").strip()
ADMIN_API_KEY = os.getenv("ADMIN_API_KEY", "").strip()
ADMIN_USERNAME = os.getenv("ADMIN_USERNAME", "admin").strip() or "admin"
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "admin123")
ADMIN_PASSWORD_SHA256 = os.getenv("ADMIN_PASSWORD_SHA256", "").strip().lower()
ADMIN_SESSION_TTL_SECONDS = max(300, int(os.getenv("ADMIN_SESSION_TTL_SECONDS", "28800")))
ADMIN_SESSION_COOKIE_NAME = os.getenv("ADMIN_SESSION_COOKIE_NAME", "mb_admin_session").strip() or "mb_admin_session"
ADMIN_SESSION_COOKIE_SECURE = os.getenv("ADMIN_SESSION_COOKIE_SECURE", "0").strip().lower() in {"1", "true", "yes", "on"}
ADMIN_SESSION_COOKIE_SAMESITE = os.getenv("ADMIN_SESSION_COOKIE_SAMESITE", "lax").strip().lower()
ADMIN_CSRF_HEADER_NAME = "x-admin-csrf-token"
USER_SESSION_TTL_SECONDS = max(300, int(os.getenv("USER_SESSION_TTL_SECONDS", "86400")))
USER_SESSION_COOKIE_NAME = os.getenv("USER_SESSION_COOKIE_NAME", "mb_user_session").strip() or "mb_user_session"
USER_SESSION_COOKIE_SECURE = os.getenv("USER_SESSION_COOKIE_SECURE", str(int(ADMIN_SESSION_COOKIE_SECURE))).strip().lower() in {"1", "true", "yes", "on"}
USER_SESSION_COOKIE_SAMESITE = os.getenv("USER_SESSION_COOKIE_SAMESITE", "lax").strip().lower()
USER_CSRF_HEADER_NAME = "x-user-csrf-token"
WALLET_MAX_SINGLE_SPEND = max(1, int(os.getenv("WALLET_MAX_SINGLE_SPEND", "200000")))
DAILY_BONUS_CREDITS = max(1, int(os.getenv("DAILY_BONUS_CREDITS", "2")))
DAILY_BONUS_INTERVAL_SECONDS = max(3600, int(os.getenv("DAILY_BONUS_INTERVAL_SECONDS", "86400")))
TRUSTED_HOSTS = os.getenv("TRUSTED_HOSTS", "127.0.0.1,localhost").strip()
RATE_LIMIT_WINDOW_SECONDS = max(1, int(os.getenv("RATE_LIMIT_WINDOW_SECONDS", "60")))
RATE_LIMIT_REQUESTS_PER_WINDOW = max(1, int(os.getenv("RATE_LIMIT_REQUESTS_PER_WINDOW", "45")))
LOGIN_LOCK_WINDOW_SECONDS = max(60, int(os.getenv("LOGIN_LOCK_WINDOW_SECONDS", "900")))
LOGIN_MAX_FAILED_ATTEMPTS = max(3, int(os.getenv("LOGIN_MAX_FAILED_ATTEMPTS", "6")))
USER_LOGIN_LOCK_WINDOW_SECONDS = max(60, int(os.getenv("USER_LOGIN_LOCK_WINDOW_SECONDS", "900")))
USER_LOGIN_MAX_FAILED_ATTEMPTS = max(3, int(os.getenv("USER_LOGIN_MAX_FAILED_ATTEMPTS", "8")))
FORCE_HTTPS = os.getenv("FORCE_HTTPS", "0").strip().lower() in {"1", "true", "yes", "on"}
CORS_ALLOW_ORIGINS = os.getenv(
    "CORS_ALLOW_ORIGINS",
    "http://localhost:3000,http://127.0.0.1:3000,http://localhost:5500,http://127.0.0.1:5500,http://localhost:8000,http://127.0.0.1:8000",
).strip()

DEFAULT_CORS_ORIGINS = [
    "http://localhost:3000",
    "http://127.0.0.1:3000",
    "http://localhost:5500",
    "http://127.0.0.1:5500",
    "http://localhost:8000",
    "http://127.0.0.1:8000",
]
USER_PROTECTED_PAGES = {"foro", "creditos", "vip-upgrade", "gift-dashboard"}
ALLOWED_USER_ROLES = {"user", "seller", "admin", "pro", "owner", "co_owner"}
PRIVILEGED_ADMIN_ROLES = {"admin", "owner"}

if CORS_ALLOW_ORIGINS == "*":
    _cors_origins = DEFAULT_CORS_ORIGINS.copy()
else:
    _cors_origins = [o.strip() for o in CORS_ALLOW_ORIGINS.split(",") if o.strip()]
if not _cors_origins:
    _cors_origins = DEFAULT_CORS_ORIGINS.copy()

if ADMIN_SESSION_COOKIE_SAMESITE not in {"lax", "strict", "none"}:
    ADMIN_SESSION_COOKIE_SAMESITE = "lax"
if ADMIN_SESSION_COOKIE_SAMESITE == "none" and not ADMIN_SESSION_COOKIE_SECURE:
    ADMIN_SESSION_COOKIE_SAMESITE = "lax"
if USER_SESSION_COOKIE_SAMESITE not in {"lax", "strict", "none"}:
    USER_SESSION_COOKIE_SAMESITE = "lax"
if USER_SESSION_COOKIE_SAMESITE == "none" and not USER_SESSION_COOKIE_SECURE:
    USER_SESSION_COOKIE_SAMESITE = "lax"

_trusted_hosts = [h.strip() for h in TRUSTED_HOSTS.split(",") if h.strip()]
if _trusted_hosts:
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=_trusted_hosts)

app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "X-Admin-Key", "X-Admin-Csrf-Token", "X-User-Csrf-Token"],
)

_rate_buckets: dict[str, deque[float]] = defaultdict(deque)
_admin_sessions: dict[str, dict[str, float | str]] = {}
_login_failures: dict[str, deque[float]] = defaultdict(deque)
_user_sessions: dict[str, dict[str, float | str]] = {}
_user_login_failures: dict[str, deque[float]] = defaultdict(deque)
_password_context = CryptContext(schemes=["pbkdf2_sha256"], deprecated="auto")
_tx_log_entries: deque[dict] = deque(maxlen=max(1000, int(os.getenv("TX_LOG_MAX_ENTRIES", "5000"))))
_tx_log_lock = Lock()


@app.middleware("http")
async def enforce_https_redirect(request: Request, call_next):
    if FORCE_HTTPS:
        forwarded_proto = (request.headers.get("x-forwarded-proto") or "").strip().lower()
        request_scheme = request.url.scheme.lower()
        if forwarded_proto != "https" and request_scheme != "https":
            target = str(request.url.replace(scheme="https"))
            return RedirectResponse(url=target, status_code=307)
    return await call_next(request)


@app.middleware("http")
async def apply_security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Frame-Options", "DENY")
    response.headers.setdefault("Referrer-Policy", "no-referrer")
    response.headers.setdefault("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
    response.headers.setdefault("Cross-Origin-Opener-Policy", "same-origin")
    response.headers.setdefault("Cross-Origin-Resource-Policy", "same-origin")
    response.headers.setdefault(
        "Content-Security-Policy",
        "default-src 'self'; object-src 'none'; frame-ancestors 'none'; "
        "img-src 'self' https: data:; media-src 'self' https: data:; "
        "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com https://cdnjs.cloudflare.com; "
        "font-src 'self' https://fonts.gstatic.com https://cdnjs.cloudflare.com data:; "
        "script-src 'self' 'unsafe-inline'; connect-src 'self' https: http://127.0.0.1:8000 http://localhost:8000; "
        "base-uri 'self'; form-action 'self'"
    )
    if request.url.scheme == "https":
        response.headers.setdefault("Strict-Transport-Security", "max-age=31536000; includeSubDomains")
    if request.url.path == "/admin.html" or request.url.path.startswith("/api/auth/"):
        response.headers.setdefault("Cache-Control", "no-store")
    return response


def _extract_admin_token(request: Request) -> str:
    token = (request.headers.get("x-admin-key") or "").strip()
    if token:
        return token

    auth = (request.headers.get("authorization") or "").strip()
    if auth.lower().startswith("bearer "):
        return auth[7:].strip()
    return ""


def _has_valid_admin_api_key(request: Request) -> bool:
    if not ADMIN_API_KEY:
        return False
    token = _extract_admin_token(request)
    if not token:
        return False
    return hmac.compare_digest(token, ADMIN_API_KEY)


def _hash_password_sha256(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _is_valid_admin_password(password: str) -> bool:
    if ADMIN_PASSWORD_SHA256:
        return hmac.compare_digest(_hash_password_sha256(password), ADMIN_PASSWORD_SHA256)
    return hmac.compare_digest(password, ADMIN_PASSWORD)


def _cleanup_admin_sessions() -> None:
    now = time.time()
    expired_ids = [
        session_id
        for session_id, data in list(_admin_sessions.items())
        if float(data.get("expires_at", 0)) <= now
    ]
    for session_id in expired_ids:
        _admin_sessions.pop(session_id, None)


def create_admin_session(username: str) -> str:
    _cleanup_admin_sessions()
    session_id = secrets.token_urlsafe(48)
    _admin_sessions[session_id] = {
        "username": username,
        "csrf_token": secrets.token_urlsafe(32),
        "expires_at": time.time() + float(ADMIN_SESSION_TTL_SECONDS),
    }
    return session_id


def get_admin_session(request: Request) -> Optional[dict]:
    _cleanup_admin_sessions()
    session_id = (request.cookies.get(ADMIN_SESSION_COOKIE_NAME) or "").strip()
    if not session_id:
        return None
    data = _admin_sessions.get(session_id)
    if not data:
        return None
    expires_at = float(data.get("expires_at", 0))
    if expires_at <= time.time():
        _admin_sessions.pop(session_id, None)
        return None
    return {
        "id": session_id,
        "username": str(data.get("username", ADMIN_USERNAME)),
        "csrf_token": str(data.get("csrf_token", "")),
        "expires_at": expires_at,
    }


def _extract_admin_csrf_token(request: Request) -> str:
    return (
        (request.headers.get(ADMIN_CSRF_HEADER_NAME) or "").strip()
        or (request.headers.get(USER_CSRF_HEADER_NAME) or "").strip()
    )


def _get_privileged_user_session(request: Request) -> Optional[dict]:
    user_session = get_user_session(request)
    if not user_session:
        return None

    users = _load_users_store()
    user = _find_user_by_username(users, str(user_session.get("username", "")))
    if not user or _user_is_expired(user):
        _user_sessions.pop(str(user_session.get("id", "")), None)
        return None

    role = _normalize_user_role(user.get("role", "user"))
    if role not in PRIVILEGED_ADMIN_ROLES:
        return None

    return {"session": user_session, "user": user, "role": role}


def _has_admin_portal_access(request: Request) -> bool:
    return bool(get_admin_session(request) or _get_privileged_user_session(request))


def require_admin_access(request: Request, *, require_csrf: bool = False) -> None:
    if _has_valid_admin_api_key(request):
        return

    admin_session = get_admin_session(request)
    if admin_session:
        if not require_csrf:
            return
        csrf_token = _extract_admin_csrf_token(request)
        expected = str(admin_session.get("csrf_token", ""))
        if not csrf_token or not expected or not hmac.compare_digest(csrf_token, expected):
            raise HTTPException(status_code=403, detail="Invalid CSRF token")
        return

    privileged = _get_privileged_user_session(request)
    if not privileged:
        raise HTTPException(status_code=401, detail="Unauthorized")
    if not require_csrf:
        return

    csrf_token = _extract_admin_csrf_token(request)
    expected = str(privileged.get("session", {}).get("csrf_token", ""))
    if not csrf_token or not expected or not hmac.compare_digest(csrf_token, expected):
        raise HTTPException(status_code=403, detail="Invalid CSRF token")


def apply_rate_limit(request: Request, scope: str) -> None:
    client_ip = request.client.host if request.client and request.client.host else "unknown"
    key = f"{scope}:{client_ip}"
    bucket = _rate_buckets[key]
    now = time.monotonic()

    while bucket and (now - bucket[0]) > RATE_LIMIT_WINDOW_SECONDS:
        bucket.popleft()

    if len(bucket) >= RATE_LIMIT_REQUESTS_PER_WINDOW:
        raise HTTPException(status_code=429, detail="Too many requests")

    bucket.append(now)


def _login_throttle_key(request: Request, username: str) -> str:
    client_ip = request.client.host if request.client and request.client.host else "unknown"
    return f"{client_ip}:{username.lower().strip()}"


def _cleanup_failed_logins(key: str) -> deque[float]:
    bucket = _login_failures[key]
    now = time.monotonic()
    while bucket and (now - bucket[0]) > LOGIN_LOCK_WINDOW_SECONDS:
        bucket.popleft()
    return bucket


def is_login_temporarily_blocked(request: Request, username: str) -> bool:
    key = _login_throttle_key(request, username)
    bucket = _cleanup_failed_logins(key)
    return len(bucket) >= LOGIN_MAX_FAILED_ATTEMPTS


def record_login_failure(request: Request, username: str) -> None:
    key = _login_throttle_key(request, username)
    bucket = _cleanup_failed_logins(key)
    bucket.append(time.monotonic())


def clear_login_failures(request: Request, username: str) -> None:
    key = _login_throttle_key(request, username)
    _login_failures.pop(key, None)


def _normalize_username(value: str) -> str:
    return re.sub(r"\s+", "", (value or "").strip()).lower()


def _is_valid_username(value: str) -> bool:
    return bool(re.fullmatch(r"[a-zA-Z0-9_.-]{3,32}", value or ""))


def _normalize_user_role(value: str) -> str:
    role = str(value or "user").strip().lower() or "user"
    return role if role in ALLOWED_USER_ROLES else "user"


def _require_postgres_enabled() -> None:
    if not _is_postgres_enabled():
        raise HTTPException(
            status_code=503,
            detail="Postgres storage unavailable. Configure DATABASE_URL and postgres driver",
        )


def _db_fetchall(sql: str, params: tuple = ()) -> list[dict]:
    _require_postgres_enabled()
    with _connect_postgres() as conn:
        with closing(conn.cursor()) as cur:
            cur.execute(sql, params)
            rows = cur.fetchall()
            columns = [desc[0] for desc in (cur.description or [])]
    return [dict(zip(columns, row)) for row in rows]


def _db_fetchone(sql: str, params: tuple = ()) -> Optional[dict]:
    rows = _db_fetchall(sql, params)
    return rows[0] if rows else None


def _db_execute(sql: str, params: tuple = ()) -> None:
    _require_postgres_enabled()
    with _connect_postgres() as conn:
        with closing(conn.cursor()) as cur:
            cur.execute(sql, params)


def ensure_app_tables() -> None:
    _require_postgres_enabled()
    ddl = """
    CREATE TABLE IF NOT EXISTS users (
        username TEXT PRIMARY KEY,
        username_lower TEXT NOT NULL UNIQUE,
        password_hash TEXT NOT NULL,
        role VARCHAR(32) NOT NULL DEFAULT 'user',
        plan VARCHAR(32) NOT NULL DEFAULT 'free',
        status VARCHAR(32) NOT NULL DEFAULT 'Activo',
        is_vip BOOLEAN NOT NULL DEFAULT FALSE,
        expiry_date DATE NULL,
        device_lock TEXT NULL,
        daily_credits_at TIMESTAMPTZ NULL,
        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
    );

    CREATE TABLE IF NOT EXISTS wallets (
        username_lower TEXT PRIMARY KEY,
        balance BIGINT NOT NULL DEFAULT 0,
        updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        CONSTRAINT wallets_balance_nonnegative CHECK (balance >= 0),
        CONSTRAINT wallets_user_fk FOREIGN KEY (username_lower) REFERENCES users(username_lower) ON DELETE CASCADE
    );

    CREATE TABLE IF NOT EXISTS gifts (
        code TEXT PRIMARY KEY,
        kind VARCHAR(32) NOT NULL,
        plan VARCHAR(32) NOT NULL DEFAULT 'vip',
        days INTEGER NOT NULL DEFAULT 30,
        credits BIGINT NOT NULL DEFAULT 0,
        status VARCHAR(16) NOT NULL DEFAULT 'active',
        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        used_at TIMESTAMPTZ NULL,
        used_by TEXT NULL
    );

    CREATE TABLE IF NOT EXISTS settings (
        key TEXT PRIMARY KEY,
        value JSONB NOT NULL DEFAULT '{}'::jsonb,
        updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
    );
    """
    with _connect_postgres() as conn:
        with closing(conn.cursor()) as cur:
            cur.execute(ddl)


def _load_users_store() -> list[dict]:
    rows = _db_fetchall(
        """
        SELECT
            username,
            username_lower,
            password_hash,
            role,
            plan,
            status,
            is_vip,
            expiry_date,
            device_lock,
            daily_credits_at,
            created_at,
            updated_at
        FROM users
        ORDER BY username_lower ASC;
        """
    )
    clean: list[dict] = []
    for raw in rows:
        if not isinstance(raw, dict):
            continue
        username = str(raw.get("username", "")).strip()
        username_lower = _normalize_username(raw.get("username_lower") or username)
        password_hash = str(raw.get("password_hash", "")).strip()
        if not username or not username_lower or not password_hash:
            continue
        clean.append(
            {
                "username": username,
                "username_lower": username_lower,
                "password_hash": password_hash,
                "role": _normalize_user_role(raw.get("role", "user")),
                "plan": str(raw.get("plan", "free")).strip().lower() or "free",
                "status": str(raw.get("status", "Activo")).strip() or "Activo",
                "isVip": bool(raw.get("is_vip", False)),
                "expiryDate": str(raw.get("expiry_date", "")).strip() or None,
                "deviceLock": str(raw.get("device_lock", "")).strip() or None,
                "dailyCreditsAt": str(raw.get("daily_credits_at", "")).strip() or None,
                "createdAt": str(raw.get("created_at", "")).strip() or datetime.now(timezone.utc).isoformat(),
                "updatedAt": str(raw.get("updated_at", "")).strip() or datetime.now(timezone.utc).isoformat(),
            }
        )
    return clean


def _save_users_store(users: list[dict]) -> None:
    clean_users = [u for u in users if isinstance(u, dict)]
    with _connect_postgres() as conn:
        with closing(conn.cursor()) as cur:
            usernames = [_normalize_username(u.get("username_lower") or u.get("username", "")) for u in clean_users]
            usernames = [u for u in usernames if u]
            if usernames:
                placeholders = ", ".join(["%s"] * len(usernames))
                cur.execute(f"DELETE FROM users WHERE username_lower NOT IN ({placeholders})", tuple(usernames))
            else:
                cur.execute("DELETE FROM users")

            upsert_sql = """
            INSERT INTO users (
                username,
                username_lower,
                password_hash,
                role,
                plan,
                status,
                is_vip,
                expiry_date,
                device_lock,
                daily_credits_at,
                created_at,
                updated_at
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (username_lower) DO UPDATE SET
                username = EXCLUDED.username,
                password_hash = EXCLUDED.password_hash,
                role = EXCLUDED.role,
                plan = EXCLUDED.plan,
                status = EXCLUDED.status,
                is_vip = EXCLUDED.is_vip,
                expiry_date = EXCLUDED.expiry_date,
                device_lock = EXCLUDED.device_lock,
                daily_credits_at = EXCLUDED.daily_credits_at,
                created_at = EXCLUDED.created_at,
                updated_at = EXCLUDED.updated_at;
            """
            for raw in clean_users:
                username = str(raw.get("username", "")).strip()
                username_lower = _normalize_username(raw.get("username_lower") or username)
                password_hash = str(raw.get("password_hash", "")).strip()
                if not username or not username_lower or not password_hash:
                    continue
                cur.execute(
                    upsert_sql,
                    (
                        username,
                        username_lower,
                        password_hash,
                        _normalize_user_role(raw.get("role", "user")),
                        str(raw.get("plan", "free")).strip().lower() or "free",
                        str(raw.get("status", "Activo")).strip() or "Activo",
                        bool(raw.get("isVip", False)),
                        str(raw.get("expiryDate", "")).strip() or None,
                        str(raw.get("deviceLock", "")).strip() or None,
                        str(raw.get("dailyCreditsAt", "")).strip() or None,
                        str(raw.get("createdAt", "")).strip() or datetime.now(timezone.utc).isoformat(),
                        str(raw.get("updatedAt", "")).strip() or datetime.now(timezone.utc).isoformat(),
                    ),
                )


def _load_wallets_store_unlocked() -> dict[str, int]:
    rows = _db_fetchall("SELECT username_lower, balance FROM wallets")
    clean: dict[str, int] = {}
    for row in rows:
        username = _normalize_username(str(row.get("username_lower", "")))
        if not username:
            continue
        try:
            value = int(round(float(row.get("balance", 0))))
        except Exception:
            value = 0
        clean[username] = max(0, value)
    return clean


def _save_wallets_store_unlocked(wallets: dict[str, int]) -> None:
    with _connect_postgres() as conn:
        with closing(conn.cursor()) as cur:
            usernames = [_normalize_username(str(u)) for u in wallets.keys()]
            usernames = [u for u in usernames if u]
            if usernames:
                placeholders = ", ".join(["%s"] * len(usernames))
                cur.execute(f"DELETE FROM wallets WHERE username_lower NOT IN ({placeholders})", tuple(usernames))
            else:
                cur.execute("DELETE FROM wallets")

            for raw_user, raw_balance in wallets.items():
                username = _normalize_username(str(raw_user))
                if not username:
                    continue
                try:
                    value = int(round(float(raw_balance)))
                except Exception:
                    value = 0
                cur.execute(
                    """
                    INSERT INTO wallets (username_lower, balance, updated_at)
                    VALUES (%s, %s, NOW())
                    ON CONFLICT (username_lower) DO UPDATE
                    SET balance = EXCLUDED.balance, updated_at = NOW();
                    """,
                    (username, max(0, value)),
                )


def _load_wallets_store() -> dict[str, int]:
    return _load_wallets_store_unlocked()


def _save_wallets_store(wallets: dict[str, int]) -> None:
    _save_wallets_store_unlocked(wallets)


def _wallet_apply_delta(username: str, delta: int, *, require_sufficient: bool = False) -> tuple[int, int]:
    normalized = _normalize_username(username)
    if not normalized:
        raise HTTPException(status_code=400, detail="Invalid username")

    safe_delta = int(round(float(delta)))
    with _connect_postgres() as conn:
        with closing(conn.cursor()) as cur:
            cur.execute("SELECT balance FROM wallets WHERE username_lower = %s FOR UPDATE", (normalized,))
            row = cur.fetchone()
            current = max(0, int(row[0])) if row else 0
            next_balance = current + safe_delta
            if require_sufficient and next_balance < 0:
                raise HTTPException(status_code=409, detail="Insufficient credits")
            next_balance = max(0, next_balance)
            cur.execute(
                """
                INSERT INTO wallets (username_lower, balance, updated_at)
                VALUES (%s, %s, NOW())
                ON CONFLICT (username_lower) DO UPDATE
                SET balance = EXCLUDED.balance, updated_at = NOW();
                """,
                (normalized, next_balance),
            )
    return current, next_balance


def _get_wallet_balance(username: str) -> int:
    normalized = _normalize_username(username)
    if not normalized:
        return 0
    wallets = _load_wallets_store()
    return max(0, int(wallets.get(normalized, 0)))


def _add_wallet_credits(username: str, amount: int) -> int:
    delta = int(round(float(amount)))
    _before, next_balance = _wallet_apply_delta(username, delta, require_sufficient=False)
    return next_balance

def _append_transaction_log(entry: dict) -> None:
    try:
        payload = dict(entry or {})
        payload.setdefault("ts", datetime.now(timezone.utc).isoformat())
        with _tx_log_lock:
            _tx_log_entries.append(payload)
        print(f"[tx] {json.dumps(payload, ensure_ascii=True)}")
    except Exception:
        pass

def _notify_alert(event: str, data: dict) -> None:
    url = os.getenv("ADMIN_ALERT_WEBHOOK_URL", "").strip()
    if not url:
        return
    try:
        with httpx.Client(timeout=3.0) as client:
            client.post(url, json={"event": event, "data": data})
    except Exception:
        pass


def _normalize_gift_code(value: str) -> str:
    return re.sub(r"[^A-Z0-9-]", "", str(value or "").upper().strip())


def _build_gift_code(kind: str) -> str:
    prefix = "CRD" if kind == "credits" else "VIP"
    chunk = lambda: secrets.token_hex(2).upper()  # noqa: E731
    return f"{prefix}-{chunk()}-{chunk()}"


def _normalize_gift_entry(raw: dict) -> Optional[dict]:
    if not isinstance(raw, dict):
        return None

    code = _normalize_gift_code(raw.get("code", ""))
    if not code or not re.fullmatch(r"[A-Z0-9]{3,4}-[A-Z0-9]{4}-[A-Z0-9]{4}", code):
        return None

    kind = str(raw.get("kind", raw.get("type", ""))).strip().lower()
    if kind not in {"credits", "vip_subscription"}:
        kind = "credits" if int(raw.get("credits", 0) or 0) > 0 else "vip_subscription"

    plan = str(raw.get("plan", "vip")).strip().lower()
    if plan not in {"vip", "pro", "elite", "black", "god"}:
        plan = "vip"

    try:
        days = int(round(float(raw.get("days", 30))))
    except Exception:
        days = 30
    if days <= 0:
        days = 30

    try:
        credits = int(round(float(raw.get("credits", 0))))
    except Exception:
        credits = 0
    credits = max(0, credits) if kind == "credits" else 0

    status = str(raw.get("status", "active")).strip().lower()
    if status not in {"active", "used", "revoked"}:
        status = "active"

    created_at = str(raw.get("createdAt", "")).strip() or datetime.now(timezone.utc).isoformat()
    used_at = str(raw.get("usedAt", "")).strip()
    used_by = _normalize_username(raw.get("usedBy", ""))

    return {
        "code": code,
        "kind": kind,
        "plan": plan,
        "days": days,
        "credits": credits,
        "status": status,
        "createdAt": created_at,
        "usedAt": used_at,
        "usedBy": used_by,
    }


def _load_gifts_store() -> list[dict]:
    rows = _db_fetchall(
        """
        SELECT
            code,
            kind,
            plan,
            days,
            credits,
            status,
            created_at,
            used_at,
            used_by
        FROM gifts
        ORDER BY created_at DESC;
        """
    )
    clean: list[dict] = []
    for row in rows:
        raw = {
            "code": row.get("code", ""),
            "kind": row.get("kind", ""),
            "plan": row.get("plan", "vip"),
            "days": row.get("days", 30),
            "credits": row.get("credits", 0),
            "status": row.get("status", "active"),
            "createdAt": str(row.get("created_at", "")),
            "usedAt": str(row.get("used_at", "")) if row.get("used_at") else "",
            "usedBy": row.get("used_by", "") or "",
        }
        normalized = _normalize_gift_entry(raw)
        if normalized:
            clean.append(normalized)
    return clean


def _save_gifts_store(gifts: list[dict]) -> None:
    payload = [g for g in (_normalize_gift_entry(item) for item in gifts) if g]
    with _connect_postgres() as conn:
        with closing(conn.cursor()) as cur:
            codes = [str(g.get("code", "")).upper() for g in payload if str(g.get("code", "")).strip()]
            if codes:
                placeholders = ", ".join(["%s"] * len(codes))
                cur.execute(f"DELETE FROM gifts WHERE UPPER(code) NOT IN ({placeholders})", tuple(codes))
            else:
                cur.execute("DELETE FROM gifts")

            upsert_sql = """
            INSERT INTO gifts (
                code,
                kind,
                plan,
                days,
                credits,
                status,
                created_at,
                used_at,
                used_by
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (code) DO UPDATE SET
                kind = EXCLUDED.kind,
                plan = EXCLUDED.plan,
                days = EXCLUDED.days,
                credits = EXCLUDED.credits,
                status = EXCLUDED.status,
                created_at = EXCLUDED.created_at,
                used_at = EXCLUDED.used_at,
                used_by = EXCLUDED.used_by;
            """
            for gift in payload:
                cur.execute(
                    upsert_sql,
                    (
                        str(gift.get("code", "")).upper(),
                        str(gift.get("kind", "credits")).lower(),
                        str(gift.get("plan", "vip")).lower(),
                        int(gift.get("days", 30) or 30),
                        int(gift.get("credits", 0) or 0),
                        str(gift.get("status", "active")).lower(),
                        str(gift.get("createdAt", "")).strip() or datetime.now(timezone.utc).isoformat(),
                        str(gift.get("usedAt", "")).strip() or None,
                        _normalize_username(gift.get("usedBy", "")) or None,
                    ),
                )


def _find_gift_by_code(gifts: list[dict], code: str) -> Optional[dict]:
    wanted = _normalize_gift_code(code)
    for gift in gifts:
        if str(gift.get("code", "")).upper() == wanted:
            return gift
    return None


def _generate_unique_gift_code(kind: str, gifts: list[dict]) -> str:
    existing_codes = {str(g.get("code", "")).upper() for g in gifts}
    for _ in range(40):
        candidate = _build_gift_code(kind)
        if candidate not in existing_codes:
            return candidate
    raise HTTPException(status_code=500, detail="Could not generate unique gift code")


def _apply_vip_subscription(user: dict, plan: str, days: int) -> str:
    safe_plan = str(plan or "vip").strip().lower()
    if safe_plan not in {"vip", "pro", "elite", "black", "god"}:
        safe_plan = "vip"

    safe_days = max(1, int(round(float(days))))
    today = datetime.now(timezone.utc).date()

    current_expiry_raw = str(user.get("expiryDate") or "").strip()
    base_date = today
    if current_expiry_raw and re.fullmatch(r"\d{4}-\d{2}-\d{2}", current_expiry_raw):
        try:
            parsed = datetime.strptime(current_expiry_raw, "%Y-%m-%d").date()
            if parsed > today:
                base_date = parsed
        except Exception:
            base_date = today

    target_date = base_date + timedelta(days=safe_days)
    expiry = target_date.isoformat()

    user["isVip"] = True
    user["plan"] = safe_plan
    user["status"] = "VIP"
    user["expiryDate"] = expiry
    user["updatedAt"] = datetime.now(timezone.utc).isoformat()
    return expiry


def _default_settings_store() -> dict:
    return {
        "announcement": "",
        "contact": {
            "whatsapp": "",
            "telegram": "",
        },
    }


def _sanitize_settings_store(raw: dict) -> dict:
    base = _default_settings_store()
    if not isinstance(raw, dict):
        return base

    announcement = str(raw.get("announcement", "")).strip()
    if len(announcement) > 500:
        announcement = announcement[:500]

    contact_raw = raw.get("contact", {})
    if not isinstance(contact_raw, dict):
        contact_raw = {}
    whatsapp = str(contact_raw.get("whatsapp", "")).strip()
    telegram = str(contact_raw.get("telegram", "")).strip()
    if len(whatsapp) > 120:
        whatsapp = whatsapp[:120]
    if len(telegram) > 120:
        telegram = telegram[:120]

    return {
        "announcement": announcement,
        "contact": {
            "whatsapp": whatsapp,
            "telegram": telegram,
        },
    }


def _load_settings_store() -> dict:
    row = _db_fetchone("SELECT value FROM settings WHERE key = %s", ("global",))
    data = row.get("value") if row else {}
    return _sanitize_settings_store(data if isinstance(data, dict) else {})


def _save_settings_store(settings: dict) -> dict:
    clean = _sanitize_settings_store(settings if isinstance(settings, dict) else {})
    _db_execute(
        """
        INSERT INTO settings (key, value, updated_at)
        VALUES (%s, %s::jsonb, NOW())
        ON CONFLICT (key) DO UPDATE
        SET value = EXCLUDED.value, updated_at = NOW();
        """,
        ("global", json.dumps(clean, ensure_ascii=False)),
    )
    return clean


def _find_user_by_username(users: list[dict], username: str) -> Optional[dict]:
    normalized = _normalize_username(username)
    if not normalized:
        return None
    for user in users:
        if str(user.get("username_lower", "")).strip() == normalized:
            return user
    return None


def _user_is_expired(user: dict) -> bool:
    expiry = str(user.get("expiryDate") or "").strip()
    if not expiry:
        return False
    today = datetime.now(timezone.utc).date().isoformat()
    return expiry < today


def _parse_iso_datetime(value: str) -> Optional[datetime]:
    raw = str(value or "").strip()
    if not raw:
        return None
    if raw.endswith("Z"):
        raw = raw[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(raw)
    except Exception:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed


def _serialize_user_public(user: dict) -> dict:
    is_vip = bool(user.get("isVip", False)) or "vip" in str(user.get("status", "")).lower()
    role = _normalize_user_role(user.get("role", "user"))
    plan = str(user.get("plan", "free")).strip().lower() or "free"
    status = str(user.get("status", "Activo")).strip() or "Activo"
    balance = _get_wallet_balance(str(user.get("username_lower", user.get("username", ""))))
    if _user_is_expired(user):
        status = "Vencido"
    elif is_vip and status.lower() not in {"vip", "vencido"}:
        status = "VIP"
    return {
        "username": str(user.get("username", "")),
        "role": role,
        "plan": plan,
        "status": status,
        "isVip": is_vip,
        "credits": balance,
        "expiryDate": str(user.get("expiryDate", "")).strip() or None,
        "deviceLocked": bool(str(user.get("deviceLock", "")).strip()),
        "createdAt": str(user.get("createdAt", "")).strip() or None,
        "updatedAt": str(user.get("updatedAt", "")).strip() or None,
    }


def _cleanup_user_sessions() -> None:
    now = time.time()
    expired_ids = [
        session_id
        for session_id, data in list(_user_sessions.items())
        if float(data.get("expires_at", 0)) <= now
    ]
    for session_id in expired_ids:
        _user_sessions.pop(session_id, None)


def create_user_session(username: str) -> str:
    _cleanup_user_sessions()
    session_id = secrets.token_urlsafe(48)
    _user_sessions[session_id] = {
        "username": _normalize_username(username),
        "csrf_token": secrets.token_urlsafe(32),
        "expires_at": time.time() + float(USER_SESSION_TTL_SECONDS),
    }
    return session_id


def get_user_session(request: Request) -> Optional[dict]:
    _cleanup_user_sessions()
    session_id = (request.cookies.get(USER_SESSION_COOKIE_NAME) or "").strip()
    if not session_id:
        return None
    data = _user_sessions.get(session_id)
    if not data:
        return None
    expires_at = float(data.get("expires_at", 0))
    if expires_at <= time.time():
        _user_sessions.pop(session_id, None)
        return None
    return {
        "id": session_id,
        "username": str(data.get("username", "")),
        "csrf_token": str(data.get("csrf_token", "")),
        "expires_at": expires_at,
    }


def require_user_access(request: Request, *, require_csrf: bool = False) -> dict:
    session = get_user_session(request)
    if not session:
        raise HTTPException(status_code=401, detail="User session required")
    if require_csrf:
        csrf_token = (request.headers.get(USER_CSRF_HEADER_NAME) or "").strip()
        expected = str(session.get("csrf_token", ""))
        if not csrf_token or not expected or not hmac.compare_digest(csrf_token, expected):
            raise HTTPException(status_code=403, detail="Invalid CSRF token")
    return session


def _user_login_throttle_key(request: Request, username: str) -> str:
    client_ip = request.client.host if request.client and request.client.host else "unknown"
    return f"{client_ip}:{_normalize_username(username)}"


def _cleanup_user_failed_logins(key: str) -> deque[float]:
    bucket = _user_login_failures[key]
    now = time.monotonic()
    while bucket and (now - bucket[0]) > USER_LOGIN_LOCK_WINDOW_SECONDS:
        bucket.popleft()
    return bucket


def user_login_temporarily_blocked(request: Request, username: str) -> bool:
    key = _user_login_throttle_key(request, username)
    bucket = _cleanup_user_failed_logins(key)
    return len(bucket) >= USER_LOGIN_MAX_FAILED_ATTEMPTS


def record_user_login_failure(request: Request, username: str) -> None:
    key = _user_login_throttle_key(request, username)
    bucket = _cleanup_user_failed_logins(key)
    bucket.append(time.monotonic())


def clear_user_login_failures(request: Request, username: str) -> None:
    key = _user_login_throttle_key(request, username)
    _user_login_failures.pop(key, None)


def _set_user_session_cookie(response: Response, session_id: str) -> None:
    response.set_cookie(
        key=USER_SESSION_COOKIE_NAME,
        value=session_id,
        max_age=USER_SESSION_TTL_SECONDS,
        httponly=True,
        secure=USER_SESSION_COOKIE_SECURE,
        samesite=USER_SESSION_COOKIE_SAMESITE,
        path="/",
    )


def _clear_user_session_cookie(response: Response) -> None:
    response.delete_cookie(
        key=USER_SESSION_COOKIE_NAME,
        path="/",
        secure=USER_SESSION_COOKIE_SECURE,
        samesite=USER_SESSION_COOKIE_SAMESITE,
    )


def _is_supabase_enabled() -> bool:
    return bool(SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY)


def _is_postgres_enabled() -> bool:
    return bool(DATABASE_URL and postgres_dbapi is not None)


def _pg8000_connect_kwargs(database_url: str) -> dict[str, object]:
    parsed = urlparse(database_url)
    if parsed.scheme not in {"postgres", "postgresql"}:
        raise ValueError("DATABASE_URL must start with postgres:// or postgresql://")

    database_name = (parsed.path or "").lstrip("/")
    if not database_name:
        raise ValueError("DATABASE_URL must include the database name")

    kwargs: dict[str, object] = {
        "user": unquote(parsed.username) if parsed.username else "",
        "password": unquote(parsed.password) if parsed.password else None,
        "host": parsed.hostname or "localhost",
        "port": parsed.port or 5432,
        "database": unquote(database_name),
    }

    query = dict(parse_qsl(parsed.query, keep_blank_values=True))

    connect_timeout = (query.get("connect_timeout") or "").strip()
    if connect_timeout:
        try:
            kwargs["timeout"] = float(connect_timeout)
        except ValueError:
            pass

    sslmode = (query.get("sslmode") or "").strip().lower()
    if sslmode and sslmode != "disable":
        kwargs["ssl_context"] = ssl.create_default_context()

    return kwargs


def _connect_postgres():
    if POSTGRES_DRIVER == "pg8000":
        return postgres_dbapi.connect(**_pg8000_connect_kwargs(DATABASE_URL))
    return postgres_dbapi.connect(DATABASE_URL)


def ensure_media_table() -> None:
    if not _is_postgres_enabled():
        return
    ddl = """
    CREATE TABLE IF NOT EXISTS media_assets (
        id BIGSERIAL PRIMARY KEY,
        object_key TEXT NOT NULL,
        public_url TEXT NOT NULL,
        media_kind VARCHAR(12) NOT NULL,
        mime_type VARCHAR(120) NOT NULL,
        size_bytes BIGINT NOT NULL,
        storage_provider VARCHAR(32) NOT NULL,
        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
    );
    """
    with _connect_postgres() as conn:
        with closing(conn.cursor()) as cur:
            cur.execute(ddl)


def insert_media_record(
    object_key: str,
    public_url: str,
    media_kind: str,
    mime_type: str,
    size_bytes: int,
    storage_provider: str,
) -> Optional[int]:
    if not _is_postgres_enabled():
        return None

    sql = """
    INSERT INTO media_assets (
        object_key, public_url, media_kind, mime_type, size_bytes, storage_provider
    ) VALUES (%s, %s, %s, %s, %s, %s)
    RETURNING id;
    """
    try:
        with _connect_postgres() as conn:
            with closing(conn.cursor()) as cur:
                cur.execute(
                    sql,
                    (object_key, public_url, media_kind, mime_type, size_bytes, storage_provider),
                )
                row = cur.fetchone()
                return int(row[0]) if row else None
    except Exception as exc:
        print(f"[media] warning postgres insert failed: {exc}")
        return None


def detect_media_kind(content_type: str) -> str:
    ctype = (content_type or "").lower().strip()
    if ctype.startswith("image/"):
        return "image"
    if ctype.startswith("video/"):
        return "video"
    raise HTTPException(status_code=415, detail="Unsupported file type")


def validate_content_type(media_kind: str, content_type: str) -> None:
    ctype = (content_type or "").lower().strip()
    if media_kind == "image" and ctype not in ALLOWED_IMAGE_TYPES:
        raise HTTPException(status_code=415, detail="Image format not allowed")
    if media_kind == "video" and ctype not in ALLOWED_VIDEO_TYPES:
        raise HTTPException(status_code=415, detail="Video format not allowed")


def max_bytes_for_kind(media_kind: str) -> int:
    return MAX_IMAGE_BYTES if media_kind == "image" else MAX_VIDEO_BYTES


def clean_folder(value: str) -> str:
    safe = re.sub(r"[^a-zA-Z0-9/_-]", "", (value or "products")).strip("/")
    return safe or "products"


def is_valid_http_url(value: str) -> bool:
    try:
        parsed = urlparse(value.strip())
    except Exception:
        return False
    if parsed.scheme not in {"http", "https"}:
        return False
    if not parsed.netloc:
        return False
    return True


def is_valid_payment_qr_url(value: str) -> bool:
    raw = str(value or "").strip()
    if not raw:
        return False

    if is_valid_http_url(raw):
        return True

    try:
        parsed = urlparse(raw)
    except Exception:
        return False

    if parsed.scheme or parsed.netloc:
        return False

    path = unquote(parsed.path or "")
    if not path.startswith("/assets/uploads/"):
        return False

    parts = [segment for segment in path.split("/") if segment]
    if any(segment in {".", ".."} for segment in parts):
        return False

    return bool(re.fullmatch(r"/assets/uploads/[A-Za-z0-9/_\.-]+", path))


def load_vip_payment_qr_map() -> dict:
    row = _db_fetchone("SELECT value FROM settings WHERE key = %s", ("vip_payment_qr",))
    data = row.get("value") if row else {}
    if not isinstance(data, dict):
        data = {}
    clean = {}
    for key in ("yape", "binance", "crypto"):
        value = data.get(key)
        if isinstance(value, str) and value.strip():
            clean[key] = value.strip()
    return clean


def save_vip_payment_qr_map(data: dict) -> dict:
    clean = {}
    for key in ("yape", "binance", "crypto"):
        value = data.get(key)
        if isinstance(value, str) and value.strip():
            clean[key] = value.strip()
    _db_execute(
        """
        INSERT INTO settings (key, value, updated_at)
        VALUES (%s, %s::jsonb, NOW())
        ON CONFLICT (key) DO UPDATE
        SET value = EXCLUDED.value, updated_at = NOW();
        """,
        ("vip_payment_qr", json.dumps(clean, ensure_ascii=False)),
    )
    return clean


def infer_extension(filename: str, content_type: str) -> str:
    ctype = (content_type or "").lower().strip()
    mapped = CONTENT_TYPE_EXTENSION_MAP.get(ctype)
    if mapped:
        return mapped

    ext = Path(filename or "").suffix.lower()
    if ext and ext in set(CONTENT_TYPE_EXTENSION_MAP.values()):
        return ext

    guessed = mimetypes.guess_extension(ctype) or ""
    if re.match(r"^\.[a-z0-9]{2,5}$", guessed):
        return guessed
    return ".bin"


async def persist_upload_to_temp(upload: UploadFile, max_bytes: int) -> tuple[Path, int]:
    tmp_path = TMP_UPLOADS_DIR / f"tmp-{uuid.uuid4().hex}"
    total = 0

    with tmp_path.open("wb") as dst:
        while True:
            chunk = await upload.read(CHUNK_SIZE)
            if not chunk:
                break
            total += len(chunk)
            if total > max_bytes:
                dst.close()
                tmp_path.unlink(missing_ok=True)
                raise HTTPException(status_code=413, detail="File exceeds max size")
            dst.write(chunk)

    if total <= 0:
        tmp_path.unlink(missing_ok=True)
        raise HTTPException(status_code=400, detail="Empty file")

    return tmp_path, total


async def upload_to_supabase_storage(*, temp_path: Path, object_key: str, content_type: str) -> str:
    encoded_key = quote(object_key, safe="/_-")
    upload_url = f"{SUPABASE_URL}/storage/v1/object/{SUPABASE_BUCKET}/{encoded_key}"
    headers = {
        "Authorization": f"Bearer {SUPABASE_SERVICE_ROLE_KEY}",
        "apikey": SUPABASE_SERVICE_ROLE_KEY,
        "x-upsert": "true",
        "content-type": content_type,
    }

    async with httpx.AsyncClient(timeout=None) as client:
        with temp_path.open("rb") as src:
            response = await client.post(upload_url, headers=headers, content=src)

    if response.status_code not in (200, 201):
        raise HTTPException(status_code=502, detail=f"Storage upload failed: {response.status_code}")

    return f"{SUPABASE_URL}/storage/v1/object/public/{SUPABASE_BUCKET}/{encoded_key}"


def move_to_local_storage(*, temp_path: Path, object_name: str, media_kind: str) -> str:
    """
    Move uploaded file to local storage. In serverless environments (Vercel),
    this fails gracefully and returns the MEDIA_PUBLIC_BASE_URL if configured.
    """
    target_root = IMAGES_DIR if media_kind == "image" else VIDEOS_DIR
    final_path = target_root / object_name
    
    try:
        # Try to create directory and move file locally
        final_path.parent.mkdir(parents=True, exist_ok=True)
        temp_path.replace(final_path)
        relative = final_path.relative_to(ASSETS_DIR).as_posix()
        if MEDIA_PUBLIC_BASE_URL:
            return f"{MEDIA_PUBLIC_BASE_URL}/assets/{relative}"
        return f"/assets/{relative}"
    except (OSError, PermissionError) as e:
        # In serverless environments (Vercel), local storage is read-only
        # Return a placeholder URL based on MEDIA_PUBLIC_BASE_URL
        if MEDIA_PUBLIC_BASE_URL:
            # Return a URL that references the external storage
            return f"{MEDIA_PUBLIC_BASE_URL}/{media_kind}s/{object_name}"
        # If no external URL is configured, raise an error
        raise HTTPException(
            status_code=503,
            detail="Local storage not available and no MEDIA_PUBLIC_BASE_URL configured. "
                   "Please set MEDIA_PUBLIC_BASE_URL or HOSTGATOR_BASE_URL environment variable."
        )


@app.on_event("startup")
def startup() -> None:
    if not _is_postgres_enabled():
        print("[startup] warning: DATABASE_URL missing or postgres driver unavailable; DB endpoints will return 503")
        return
    ensure_app_tables()
    ensure_media_table()
    if not _load_users_store():
        _save_users_store([])
    if not _load_wallets_store():
        _save_wallets_store({})
    if not _load_gifts_store():
        _save_gifts_store([])
    if not _db_fetchone("SELECT key FROM settings WHERE key = %s", ("global",)):
        _save_settings_store(_default_settings_store())


# Mount static directories - Vercel read-only safe implementation
_css_dir = BASE_DIR / "css"
_js_dir = BASE_DIR / "js"
_audio_dir = ASSETS_DIR / "audio"
_recursos_dir = ASSETS_DIR / "recursos"

# Efficient loop-based mounting with exists() and is_dir() checks
for path, name in [(_css_dir, "css"), (_js_dir, "js"), (ASSETS_DIR, "assets"), (_audio_dir, "audio"), (_recursos_dir, "recursos")]:
    if path.exists() and path.is_dir():
        try:
            app.mount(f"/{name}", StaticFiles(directory=str(path)), name=name)
        except Exception:
            pass


@app.get("/favicon.ico")
async def favicon():
    """Return 204 No Content for favicon requests to prevent 500 errors. 
    Favicon is optional and should not crash the application."""
    return Response(status_code=204)


@app.get("/")
async def read_root():
    return FileResponse(str(BASE_DIR / "index.html"))


@app.get("/admin.html")
async def read_admin(request: Request):
    if not _has_admin_portal_access(request):
        return RedirectResponse(url="/", status_code=303)
    return FileResponse(str(BASE_DIR / "admin.html"))


@app.get("/foro.html")
async def read_foro(request: Request):
    if not get_user_session(request) and not get_admin_session(request):
        return RedirectResponse(url="/", status_code=303)
    return FileResponse(str(BASE_DIR / "foro.html"))


@app.get("/api/status")
def server_status():
    users_count = 0
    gifts_count = 0
    wallets_count = 0
    if _is_postgres_enabled():
        try:
            users_count = len(_load_users_store())
            gifts_count = len(_load_gifts_store())
            wallets_count = len(_load_wallets_store())
        except Exception:
            users_count = 0
            gifts_count = 0
            wallets_count = 0
    return {
        "message": "Servidor MB CMD Funcionando",
        "storage_mode": "supabase" if _is_supabase_enabled() else "local",
        "postgres_enabled": _is_postgres_enabled(),
        "database_required_for_persistence": True,
        "admin_api_key_configured": bool(ADMIN_API_KEY),
        "admin_user_configured": bool(ADMIN_USERNAME),
        "admin_password_sha256_enabled": bool(ADMIN_PASSWORD_SHA256),
        "admin_session_ttl_seconds": ADMIN_SESSION_TTL_SECONDS,
        "admin_cookie_secure": ADMIN_SESSION_COOKIE_SECURE,
        "user_session_ttl_seconds": USER_SESSION_TTL_SECONDS,
        "user_cookie_secure": USER_SESSION_COOKIE_SECURE,
        "max_image_mb": MAX_IMAGE_MB,
        "max_video_mb": MAX_VIDEO_MB,
        "cors_allow_origins": _cors_origins,
        "cors_allow_credentials": True,
        "trusted_hosts": _trusted_hosts if _trusted_hosts else ["127.0.0.1", "localhost"],
        "rate_limit_window_seconds": RATE_LIMIT_WINDOW_SECONDS,
        "rate_limit_requests": RATE_LIMIT_REQUESTS_PER_WINDOW,
        "login_lock_window_seconds": LOGIN_LOCK_WINDOW_SECONDS,
        "login_max_failed_attempts": LOGIN_MAX_FAILED_ATTEMPTS,
        "user_login_lock_window_seconds": USER_LOGIN_LOCK_WINDOW_SECONDS,
        "user_login_max_failed_attempts": USER_LOGIN_MAX_FAILED_ATTEMPTS,
        "force_https": FORCE_HTTPS,
        "wallet_max_single_spend": WALLET_MAX_SINGLE_SPEND,
        "users_count": users_count,
        "gifts_count": gifts_count,
        "wallets_count": wallets_count,
    }

@app.get("/api/admin/transactions")
def admin_list_transactions(request: Request, limit: int = 100, kind: str = ""):
    require_admin_access(request, require_csrf=True)
    if limit <= 0:
        limit = 100
    limit = min(limit, 1000)
    entries: list[dict] = []
    with _tx_log_lock:
        snapshot = list(_tx_log_entries)
    for item in reversed(snapshot):
        if len(entries) >= limit:
            break
        if kind and str(item.get("type", "")).lower() != str(kind).lower():
            continue
        entries.append(dict(item))
    return {"ok": True, "entries": entries}

@app.get("/api/admin/reconcile")
def admin_reconcile_wallets(request: Request):
    require_admin_access(request, require_csrf=True)
    actual = _load_wallets_store()
    expected_map: dict[str, int] = defaultdict(int)
    processed = 0
    with _tx_log_lock:
        snapshot = list(_tx_log_entries)
    for item in snapshot:
        t = str(item.get("type", "")).lower()
        if not item.get("ok", False):
            continue
        username = _normalize_username(str(item.get("username", "")))
        if not username:
            continue
        delta = 0
        if t in {"admin_credit", "gift_credit", "daily_credit"}:
            delta = max(0, int(round(float(item.get("amount", 0)))))
        elif t in {"user_spend"}:
            delta = -max(0, int(round(float(item.get("amount", 0)))))
        else:
            continue
        expected_map[username] += delta
        processed += 1
    discrepancies = []
    for user, expected in expected_map.items():
        actual_balance = max(0, int(actual.get(user, 0)))
        if actual_balance != expected:
            discrepancies.append({
                "username": user,
                "expected_balance": expected,
                "actual_balance": actual_balance,
                "delta": actual_balance - expected,
            })
    return {
        "ok": True,
        "processed_log_entries": processed,
        "expected": expected_map,
        "actual": actual,
        "discrepancies": discrepancies,
    }


@app.post("/api/auth/admin/login")
def admin_login(request: Request, response: Response, payload: dict = Body(...)):
    apply_rate_limit(request, "admin_login")
    username = str(payload.get("username", "")).strip()
    password = str(payload.get("password", ""))

    if not username or not password:
        raise HTTPException(status_code=400, detail="Username and password are required")

    if is_login_temporarily_blocked(request, username):
        raise HTTPException(status_code=429, detail="Too many failed login attempts. Try again later")

    if not hmac.compare_digest(username.lower(), ADMIN_USERNAME.lower()):
        record_login_failure(request, username)
        raise HTTPException(status_code=401, detail="Invalid admin credentials")
    if not _is_valid_admin_password(password):
        record_login_failure(request, username)
        raise HTTPException(status_code=401, detail="Invalid admin credentials")

    clear_login_failures(request, username)

    session_id = create_admin_session(username=username)
    session_data = _admin_sessions.get(session_id, {})
    response.set_cookie(
        key=ADMIN_SESSION_COOKIE_NAME,
        value=session_id,
        max_age=ADMIN_SESSION_TTL_SECONDS,
        httponly=True,
        secure=ADMIN_SESSION_COOKIE_SECURE,
        samesite=ADMIN_SESSION_COOKIE_SAMESITE,
        path="/",
    )
    return {
        "ok": True,
        "role": "admin",
        "username": username,
        "csrf_token": str(session_data.get("csrf_token", "")),
        "expires_in_seconds": ADMIN_SESSION_TTL_SECONDS,
    }


@app.get("/api/auth/session")
def admin_session_status(request: Request):
    if _has_valid_admin_api_key(request):
        return {"ok": True, "authenticated": True, "role": "admin", "auth_via": "api_key"}

    admin_session = get_admin_session(request)
    if admin_session:
        return {
            "ok": True,
            "authenticated": True,
            "role": "admin",
            "auth_via": "session_cookie",
            "username": admin_session["username"],
            "csrf_token": admin_session.get("csrf_token", ""),
        }

    privileged = _get_privileged_user_session(request)
    if privileged:
        session = privileged.get("session", {})
        user = privileged.get("user", {})
        role = str(privileged.get("role", "owner"))
        return {
            "ok": True,
            "authenticated": True,
            "role": role,
            "auth_via": "user_session",
            "username": str(user.get("username", session.get("username", ""))),
            "csrf_token": session.get("csrf_token", ""),
        }

    return {"ok": True, "authenticated": False, "role": None}


@app.post("/api/auth/logout")
def admin_logout(request: Request, response: Response):
    clear_user_session = False
    if not _has_valid_admin_api_key(request):
        admin_session = get_admin_session(request)
        if admin_session:
            csrf_token = _extract_admin_csrf_token(request)
            expected = str(admin_session.get("csrf_token", ""))
            if not csrf_token or not expected or not hmac.compare_digest(csrf_token, expected):
                raise HTTPException(status_code=403, detail="Invalid CSRF token")
        else:
            privileged = _get_privileged_user_session(request)
            if privileged:
                user_session = privileged.get("session", {})
                csrf_token = _extract_admin_csrf_token(request)
                expected = str(user_session.get("csrf_token", ""))
                if not csrf_token or not expected or not hmac.compare_digest(csrf_token, expected):
                    raise HTTPException(status_code=403, detail="Invalid CSRF token")
                user_session_id = str(user_session.get("id", "")).strip()
                if user_session_id:
                    _user_sessions.pop(user_session_id, None)
                clear_user_session = True

    session_id = (request.cookies.get(ADMIN_SESSION_COOKIE_NAME) or "").strip()
    if session_id:
        _admin_sessions.pop(session_id, None)
    response.delete_cookie(
        key=ADMIN_SESSION_COOKIE_NAME,
        path="/",
        secure=ADMIN_SESSION_COOKIE_SECURE,
        samesite=ADMIN_SESSION_COOKIE_SAMESITE,
    )
    if clear_user_session:
        _clear_user_session_cookie(response)
    return {"ok": True}


@app.post("/api/auth/user/register")
def user_register(request: Request, response: Response, payload: dict = Body(...)):
    apply_rate_limit(request, "user_register")

    raw_username = str(payload.get("username", "")).strip()
    password = str(payload.get("password", ""))
    bind_device = bool(payload.get("bind_device", True))
    device_id = str(payload.get("device_id", "")).strip() or None

    if not raw_username or not password:
        raise HTTPException(status_code=400, detail="Username and password are required")
    if not _is_valid_username(raw_username):
        raise HTTPException(status_code=400, detail="Invalid username format")
    if _normalize_username(raw_username) == _normalize_username(ADMIN_USERNAME):
        raise HTTPException(status_code=400, detail="Username unavailable")
    if len(password) < 6:
        raise HTTPException(status_code=400, detail="Password must be at least 6 characters")

    users = _load_users_store()
    if _find_user_by_username(users, raw_username):
        raise HTTPException(status_code=409, detail="Username already exists")

    now_iso = datetime.now(timezone.utc).isoformat()
    user = {
        "username": raw_username,
        "username_lower": _normalize_username(raw_username),
        "password_hash": _password_context.hash(password),
        "role": "user",
        "plan": "free",
        "status": "Activo",
        "isVip": False,
        "expiryDate": None,
        "deviceLock": device_id if (bind_device and device_id) else None,
        "createdAt": now_iso,
        "updatedAt": now_iso,
    }
    users.append(user)
    _save_users_store(users)

    session_id = create_user_session(user["username_lower"])
    _set_user_session_cookie(response, session_id)
    session = _user_sessions.get(session_id, {})

    return {
        "ok": True,
        "authenticated": True,
        "role": "user",
        "csrf_token": str(session.get("csrf_token", "")),
        "user": _serialize_user_public(user),
        "expires_in_seconds": USER_SESSION_TTL_SECONDS,
    }


@app.post("/api/auth/user/login")
def user_login(request: Request, response: Response, payload: dict = Body(...)):
    apply_rate_limit(request, "user_login")

    raw_username = str(payload.get("username", "")).strip()
    password = str(payload.get("password", ""))
    bind_device = bool(payload.get("bind_device", True))
    device_id = str(payload.get("device_id", "")).strip() or None

    if not raw_username or not password:
        raise HTTPException(status_code=400, detail="Username and password are required")

    if user_login_temporarily_blocked(request, raw_username):
        raise HTTPException(status_code=429, detail="Too many failed login attempts. Try again later")

    users = _load_users_store()
    user = _find_user_by_username(users, raw_username)
    if not user:
        record_user_login_failure(request, raw_username)
        raise HTTPException(status_code=401, detail="Invalid credentials")

    try:
        valid_password = _password_context.verify(password, str(user.get("password_hash", "")))
    except Exception:
        valid_password = False
    if not valid_password:
        record_user_login_failure(request, raw_username)
        raise HTTPException(status_code=401, detail="Invalid credentials")

    if _user_is_expired(user):
        raise HTTPException(status_code=403, detail="User access expired")

    if user.get("deviceLock"):
        if not device_id:
            raise HTTPException(status_code=400, detail="Device identifier is required for this account")
        if str(user.get("deviceLock")) != device_id:
            raise HTTPException(status_code=403, detail="Unauthorized device")
    elif bind_device and device_id:
        user["deviceLock"] = device_id
        user["updatedAt"] = datetime.now(timezone.utc).isoformat()
        _save_users_store(users)

    clear_user_login_failures(request, raw_username)

    session_id = create_user_session(str(user.get("username_lower", raw_username)))
    _set_user_session_cookie(response, session_id)
    session = _user_sessions.get(session_id, {})

    return {
        "ok": True,
        "authenticated": True,
        "role": str(user.get("role", "user")),
        "csrf_token": str(session.get("csrf_token", "")),
        "user": _serialize_user_public(user),
        "expires_in_seconds": USER_SESSION_TTL_SECONDS,
    }


@app.get("/api/auth/user/session")
def user_session_status(request: Request):
    session = get_user_session(request)
    if not session:
        return {"ok": True, "authenticated": False, "role": None}

    users = _load_users_store()
    user = _find_user_by_username(users, str(session.get("username", "")))
    if not user:
        _user_sessions.pop(str(session.get("id", "")), None)
        return {"ok": True, "authenticated": False, "role": None}

    if _user_is_expired(user):
        return {"ok": True, "authenticated": False, "role": None, "expired": True}

    public_user = _serialize_user_public(user)
    return {
        "ok": True,
        "authenticated": True,
        "role": public_user.get("role", "user"),
        "csrf_token": session.get("csrf_token", ""),
        "user": public_user,
    }


@app.post("/api/auth/user/logout")
def user_logout(request: Request, response: Response):
    session = get_user_session(request)
    if session:
        csrf_token = (request.headers.get(USER_CSRF_HEADER_NAME) or "").strip()
        expected = str(session.get("csrf_token", ""))
        if not csrf_token or not expected or not hmac.compare_digest(csrf_token, expected):
            raise HTTPException(status_code=403, detail="Invalid CSRF token")
        _user_sessions.pop(str(session.get("id", "")), None)
    _clear_user_session_cookie(response)
    return {"ok": True}


@app.get("/api/admin/users")
def admin_list_users(request: Request):
    require_admin_access(request, require_csrf=True)
    users = _load_users_store()
    users_sorted = sorted(users, key=lambda u: str(u.get("username_lower", "")))
    return {"ok": True, "users": [_serialize_user_public(u) for u in users_sorted]}


@app.post("/api/admin/users")
def admin_create_user(request: Request, payload: dict = Body(...)):
    require_admin_access(request, require_csrf=True)
    apply_rate_limit(request, "admin_create_user")

    raw_username = str(payload.get("username", "")).strip()
    password = str(payload.get("password", "")).strip()
    role = _normalize_user_role(payload.get("role", "user"))
    status = str(payload.get("status", "Activo")).strip() or "Activo"

    if not raw_username or not password:
        raise HTTPException(status_code=400, detail="Username and password are required")
    if not _is_valid_username(raw_username):
        raise HTTPException(status_code=400, detail="Invalid username format")
    if len(password) < 6:
        raise HTTPException(status_code=400, detail="Password must be at least 6 characters")

    users = _load_users_store()
    if _find_user_by_username(users, raw_username):
        raise HTTPException(status_code=409, detail="Username already exists")

    now_iso = datetime.now(timezone.utc).isoformat()
    plan = str(payload.get("plan", "free")).strip().lower() or "free"
    if plan not in {"free", "vip", "pro", "elite", "black", "god"}:
        plan = "free"
    is_vip = bool(payload.get("isVip", plan in {"vip", "pro", "elite", "black", "god"}))

    user = {
        "username": raw_username,
        "username_lower": _normalize_username(raw_username),
        "password_hash": _password_context.hash(password),
        "role": role,
        "plan": plan,
        "status": "VIP" if is_vip else status,
        "isVip": is_vip,
        "expiryDate": str(payload.get("expiryDate", "")).strip() or None,
        "deviceLock": None,
        "dailyCreditsAt": None,
        "createdAt": now_iso,
        "updatedAt": now_iso,
    }
    users.append(user)
    _save_users_store(users)
    return {"ok": True, "user": _serialize_user_public(user)}


@app.patch("/api/admin/users/{username}")
def admin_update_user(request: Request, username: str, payload: dict = Body(...)):
    require_admin_access(request, require_csrf=True)

    users = _load_users_store()
    user = _find_user_by_username(users, username)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    role = payload.get("role")
    if role is not None:
        role_value = str(role).strip().lower()
        if role_value not in ALLOWED_USER_ROLES:
            raise HTTPException(status_code=400, detail="Invalid role")
        user["role"] = role_value

    plan = payload.get("plan")
    if plan is not None:
        plan_value = str(plan).strip().lower()
        if plan_value not in {"free", "vip", "pro", "elite", "black", "god"}:
            raise HTTPException(status_code=400, detail="Invalid plan")
        user["plan"] = plan_value
        if plan_value in {"vip", "pro", "elite", "black", "god"}:
            user["isVip"] = True
            user["status"] = "VIP"
        elif not bool(user.get("isVip", False)):
            user["status"] = "Activo"

    if "isVip" in payload:
        is_vip = bool(payload.get("isVip"))
        user["isVip"] = is_vip
        user["status"] = "VIP" if is_vip else "Activo"
        if is_vip and str(user.get("plan", "free")).lower() == "free":
            user["plan"] = "vip"

    expiry_date = payload.get("expiryDate")
    if expiry_date is not None:
        expiry_value = str(expiry_date).strip()
        if not expiry_value:
            user["expiryDate"] = None
        elif not re.fullmatch(r"\d{4}-\d{2}-\d{2}", expiry_value):
            raise HTTPException(status_code=400, detail="Invalid expiry date format")
        else:
            user["expiryDate"] = expiry_value

    if payload.get("resetDevice") is True:
        user["deviceLock"] = None

    user["updatedAt"] = datetime.now(timezone.utc).isoformat()
    _save_users_store(users)
    return {"ok": True, "user": _serialize_user_public(user)}


@app.delete("/api/admin/users/{username}")
def admin_delete_user(request: Request, username: str):
    require_admin_access(request, require_csrf=True)

    users = _load_users_store()
    normalized = _normalize_username(username)
    next_users = [u for u in users if str(u.get("username_lower", "")) != normalized]
    if len(next_users) == len(users):
        raise HTTPException(status_code=404, detail="User not found")

    _save_users_store(next_users)

    for session_id, session_data in list(_user_sessions.items()):
        if str(session_data.get("username", "")) == normalized:
            _user_sessions.pop(session_id, None)

    return {"ok": True}


@app.post("/api/admin/users/{username}/credits")
def admin_add_user_credits(request: Request, username: str, payload: dict = Body(...)):
    require_admin_access(request, require_csrf=True)
    apply_rate_limit(request, "admin_user_credits")

    amount_raw = payload.get("amount")
    try:
        amount = int(round(float(amount_raw)))
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid amount")

    if amount <= 0:
        raise HTTPException(status_code=400, detail="Amount must be greater than 0")
    if amount > 1_000_000:
        raise HTTPException(status_code=400, detail="Amount too large")

    users = _load_users_store()
    user = _find_user_by_username(users, username)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    username_lower = str(user.get("username_lower", user.get("username", "")))
    event_id = secrets.token_hex(12)
    try:
        before, after = _wallet_apply_delta(username_lower, amount, require_sufficient=False)
        _append_transaction_log({
            "type": "admin_credit",
            "event_id": event_id,
            "username": username_lower,
            "amount": amount,
            "balance_before": before,
            "balance_after": after,
            "source": "admin_panel",
            "ok": True,
        })
        return {
            "ok": True,
            "username": user.get("username"),
            "delta": amount,
            "balance": after,
        }
    except Exception as e:
        _append_transaction_log({
            "type": "admin_credit",
            "event_id": event_id,
            "username": username_lower,
            "amount": amount,
            "error": str(e),
            "ok": False,
        })
        _notify_alert("credit_failure", {"event_id": event_id, "username": username_lower, "amount": amount, "error": str(e)})
        raise


@app.get("/api/admin/gifts")
def admin_list_gifts(request: Request):
    require_admin_access(request, require_csrf=True)
    gifts = _load_gifts_store()
    gifts_sorted = sorted(gifts, key=lambda g: str(g.get("createdAt", "")), reverse=True)
    return {"ok": True, "gifts": gifts_sorted}


@app.post("/api/admin/gifts")
def admin_create_gift(request: Request, payload: dict = Body(...)):
    require_admin_access(request, require_csrf=True)
    apply_rate_limit(request, "admin_create_gift")

    kind = str(payload.get("kind", "vip_subscription")).strip().lower()
    if kind not in {"credits", "vip_subscription"}:
        raise HTTPException(status_code=400, detail="Invalid gift type")

    if kind == "credits":
        try:
            credits = int(round(float(payload.get("credits", 0))))
        except Exception:
            credits = 0
        if credits <= 0:
            raise HTTPException(status_code=400, detail="Credits must be greater than 0")
        if credits > 5_000_000:
            raise HTTPException(status_code=400, detail="Credits amount too large")
        plan = "vip"
        days = 0
    else:
        plan = str(payload.get("plan", "vip")).strip().lower()
        if plan not in {"vip", "pro", "elite", "black", "god"}:
            raise HTTPException(status_code=400, detail="Invalid VIP plan")
        try:
            days = int(round(float(payload.get("days", 30))))
        except Exception:
            days = 30
        if days <= 0 or days > 3650:
            raise HTTPException(status_code=400, detail="Invalid subscription days")
        credits = 0

    gifts = _load_gifts_store()
    requested_code = _normalize_gift_code(payload.get("code", ""))
    if requested_code:
        if not re.fullmatch(r"[A-Z0-9]{3,4}-[A-Z0-9]{4}-[A-Z0-9]{4}", requested_code):
            raise HTTPException(status_code=400, detail="Invalid gift code format")
        if _find_gift_by_code(gifts, requested_code):
            raise HTTPException(status_code=409, detail="Gift code already exists")
        code = requested_code
    else:
        code = _generate_unique_gift_code(kind, gifts)

    entry = _normalize_gift_entry(
        {
            "code": code,
            "kind": kind,
            "plan": plan,
            "days": days,
            "credits": credits,
            "status": "active",
            "createdAt": datetime.now(timezone.utc).isoformat(),
            "usedAt": "",
            "usedBy": "",
        }
    )
    if not entry:
        raise HTTPException(status_code=400, detail="Invalid gift payload")

    gifts.append(entry)
    _save_gifts_store(gifts)
    return {"ok": True, "gift": entry}


@app.patch("/api/admin/gifts/{code}")
def admin_update_gift(request: Request, code: str, payload: dict = Body(...)):
    require_admin_access(request, require_csrf=True)
    apply_rate_limit(request, "admin_update_gift")

    status_raw = str(payload.get("status", "")).strip().lower()
    if status_raw not in {"active", "revoked"}:
        raise HTTPException(status_code=400, detail="Invalid gift status")

    gifts = _load_gifts_store()
    gift = _find_gift_by_code(gifts, code)
    if not gift:
        raise HTTPException(status_code=404, detail="Gift not found")
    if str(gift.get("status", "")).lower() == "used":
        raise HTTPException(status_code=409, detail="Used gift cannot be modified")

    gift["status"] = status_raw
    _save_gifts_store(gifts)
    return {"ok": True, "gift": gift}


@app.delete("/api/admin/gifts/{code}")
def admin_delete_gift(request: Request, code: str):
    require_admin_access(request, require_csrf=True)
    gifts = _load_gifts_store()
    normalized_code = _normalize_gift_code(code)
    next_gifts = [g for g in gifts if str(g.get("code", "")).upper() != normalized_code]
    if len(next_gifts) == len(gifts):
        raise HTTPException(status_code=404, detail="Gift not found")
    _save_gifts_store(next_gifts)
    return {"ok": True}


def _resolve_user_session_user(request: Request) -> tuple[dict, dict]:
    session = require_user_access(request)
    users = _load_users_store()
    user = _find_user_by_username(users, str(session.get("username", "")))
    if not user:
        _user_sessions.pop(str(session.get("id", "")), None)
        raise HTTPException(status_code=401, detail="User session not found")
    if _user_is_expired(user):
        raise HTTPException(status_code=403, detail="User access expired")
    return session, user


@app.get("/api/user/wallet")
def user_wallet_status(request: Request):
    _session, user = _resolve_user_session_user(request)
    username = str(user.get("username_lower", user.get("username", "")))
    balance = _get_wallet_balance(username)
    return {"ok": True, "balance": balance}


@app.post("/api/user/wallet/daily-bonus")
def user_wallet_daily_bonus(request: Request):
    require_user_access(request, require_csrf=True)
    apply_rate_limit(request, "user_wallet_daily_bonus")
    session = get_user_session(request)
    if not session:
        raise HTTPException(status_code=401, detail="Unauthorized")
    users = _load_users_store()
    user = _find_user_by_username(users, str(session.get("username", "")))
    if not user:
        _user_sessions.pop(str(session.get("id", "")), None)
        raise HTTPException(status_code=401, detail="User session not found")
    if _user_is_expired(user):
        raise HTTPException(status_code=403, detail="User access expired")

    now = datetime.now(timezone.utc)
    last_claim = _parse_iso_datetime(str(user.get("dailyCreditsAt", "")).strip())
    if last_claim and (now - last_claim).total_seconds() < DAILY_BONUS_INTERVAL_SECONDS:
        next_available = last_claim + timedelta(seconds=DAILY_BONUS_INTERVAL_SECONDS)
        return {
            "ok": True,
            "granted": False,
            "balance": _get_wallet_balance(str(user.get("username_lower", user.get("username", "")))),
            "next_available_at": next_available.isoformat(),
        }

    username = str(user.get("username_lower", user.get("username", "")))
    event_id = secrets.token_hex(12)
    before, after = _wallet_apply_delta(username, DAILY_BONUS_CREDITS, require_sufficient=False)
    user["dailyCreditsAt"] = now.isoformat()
    user["updatedAt"] = now.isoformat()
    _save_users_store(users)
    _append_transaction_log({
        "type": "daily_credit",
        "event_id": event_id,
        "username": username,
        "amount": DAILY_BONUS_CREDITS,
        "balance_before": before,
        "balance_after": after,
        "source": "daily_bonus",
        "ok": True,
    })
    return {
        "ok": True,
        "granted": True,
        "delta": DAILY_BONUS_CREDITS,
        "balance_before": before,
        "balance_after": after,
        "next_available_at": (now + timedelta(seconds=DAILY_BONUS_INTERVAL_SECONDS)).isoformat(),
    }


@app.post("/api/user/wallet/spend")
def user_wallet_spend(request: Request, payload: dict = Body(...)):
    require_user_access(request, require_csrf=True)
    apply_rate_limit(request, "user_wallet_spend")
    _session, user = _resolve_user_session_user(request)

    amount_raw = payload.get("amount")
    reason = str(payload.get("reason", "purchase")).strip().lower()
    metadata = payload.get("metadata", {})

    try:
        amount = int(round(float(amount_raw)))
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid amount")
    if amount <= 0:
        raise HTTPException(status_code=400, detail="Amount must be greater than 0")
    if amount > WALLET_MAX_SINGLE_SPEND:
        raise HTTPException(status_code=400, detail="Amount exceeds allowed limit")
    if reason not in {"purchase", "manual_spend"}:
        raise HTTPException(status_code=400, detail="Invalid spend reason")
    if metadata is not None and not isinstance(metadata, dict):
        raise HTTPException(status_code=400, detail="Invalid metadata format")

    username = str(user.get("username_lower", user.get("username", "")))
    event_id = secrets.token_hex(12)
    before, after = _wallet_apply_delta(username, -amount, require_sufficient=True)
    _append_transaction_log({
        "type": "user_spend",
        "event_id": event_id,
        "username": username,
        "amount": amount,
        "reason": reason,
        "balance_before": before,
        "balance_after": after,
        "source": "user_spend",
        "ok": True,
        "metadata": metadata if isinstance(metadata, dict) else {},
    })
    return {
        "ok": True,
        "reason": reason,
        "amount": amount,
        "balance_before": before,
        "balance_after": after,
    }


@app.get("/api/user/gifts/history")
def user_gifts_history(request: Request):
    _session, user = _resolve_user_session_user(request)
    username = str(user.get("username_lower", user.get("username", "")))
    gifts = _load_gifts_store()
    history = [
        gift
        for gift in gifts
        if str(gift.get("status", "")).lower() == "used"
        and _normalize_username(gift.get("usedBy", "")) == username
    ]
    history_sorted = sorted(history, key=lambda g: str(g.get("usedAt", "")), reverse=True)
    return {"ok": True, "history": history_sorted}


@app.post("/api/user/gifts/redeem")
def user_redeem_gift(request: Request, payload: dict = Body(...)):
    require_user_access(request, require_csrf=True)
    apply_rate_limit(request, "user_gift_redeem")

    _session, user = _resolve_user_session_user(request)
    code = _normalize_gift_code(payload.get("code", ""))
    if not code:
        raise HTTPException(status_code=400, detail="Gift code is required")

    gifts = _load_gifts_store()
    gift = _find_gift_by_code(gifts, code)
    if not gift:
        raise HTTPException(status_code=404, detail="Gift code not found")

    status = str(gift.get("status", "")).lower()
    if status == "revoked":
        raise HTTPException(status_code=409, detail="Gift code is revoked")
    if status == "used":
        used_by = _normalize_username(gift.get("usedBy", ""))
        current_user = _normalize_username(user.get("username_lower", user.get("username", "")))
        if used_by == current_user:
            raise HTTPException(status_code=409, detail="Gift code already redeemed by this account")
        raise HTTPException(status_code=409, detail="Gift code already redeemed")

    kind = str(gift.get("kind", "")).lower()
    username_lower = str(user.get("username_lower", user.get("username", "")))
    wallet_balance = _get_wallet_balance(username_lower)
    redeemed_detail: dict[str, object] = {"kind": kind}

    if kind == "credits":
        credits = max(0, int(round(float(gift.get("credits", 0) or 0))))
        if credits <= 0:
            raise HTTPException(status_code=400, detail="Invalid credit gift")
        before, after = _wallet_apply_delta(username_lower, credits, require_sufficient=False)
        wallet_balance = after
        _append_transaction_log({
            "type": "gift_credit",
            "event_id": secrets.token_hex(12),
            "username": username_lower,
            "amount": credits,
            "balance_before": before,
            "balance_after": after,
            "source": "gift_redeem",
            "ok": True,
            "gift_code": code,
        })
        redeemed_detail["credits"] = credits
    else:
        plan = str(gift.get("plan", "vip")).lower()
        days = max(1, int(round(float(gift.get("days", 30) or 30))))
        users = _load_users_store()
        persisted_user = _find_user_by_username(users, username_lower)
        if not persisted_user:
            raise HTTPException(status_code=404, detail="User not found")
        expiry = _apply_vip_subscription(persisted_user, plan, days)
        _save_users_store(users)
        user = persisted_user
        redeemed_detail["plan"] = plan
        redeemed_detail["days"] = days
        redeemed_detail["expiryDate"] = expiry

    gift["status"] = "used"
    gift["usedBy"] = username_lower
    gift["usedAt"] = datetime.now(timezone.utc).isoformat()
    _save_gifts_store(gifts)

    return {
        "ok": True,
        "gift": gift,
        "wallet_balance": wallet_balance,
        "user": _serialize_user_public(user),
        "redeemed": redeemed_detail,
    }


@app.get("/api/public/announcement")
def public_announcement():
    settings = _load_settings_store()
    return {"ok": True, "message": str(settings.get("announcement", ""))}


@app.put("/api/admin/announcement")
def admin_set_announcement(request: Request, payload: dict = Body(...)):
    require_admin_access(request, require_csrf=True)
    message = str(payload.get("message", "")).strip()
    if len(message) > 500:
        raise HTTPException(status_code=400, detail="Announcement is too long")
    settings = _load_settings_store()
    settings["announcement"] = message
    saved = _save_settings_store(settings)
    return {"ok": True, "message": str(saved.get("announcement", ""))}


@app.delete("/api/admin/announcement")
def admin_clear_announcement(request: Request):
    require_admin_access(request, require_csrf=True)
    settings = _load_settings_store()
    settings["announcement"] = ""
    _save_settings_store(settings)
    return {"ok": True}


@app.get("/api/public/contact")
def public_contact_channels():
    settings = _load_settings_store()
    contact = settings.get("contact", {})
    if not isinstance(contact, dict):
        contact = {}
    return {
        "ok": True,
        "contact": {
            "whatsapp": str(contact.get("whatsapp", "")).strip(),
            "telegram": str(contact.get("telegram", "")).strip(),
        },
    }


@app.put("/api/admin/contact")
def admin_set_contact_channels(request: Request, payload: dict = Body(...)):
    require_admin_access(request, require_csrf=True)
    whatsapp = str(payload.get("whatsapp", "")).strip()
    telegram = str(payload.get("telegram", "")).strip()
    if len(whatsapp) > 120 or len(telegram) > 120:
        raise HTTPException(status_code=400, detail="Contact fields are too long")

    settings = _load_settings_store()
    contact = settings.get("contact", {})
    if not isinstance(contact, dict):
        contact = {}
    contact["whatsapp"] = whatsapp
    contact["telegram"] = telegram
    settings["contact"] = contact
    saved = _save_settings_store(settings)
    return {"ok": True, "contact": saved.get("contact", {})}


@app.get("/api/vip/payment-qr")
def get_vip_payment_qr():
    return {"ok": True, "data": load_vip_payment_qr_map()}


@app.put("/api/vip/payment-qr")
def update_vip_payment_qr(request: Request, payload: dict = Body(...)):
    require_admin_access(request, require_csrf=True)
    apply_rate_limit(request, "vip_payment_qr_update")

    method = str(payload.get("method", "")).lower().strip()
    url = str(payload.get("url", "")).strip()

    if method not in {"yape", "binance", "crypto"}:
        raise HTTPException(status_code=400, detail="Invalid payment method")
    if not url:
        raise HTTPException(status_code=400, detail="URL is required")
    if not is_valid_payment_qr_url(url):
        raise HTTPException(status_code=400, detail="Invalid URL format")

    data = load_vip_payment_qr_map()
    data[method] = url
    saved = save_vip_payment_qr_map(data)
    return {"ok": True, "data": saved}


@app.post("/api/media/upload")
async def upload_media(request: Request, file: UploadFile = File(...), folder: str = Form("products")):
    require_admin_access(request, require_csrf=True)
    apply_rate_limit(request, "media_upload")

    if not file or not file.filename:
        raise HTTPException(status_code=400, detail="File is required")

    content_type = (file.content_type or "").lower().strip()
    media_kind = detect_media_kind(content_type)
    validate_content_type(media_kind, content_type)

    safe_folder = clean_folder(folder)
    max_bytes = max_bytes_for_kind(media_kind)
    ext = infer_extension(file.filename, content_type)

    now = datetime.now(timezone.utc)
    object_name = f"{now.strftime('%Y%m%d-%H%M%S')}-{uuid.uuid4().hex}{ext}"
    object_key = f"{safe_folder}/{media_kind}s/{object_name}"

    temp_path, size_bytes = await persist_upload_to_temp(file, max_bytes=max_bytes)

    try:
        use_supabase_storage = MEDIA_STORAGE_MODE == "supabase" and _is_supabase_enabled()
        if use_supabase_storage:
            public_url = await upload_to_supabase_storage(
                temp_path=temp_path,
                object_key=object_key,
                content_type=content_type,
            )
            storage_provider = "supabase"
        else:
            public_url = move_to_local_storage(
                temp_path=temp_path,
                object_name=object_name,
                media_kind=media_kind,
            )
            storage_provider = "local"
            object_key = public_url
    finally:
        if temp_path.exists():
            temp_path.unlink(missing_ok=True)

    media_id = insert_media_record(
        object_key=object_key,
        public_url=public_url,
        media_kind=media_kind,
        mime_type=content_type,
        size_bytes=size_bytes,
        storage_provider=storage_provider,
    )

    return {
        "ok": True,
        "id": media_id,
        "url": public_url,
        "object_key": object_key,
        "kind": media_kind,
        "mime_type": content_type,
        "size_bytes": size_bytes,
        "storage_provider": storage_provider,
    }


@app.get("/{page_name}.html")
async def read_generic_page(page_name: str, request: Request):
    if page_name.lower() == "admin" and not _has_admin_portal_access(request):
        return RedirectResponse(url="/", status_code=303)
    if page_name.lower() in USER_PROTECTED_PAGES and not get_user_session(request) and not get_admin_session(request):
        return RedirectResponse(url="/", status_code=303)
    path = BASE_DIR / f"{page_name}.html"
    if path.exists():
        return FileResponse(str(path))
    raise HTTPException(status_code=404, detail="Page not found")
