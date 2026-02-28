from __future__ import annotations

import os
from pathlib import Path

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from octw.common.config import settings
from octw.common.logging import get_logger

log = get_logger(__name__)

_NONCE_SIZE = 12
_KEY_SIZE = 32  # AES-256


class EnvelopeVault:
    """Envelope encryption: KEK wraps per-tenant DEKs, DEKs wrap secret values."""

    def __init__(self, kek: bytes | None = None) -> None:
        if kek is not None:
            self._kek = kek
        else:
            self._kek = self._load_kek()
        self._aesgcm = AESGCM(self._kek)

    @staticmethod
    def _load_kek() -> bytes:
        kek_env = os.environ.get("OCTW_KEK")
        if kek_env:
            raw = bytes.fromhex(kek_env)
            if len(raw) != _KEY_SIZE:
                raise ValueError(f"KEK must be {_KEY_SIZE} bytes")
            return raw
        kek_path = Path(settings.kek_path)
        if kek_path.exists():
            try:
                raw = kek_path.read_bytes()
            except PermissionError:
                raise RuntimeError(
                    f"KEK file at {kek_path} is not readable by the current user. "
                    f"Run: sudo chown $USER {kek_path}"
                ) from None
            if len(raw) != _KEY_SIZE:
                raise ValueError(f"KEK must be {_KEY_SIZE} bytes, got {len(raw)}")
            return raw
        raise RuntimeError(
            f"No KEK found. Generate one with: "
            f"sudo python3 -c \"import os; open('{settings.kek_path}','wb')"
            f".write(os.urandom(32))\" && sudo chown $USER {settings.kek_path}"
        )

    @staticmethod
    def generate_dek() -> bytes:
        return os.urandom(_KEY_SIZE)

    def encrypt_dek(self, dek: bytes) -> tuple[bytes, bytes]:
        nonce = os.urandom(_NONCE_SIZE)
        ct = self._aesgcm.encrypt(nonce, dek, None)
        return ct, nonce

    def decrypt_dek(self, encrypted_dek: bytes, nonce: bytes) -> bytes:
        return self._aesgcm.decrypt(nonce, encrypted_dek, None)

    @staticmethod
    def encrypt_value(dek: bytes, plaintext: bytes) -> tuple[bytes, bytes]:
        nonce = os.urandom(_NONCE_SIZE)
        aesgcm = AESGCM(dek)
        ct = aesgcm.encrypt(nonce, plaintext, None)
        return ct, nonce

    @staticmethod
    def decrypt_value(dek: bytes, ciphertext: bytes, nonce: bytes) -> bytes:
        aesgcm = AESGCM(dek)
        return aesgcm.decrypt(nonce, ciphertext, None)
