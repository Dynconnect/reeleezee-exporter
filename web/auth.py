"""Session management and credential encryption."""

import json
import uuid
from datetime import datetime, timedelta
from typing import Optional

from cryptography.fernet import Fernet, InvalidToken
from fastapi import Cookie, HTTPException, Request

from . import config
from .database import get_db


def _get_fernet() -> Fernet:
    """Create a Fernet cipher from the SECRET_KEY.

    Fernet requires a 32-byte url-safe base64-encoded key.
    We derive one from the configured SECRET_KEY by padding/hashing.
    """
    import base64
    import hashlib
    key_bytes = hashlib.sha256(config.SECRET_KEY.encode()).digest()
    return Fernet(base64.urlsafe_b64encode(key_bytes))


def encrypt_credentials(username: str, password: str) -> bytes:
    """Encrypt credentials for storage."""
    f = _get_fernet()
    payload = json.dumps({"username": username, "password": password}).encode()
    return f.encrypt(payload)


def decrypt_credentials(encrypted: bytes) -> dict:
    """Decrypt credentials, returns {"username": ..., "password": ...}."""
    f = _get_fernet()
    try:
        payload = f.decrypt(encrypted)
        return json.loads(payload)
    except (InvalidToken, json.JSONDecodeError) as e:
        raise ValueError(f"Failed to decrypt credentials: {e}")


def create_session(encrypted_credentials: bytes, administrations: list) -> str:
    """Create a new session in the database, return session ID."""
    session_id = str(uuid.uuid4())
    expires_at = datetime.utcnow() + timedelta(hours=config.SESSION_EXPIRY_HOURS)

    with get_db() as db:
        db.execute(
            """INSERT INTO sessions (id, encrypted_credentials, administrations, expires_at)
               VALUES (?, ?, ?, ?)""",
            (session_id, encrypted_credentials, json.dumps(administrations),
             expires_at.isoformat()),
        )
    return session_id


def get_session(session_id: str) -> Optional[dict]:
    """Retrieve a valid (non-expired) session."""
    with get_db() as db:
        row = db.execute(
            "SELECT * FROM sessions WHERE id = ? AND expires_at > datetime('now')",
            (session_id,),
        ).fetchone()
        if not row:
            return None
        # Update last_active
        db.execute(
            "UPDATE sessions SET last_active = datetime('now') WHERE id = ?",
            (session_id,),
        )
        return dict(row)


def delete_session(session_id: str):
    """Delete a session."""
    with get_db() as db:
        db.execute("DELETE FROM sessions WHERE id = ?", (session_id,))


def get_current_session(request: Request) -> dict:
    """FastAPI dependency: extract and validate session from cookie.

    Raises HTTPException 401 if not authenticated.
    """
    session_id = request.cookies.get("session_id")
    if not session_id:
        raise HTTPException(status_code=401, detail="Not authenticated")

    session = get_session(session_id)
    if not session:
        raise HTTPException(status_code=401, detail="Session expired or invalid")

    return session


def cleanup_expired_sessions():
    """Remove expired sessions from the database."""
    with get_db() as db:
        db.execute("DELETE FROM sessions WHERE expires_at <= datetime('now')")
