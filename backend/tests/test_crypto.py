"""
Tests for app/core/crypto.py — at-rest encryption for provider API keys.
"""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from app.core.crypto import encrypt_value, decrypt_value


def test_round_trip():
    original = "sk-ant-api03-fake-test-key-12345"
    encrypted = encrypt_value(original)
    assert encrypted != original
    assert decrypt_value(encrypted) == original


def test_encrypted_value_is_not_substring_of_plaintext():
    """The whole point — ciphertext must not leak the plaintext key."""
    original = "sk-super-secret-value"
    encrypted = encrypt_value(original)
    assert original not in encrypted


def test_decrypt_plaintext_fallback_for_pre_encryption_data():
    """Existing installs have plaintext keys from before encryption was
    added — decrypt_value must return them as-is instead of crashing, so
    upgrading doesn't break existing LLM configs."""
    plaintext = "sk-this-was-never-encrypted"
    assert decrypt_value(plaintext) == plaintext


def test_empty_and_none_pass_through_type_decorator():
    from app.core.crypto import EncryptedString

    col_type = EncryptedString()
    assert col_type.process_bind_param(None, None) is None
    assert col_type.process_bind_param("", None) == ""
    assert col_type.process_result_value(None, None) is None


def test_type_decorator_round_trip():
    from app.core.crypto import EncryptedString

    col_type = EncryptedString()
    bound = col_type.process_bind_param("my-api-key", None)
    assert bound != "my-api-key"
    result = col_type.process_result_value(bound, None)
    assert result == "my-api-key"
