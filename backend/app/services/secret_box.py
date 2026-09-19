"""Authenticated encryption for settings that must not sit in the database in clear.

The key is derived from ``JWT_SECRET_KEY``, so a leaked database dump (or a
backup) does not expose the stored SMTP password on its own. Rotating the JWT
secret makes existing secrets undecryptable, which is treated as "not set"
rather than an error.
"""
from __future__ import annotations

import base64
import hashlib
import logging
from typing import Optional

from cryptography.fernet import Fernet, InvalidToken

from app.config import JWT_SECRET_KEY

logger = logging.getLogger("litechat.secrets")

_SALT = b"litechat.app-settings.v1"
_ITERATIONS = 200_000
_PREFIX = "enc:v1:"


def _fernet() -> Fernet:
    key = hashlib.pbkdf2_hmac("sha256", JWT_SECRET_KEY.encode("utf-8"), _SALT, _ITERATIONS, dklen=32)
    return Fernet(base64.urlsafe_b64encode(key))


def encrypt(plaintext: str) -> str:
    """Encrypt a value for storage. Empty input stays empty (means "unset")."""
    if not plaintext:
        return ""
    token = _fernet().encrypt(plaintext.encode("utf-8")).decode("ascii")
    return f"{_PREFIX}{token}"


def decrypt(stored: Optional[str]) -> str:
    """Decrypt a stored value. Unreadable or legacy plaintext returns as-is."""
    if not stored:
        return ""
    if not stored.startswith(_PREFIX):
        # Value was written before encryption existed; treat it as plaintext.
        return stored

    try:
        return _fernet().decrypt(stored[len(_PREFIX):].encode("ascii")).decode("utf-8")
    except (InvalidToken, ValueError):
        logger.warning("Stored secret could not be decrypted (JWT secret rotated?); treating as unset")
        return ""


def is_encrypted(stored: Optional[str]) -> bool:
    return bool(stored and stored.startswith(_PREFIX))
