import os

import pytest
from cryptography.fernet import Fernet

from avanamy.services import encryption_service


def test_encryption_service_requires_key(monkeypatch):
    monkeypatch.delenv("ENCRYPTION_KEY", raising=False)
    with pytest.raises(ValueError):
        encryption_service.EncryptionService()


def test_encrypt_decrypt_roundtrip(monkeypatch):
    key = Fernet.generate_key().decode()
    monkeypatch.setenv("ENCRYPTION_KEY", key)

    service = encryption_service.EncryptionService()
    encrypted = service.encrypt("secret")

    assert encrypted != "secret"
    assert service.decrypt(encrypted) == "secret"


def test_encrypt_decrypt_empty(monkeypatch):
    key = Fernet.generate_key().decode()
    monkeypatch.setenv("ENCRYPTION_KEY", key)

    service = encryption_service.EncryptionService()
    assert service.encrypt("") == ""
    assert service.decrypt("") == ""


def test_decrypt_invalid_raises(monkeypatch):
    key = Fernet.generate_key().decode()
    monkeypatch.setenv("ENCRYPTION_KEY", key)

    service = encryption_service.EncryptionService()
    with pytest.raises(ValueError):
        service.decrypt("not-a-valid-token")


def test_get_encryption_service_singleton(monkeypatch):
    key = Fernet.generate_key().decode()
    monkeypatch.setenv("ENCRYPTION_KEY", key)

    encryption_service._encryption_service = None
    first = encryption_service.get_encryption_service()
    second = encryption_service.get_encryption_service()

    assert first is second
