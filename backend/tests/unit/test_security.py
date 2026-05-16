import pytest
from app.core.security import (
    derive_hmac_key,
    hash_token,
    lookup_prefix,
    verify_token_hash,
)


def test_hash_then_verify_succeeds() -> None:
    raw = "my-secret-token-abc"
    h = hash_token(raw)
    assert h != raw
    assert h.startswith("$argon2id$")
    assert verify_token_hash(raw, h) is True


def test_verify_wrong_token_fails() -> None:
    h = hash_token("correct")
    assert verify_token_hash("incorrect", h) is False


def test_verify_invalid_hash_returns_false() -> None:
    assert verify_token_hash("anything", "not-a-real-hash") is False


def test_hashes_differ_due_to_salt() -> None:
    h1 = hash_token("same-token")
    h2 = hash_token("same-token")
    assert h1 != h2  # 隨機 salt 確保每次雜湊不同


def test_lookup_prefix_deterministic() -> None:
    key = b"k" * 32
    p1 = lookup_prefix("raw-token-xyz", key)
    p2 = lookup_prefix("raw-token-xyz", key)
    assert p1 == p2
    assert len(p1) == 16


def test_lookup_prefix_different_tokens_diverge() -> None:
    key = b"k" * 32
    assert lookup_prefix("token-a", key) != lookup_prefix("token-b", key)


def test_lookup_prefix_different_keys_diverge() -> None:
    p1 = lookup_prefix("same-token", b"a" * 32)
    p2 = lookup_prefix("same-token", b"b" * 32)
    assert p1 != p2


def test_lookup_prefix_empty_key_raises() -> None:
    with pytest.raises(ValueError, match="hmac_key 不可為空"):
        lookup_prefix("token", b"")


def test_derive_hmac_key_returns_32_bytes() -> None:
    key = derive_hmac_key("api-key-value")
    assert len(key) == 32
