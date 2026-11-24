"""
Authentication, password hashing, and signed access tokens for the JARVIS backend.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import re
import secrets
import sqlite3
import time
from typing import Any

from backend.config import Settings
from backend.database import get_connection
from backend.logger import logger

_USERNAME_PATTERN = re.compile(r"^[a-zA-Z0-9_.-]{3,32}$")
_PBKDF2_ITERATIONS = 200_000


class AuthError(Exception):
    """Base authentication error."""


class RegistrationDisabledError(AuthError):
    """Raised when public registration is turned off."""


class UserAlreadyExistsError(AuthError):
    """Raised when trying to register an existing username."""


class InvalidCredentialsError(AuthError):
    """Raised when username or password is wrong."""


class InvalidTokenError(AuthError):
    """Raised when an access token is invalid or expired."""


def _b64url_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _b64url_decode(data: str) -> bytes:
    padding = "=" * (-len(data) % 4)
    return base64.urlsafe_b64decode((data + padding).encode("ascii"))


def hash_password(password: str) -> str:
    """Hash a password using PBKDF2-HMAC-SHA256 with a random salt."""
    if len(password) < 8:
        raise AuthError("Password must be at least 8 characters long.")

    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt,
        _PBKDF2_ITERATIONS,
    )
    return f"pbkdf2_sha256${_PBKDF2_ITERATIONS}${salt.hex()}${digest.hex()}"


def verify_password(password: str, stored_hash: str) -> bool:
    """Verify a plain password against a stored PBKDF2 hash."""
    try:
        algorithm, iter_str, salt_hex, hash_hex = stored_hash.split("$", 3)
        if algorithm != "pbkdf2_sha256":
            return False
        iterations = int(iter_str)
        salt = bytes.fromhex(salt_hex)
        expected_digest = bytes.fromhex(hash_hex)
    except (ValueError, TypeError):
        return False

    actual_digest = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt,
        iterations,
    )
    return hmac.compare_digest(actual_digest, expected_digest)


def create_access_token(
    user_id: int,
    username: str,
    secret: str,
    ttl_minutes: int = 1440,
) -> str:
    """Create a signed, expiring access token for the Android app."""
    if not secret:
        raise AuthError("Server auth secret is not configured.")

    now = int(time.time())
    payload = {
        "sub": user_id,
        "username": username,
        "iat": now,
        "exp": now + (ttl_minutes * 60),
    }
    payload_bytes = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
    payload_b64 = _b64url_encode(payload_bytes)

    signature = hmac.new(
        secret.encode("utf-8"),
        payload_b64.encode("ascii"),
        hashlib.sha256,
    ).digest()
    sig_b64 = _b64url_encode(signature)

    return f"{payload_b64}.{sig_b64}"


def verify_access_token(token: str, secret: str) -> dict[str, Any]:
    """Verify a token's signature and expiry, returning its payload."""
    if not token or "." not in token or not secret:
        raise InvalidTokenError("Missing or malformed token.")

    try:
        payload_b64, sig_b64 = token.split(".", 1)
        expected_sig = hmac.new(
            secret.encode("utf-8"),
            payload_b64.encode("ascii"),
            hashlib.sha256,
        ).digest()
        provided_sig = _b64url_decode(sig_b64)
    except Exception as exc:
        raise InvalidTokenError("Invalid token format.") from exc

    if not hmac.compare_digest(expected_sig, provided_sig):
        raise InvalidTokenError("Invalid token signature.")

    try:
        payload = json.loads(_b64url_decode(payload_b64).decode("utf-8"))
    except Exception as exc:
        raise InvalidTokenError("Corrupted token payload.") from exc

    if int(time.time()) >= int(payload.get("exp", 0)):
        raise InvalidTokenError("Token has expired. Please log in again.")

    if "sub" not in payload or "username" not in payload:
        raise InvalidTokenError("Incomplete token payload.")

    return payload


def _normalize_username(username: str) -> str:
    cleaned = username.strip().lower()
    if not _USERNAME_PATTERN.match(cleaned):
        raise AuthError(
            "Username must be 3-32 characters and contain only letters, numbers, '_', '.', or '-'."
        )
    return cleaned


def register_user(settings: Settings, username: str, password: str) -> dict[str, Any]:
    """Register a new user account and return user details + access token."""
    if not settings.allow_registration:
        raise RegistrationDisabledError("Registration is currently disabled.")

    clean_username = _normalize_username(username)
    pw_hash = hash_password(password)

    with get_connection(settings.db_path) as conn:
        try:
            cursor = conn.execute(
                "INSERT INTO users (username, password_hash) VALUES (?, ?)",
                (clean_username, pw_hash),
            )
            user_id = int(cursor.lastrowid)
        except sqlite3.IntegrityError as exc:
            raise UserAlreadyExistsError("That username is already taken.") from exc

    logger.info("Registered new user: %s (id=%s)", clean_username, user_id)
    token = create_access_token(
        user_id=user_id,
        username=clean_username,
        secret=settings.auth_secret,
        ttl_minutes=settings.token_ttl_minutes,
    )
    return {
        "user": {"id": user_id, "username": clean_username},
        "access_token": token,
        "token_type": "bearer",
    }


def authenticate_user(settings: Settings, username: str, password: str) -> dict[str, Any]:
    """Verify username/password and return user details + access token."""
    clean_username = username.strip().lower()
    if not clean_username or not password:
        raise InvalidCredentialsError("Username and password are required.")

    with get_connection(settings.db_path) as conn:
        row = conn.execute(
            "SELECT id, username, password_hash FROM users WHERE username = ?",
            (clean_username,),
        ).fetchone()

    if row is None or not verify_password(password, row["password_hash"]):
        raise InvalidCredentialsError("Invalid username or password.")

    user_id = int(row["id"])
    token = create_access_token(
        user_id=user_id,
        username=row["username"],
        secret=settings.auth_secret,
        ttl_minutes=settings.token_ttl_minutes,
    )
    logger.info("User logged in: %s (id=%s)", row["username"], user_id)
    return {
        "user": {"id": user_id, "username": row["username"]},
        "access_token": token,
        "token_type": "bearer",
    }


def get_user_by_id(settings: Settings, user_id: int) -> dict[str, Any] | None:
    """Fetch a user's public info by ID, or None if not found."""
    with get_connection(settings.db_path) as conn:
        row = conn.execute(
            "SELECT id, username, created_at FROM users WHERE id = ?",
            (user_id,),
        ).fetchone()

    if row is None:
        return None
    return {
        "id": int(row["id"]),
        "username": row["username"],
        "created_at": row["created_at"],
    }