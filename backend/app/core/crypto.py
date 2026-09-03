"""
At-rest encryption for sensitive DB columns (LLM/embedder API keys, AWS
secrets, Vertex credentials). Previously these were stored as plaintext in
SQLite — masked in *some* API responses, but fully readable to anyone with
filesystem access to obtrac.db, and unmasked in at least one endpoint
(GET /embedder/default).

Key management: OBTRAC_ENCRYPTION_KEY env var takes priority (required for
any real deployment — e.g. Docker/Kubernetes secrets). If unset, a key is
generated on first use and persisted to data/.encryption_key with 0600
permissions, so a single self-hosted instance keeps working across restarts
without extra setup. Losing that file makes existing encrypted secrets
unrecoverable — back it up like you would the database itself.
"""

import base64
import logging
import os

from cryptography.fernet import Fernet, InvalidToken
from sqlalchemy import String, TypeDecorator

logger = logging.getLogger("obtrac")

_fernet: Fernet | None = None


def _load_or_create_key() -> bytes:
    env_key = os.environ.get("OBTRAC_ENCRYPTION_KEY")
    if env_key:
        return env_key.encode() if isinstance(env_key, str) else env_key

    from app.db.database import DATABASE_DIR
    key_path = os.path.join(DATABASE_DIR, ".encryption_key")

    if os.path.exists(key_path):
        with open(key_path, "rb") as f:
            return f.read().strip()

    key = Fernet.generate_key()
    fd = os.open(key_path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "wb") as f:
        f.write(key)
    logger.warning(
        f"No OBTRAC_ENCRYPTION_KEY set — generated a new encryption key at {key_path}. "
        "For production/hosted deployments, set OBTRAC_ENCRYPTION_KEY explicitly and "
        "back it up — losing it makes existing encrypted secrets unrecoverable."
    )
    return key


def _get_fernet() -> Fernet:
    global _fernet
    if _fernet is None:
        _fernet = Fernet(_load_or_create_key())
    return _fernet


def encrypt_value(value: str) -> str:
    token = _get_fernet().encrypt(value.encode("utf-8"))
    return base64.urlsafe_b64encode(token).decode("ascii")


def decrypt_value(stored: str) -> str:
    try:
        token = base64.urlsafe_b64decode(stored.encode("ascii"))
        return _get_fernet().decrypt(token).decode("utf-8")
    except (InvalidToken, ValueError, Exception):
        # Value predates encryption (plaintext from before this migration),
        # or was written under a different key. Treat it as already-plaintext
        # rather than crashing every read — this keeps existing installs
        # working; the value gets re-encrypted next time it's saved.
        return stored


class EncryptedString(TypeDecorator):
    """SQLAlchemy column type that transparently encrypts on write and
    decrypts on read. Existing callers that just do `record.api_key` keep
    working unchanged."""

    impl = String
    cache_ok = True

    def process_bind_param(self, value, dialect):
        if value is None or value == "":
            return value
        return encrypt_value(value)

    def process_result_value(self, value, dialect):
        if value is None or value == "":
            return value
        return decrypt_value(value)
