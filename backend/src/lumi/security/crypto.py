"""Fernet encryption for OAuth tokens stored in the DB."""

from __future__ import annotations

import base64
import hashlib

from cryptography.fernet import Fernet, InvalidToken

from lumi.config import get_settings


class CryptoError(Exception):
    pass


def _fernet() -> Fernet:
    key = get_settings().encryption_key
    if not key or key.startswith("change-me"):
        # Local-dev fallback: derive a stable key from whatever is configured.
        # Real setups generate a proper key via `python -m lumi.scripts.generate_encryption_key`.
        derived = hashlib.sha256(f"lumi-local:{key}".encode()).digest()
        return Fernet(base64.urlsafe_b64encode(derived))
    try:
        return Fernet(key.encode())
    except (ValueError, TypeError) as exc:
        raise CryptoError("ENCRYPTION_KEY is not a valid Fernet key") from exc


def encrypt_text(plaintext: str) -> str:
    return _fernet().encrypt(plaintext.encode()).decode()


def decrypt_text(ciphertext: str) -> str:
    try:
        return _fernet().decrypt(ciphertext.encode()).decode()
    except InvalidToken as exc:
        raise CryptoError("cannot decrypt: wrong ENCRYPTION_KEY?") from exc
