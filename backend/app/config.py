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
