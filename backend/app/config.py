from pathlib import Path
import os

BASE_DIR = Path(__file__).resolve().parent.parent
UPLOAD_DIR = BASE_DIR / "uploads"
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

# Database Configuration
DATABASE_URL = os.getenv("DATABASE_URL", f"sqlite+aiosqlite:///{BASE_DIR / 'litechat.db'}")

import secrets
import logging

logger = logging.getLogger("litechat.security")

# Security & JWT
ENV_JWT_SECRET = os.getenv("JWT_SECRET_KEY")
if not ENV_JWT_SECRET:
    if os.getenv("ENVIRONMENT") == "production":
        raise RuntimeError("FATAL: JWT_SECRET_KEY environment variable MUST be explicitly set in production mode.")
    secret_file = BASE_DIR / ".jwt_secret"
    if secret_file.exists():
        JWT_SECRET_KEY = secret_file.read_text().strip()
    else:
        JWT_SECRET_KEY = secrets.token_urlsafe(32)
        try:
            secret_file.write_text(JWT_SECRET_KEY)
        except Exception:
            pass
    logger.warning("DEVELOPMENT WARNING: Using auto-generated persistent JWT secret key from .jwt_secret")
else:
    JWT_SECRET_KEY = ENV_JWT_SECRET

JWT_ALGORITHM = "HS256"
JWT_EXPIRE_MINUTES = 60 * 24 * 7  # 7 days
# Short-lived ticket used on the WebSocket URL so the 7-day access token is
# not written into reverse-proxy access logs.
WS_TICKET_TTL_MINUTES = int(os.getenv("WS_TICKET_TTL_MINUTES", "2"))

# SLA Configuration (in minutes)
SLA_FIRST_RESPONSE_MINUTES = {
    "urgent": 15,
    "high": 30,
    "medium": 120,
    "low": 480,
}

SLA_RESOLUTION_MINUTES = {
    "urgent": 120,
    "high": 360,
    "medium": 1440,
    "low": 2880,
}


def _env_flag(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in ("1", "true", "yes", "on")


ENVIRONMENT = os.getenv("ENVIRONMENT", "development").strip().lower()
IS_PRODUCTION = ENVIRONMENT == "production"

# Public API docs are useful in development but expose the whole surface in
# production, so they are disabled there unless explicitly re-enabled.
ENABLE_API_DOCS = _env_flag("ENABLE_API_DOCS", default=not IS_PRODUCTION)

# --- Rate limiting -----------------------------------------------------------
# Applied per client IP to the credential endpoints. This limiter is held in
# process memory: it protects a single worker. Behind multiple workers or a
# load balancer, move the store to Redis so the limits are shared.
RATE_LIMIT_ENABLED = _env_flag("RATE_LIMIT_ENABLED", default=True)
# Only trust X-Forwarded-For when the app actually sits behind a trusted proxy,
# otherwise a client can spoof the header and bypass the limit.
TRUST_PROXY_HEADERS = _env_flag("TRUST_PROXY_HEADERS", default=False)

# route path -> (max requests, window in seconds)
def _rate_rule(max_requests: int, window_seconds: int) -> tuple[int, int]:
    return (max_requests, window_seconds)


RATE_LIMIT_RULES = {
    "/api/auth/login": _rate_rule(int(os.getenv("RATE_LIMIT_LOGIN", "10")), 60),
    "/api/auth/register": _rate_rule(int(os.getenv("RATE_LIMIT_REGISTER", "5")), 600),
    "/api/auth/setup-admin": _rate_rule(int(os.getenv("RATE_LIMIT_SETUP_ADMIN", "5")), 600),
    "/api/auth/forgot-password": _rate_rule(int(os.getenv("RATE_LIMIT_FORGOT_PASSWORD", "5")), 600),
    "/api/auth/reset-password": _rate_rule(int(os.getenv("RATE_LIMIT_RESET_PASSWORD", "10")), 600),
    "/api/auth/resend-verification": _rate_rule(int(os.getenv("RATE_LIMIT_RESEND_VERIFICATION", "5")), 600),
    "/api/auth/verify-email": _rate_rule(int(os.getenv("RATE_LIMIT_VERIFY_EMAIL", "20")), 600),
    "/api/auth/ws-ticket": _rate_rule(int(os.getenv("RATE_LIMIT_WS_TICKET", "30")), 60),
    "/api/upload": _rate_rule(int(os.getenv("RATE_LIMIT_UPLOAD", "20")), 60),
}

# --- Email delivery ----------------------------------------------------------
# When SMTP_HOST is unset (the default in development) outbound mail is logged
# instead of sent, so password-reset links are visible in the server output.
SMTP_HOST = os.getenv("SMTP_HOST")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SMTP_USERNAME = os.getenv("SMTP_USERNAME")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD")
SMTP_USE_TLS = _env_flag("SMTP_USE_TLS", default=True)
SMTP_FROM = os.getenv("SMTP_FROM", "no-reply@litechat.local")
# Base URL of the frontend, used to build links inside emails.
PUBLIC_APP_URL = os.getenv("PUBLIC_APP_URL", "http://localhost:3000").rstrip("/")

# Token lifetimes (minutes)
PASSWORD_RESET_TTL_MINUTES = int(os.getenv("PASSWORD_RESET_TTL_MINUTES", "30"))
EMAIL_VERIFICATION_TTL_MINUTES = int(os.getenv("EMAIL_VERIFICATION_TTL_MINUTES", "1440"))

