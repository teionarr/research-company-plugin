"""Tests for the file-based cache.

Cover the operations that matter for correctness: hit/miss, TTL expiry, atomic
writes, namespace clearing, and that keys are hashed (no plain target names on disk).
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "lib"))

import _cache as cache_mod


@pytest.fixture
def cache(tmp_path: Path) -> cache_mod.Cache:
    return cache_mod.Cache(base_dir=tmp_path)


def test_get_returns_none_for_missing(cache: cache_mod.Cache) -> None:
    assert cache.get("perplexity", {"q": "anything"}) is None


def test_set_then_get_roundtrip(cache: cache_mod.Cache) -> None:
    cache.set("perplexity", {"q": "Stripe"}, {"answer": "..."})
    assert cache.get("perplexity", {"q": "Stripe"}) == {"answer": "..."}


def test_get_returns_none_after_ttl_expiry(tmp_path: Path) -> None:
    c = cache_mod.Cache(base_dir=tmp_path, fact_ttl_s=0)  # immediate expiry
    c.set("perplexity", {"q": "Stripe"}, {"answer": "..."})
    time.sleep(0.05)
    assert c.get("perplexity", {"q": "Stripe"}) is None


def test_static_ttl_outlives_fact_ttl(tmp_path: Path) -> None:
    c = cache_mod.Cache(base_dir=tmp_path, fact_ttl_s=0, static_ttl_s=60)
    c.set("ns", {"q": "x"}, "static-value", ttl_kind="static")
    time.sleep(0.05)
    assert c.get("ns", {"q": "x"}) == "static-value"


def test_keys_are_hashed_not_plain(cache: cache_mod.Cache, tmp_path: Path) -> None:
    cache.set("perplexity", {"q": "Stripe Inc"}, {"answer": "..."})
    files = list(tmp_path.glob("*.json"))
    assert len(files) == 1
    # The plain text "Stripe Inc" should not appear in the filename
    assert "Stripe" not in files[0].name
    # The contents of the cache envelope DO retain the value (we want to read it back),
    # but the namespace is the only identifying string in the envelope (no payload).
    raw = json.loads(files[0].read_text())
    assert raw["namespace"] == "perplexity"


def test_dict_payload_order_independent(cache: cache_mod.Cache) -> None:
    cache.set("ns", {"a": 1, "b": 2}, "value")
    # Different key order should still hit
    assert cache.get("ns", {"b": 2, "a": 1}) == "value"


def test_string_payload_works(cache: cache_mod.Cache) -> None:
    cache.set("ns", "just-a-string-key", "value")
    assert cache.get("ns", "just-a-string-key") == "value"


def test_delete_removes_entry(cache: cache_mod.Cache) -> None:
    cache.set("ns", {"k": 1}, "value")
    assert cache.delete("ns", {"k": 1}) is True
    assert cache.get("ns", {"k": 1}) is None


def test_delete_returns_false_when_missing(cache: cache_mod.Cache) -> None:
    assert cache.delete("ns", {"k": "missing"}) is False


def test_clear_namespace_only(cache: cache_mod.Cache) -> None:
    cache.set("perplexity", {"q": "a"}, "v1")
    cache.set("perplexity", {"q": "b"}, "v2")
    cache.set("exa", {"q": "c"}, "v3")
    deleted = cache.clear("perplexity")
    assert deleted == 2
    assert cache.get("exa", {"q": "c"}) == "v3"


def test_clear_all(cache: cache_mod.Cache) -> None:
    cache.set("perplexity", {"q": "a"}, "v1")
    cache.set("exa", {"q": "c"}, "v3")
    deleted = cache.clear()
    assert deleted == 2


def test_corrupt_entry_treated_as_miss(cache: cache_mod.Cache, tmp_path: Path) -> None:
    cache.set("ns", {"k": 1}, "value")
    files = list(tmp_path.glob("*.json"))
    files[0].write_text("not json {{")
    assert cache.get("ns", {"k": 1}) is None
    # And the corrupt file should be cleaned up
    assert not files[0].exists()


def test_atomic_write_no_temp_files_left(cache: cache_mod.Cache, tmp_path: Path) -> None:
    cache.set("ns", {"k": 1}, "value")
    leftover = list(tmp_path.glob("*.tmp"))
    assert leftover == []


def test_stats(cache: cache_mod.Cache) -> None:
    cache.set("ns", {"k": 1}, "value")
    cache.set("ns", {"k": 2}, "value")
    s = cache.stats()
    assert s["entries"] == 2
    assert s["expired"] == 0
    assert s["total_bytes"] > 0


def test_hash_key_stable_across_calls() -> None:
    h1 = cache_mod._hash_key("ns", {"a": 1, "b": 2})
    h2 = cache_mod._hash_key("ns", {"b": 2, "a": 1})
    assert h1 == h2
    assert h1.startswith("ns-")
