from __future__ import annotations

import os

import pytest

from octw.vault.envelope import EnvelopeVault


@pytest.fixture
def kek():
    return os.urandom(32)


@pytest.fixture
def vault(kek):
    return EnvelopeVault(kek=kek)


class TestEnvelopeVault:
    def test_generate_dek(self, vault):
        dek = vault.generate_dek()
        assert len(dek) == 32
        dek2 = vault.generate_dek()
        assert dek != dek2

    def test_encrypt_decrypt_dek(self, vault):
        dek = vault.generate_dek()
        ct, nonce = vault.encrypt_dek(dek)
        assert ct != dek
        decrypted = vault.decrypt_dek(ct, nonce)
        assert decrypted == dek

    def test_encrypt_decrypt_value(self, vault):
        dek = vault.generate_dek()
        plaintext = b"sk-secret-api-key-12345"
        ct, nonce = vault.encrypt_value(dek, plaintext)
        assert ct != plaintext
        decrypted = vault.decrypt_value(dek, ct, nonce)
        assert decrypted == plaintext

    def test_different_nonces(self, vault):
        dek = vault.generate_dek()
        plaintext = b"same-value"
        ct1, n1 = vault.encrypt_value(dek, plaintext)
        ct2, n2 = vault.encrypt_value(dek, plaintext)
        assert n1 != n2
        assert ct1 != ct2

    def test_wrong_key_fails(self, kek):
        vault = EnvelopeVault(kek=kek)
        dek = vault.generate_dek()
        ct, nonce = vault.encrypt_value(dek, b"secret")
        wrong_dek = os.urandom(32)
        with pytest.raises(Exception):
            vault.decrypt_value(wrong_dek, ct, nonce)

    def test_tampered_ciphertext_fails(self, vault):
        dek = vault.generate_dek()
        ct, nonce = vault.encrypt_value(dek, b"secret")
        tampered = bytearray(ct)
        tampered[0] ^= 0xFF
        with pytest.raises(Exception):
            vault.decrypt_value(dek, bytes(tampered), nonce)


class TestEnvelopeVaultKEK:
    def test_wrong_kek_for_dek(self):
        kek1 = os.urandom(32)
        kek2 = os.urandom(32)
        v1 = EnvelopeVault(kek=kek1)
        v2 = EnvelopeVault(kek=kek2)
        dek = v1.generate_dek()
        ct, nonce = v1.encrypt_dek(dek)
        with pytest.raises(Exception):
            v2.decrypt_dek(ct, nonce)
