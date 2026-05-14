"""Tests for ServiceClient.verify() — the kitchen /verify integration."""

from __future__ import annotations

import io
import json
import sys
import urllib.error
from pathlib import Path
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "lib"))

import service_client as sc
from _cache import Cache


class _FakeResponse:
    def __init__(self, status: int, body: bytes = b"") -> None:
        self.status = status
        self._body = body

    def read(self) -> bytes:
        return self._body

    def __enter__(self) -> _FakeResponse:
        return self

    def __exit__(self, *args: object) -> None:
        return None


def _ok(payload: dict) -> _FakeResponse:
    return _FakeResponse(200, json.dumps(payload).encode())


@pytest.fixture
def cache(tmp_path: Path) -> Cache:
    return Cache(base_dir=tmp_path)


@pytest.fixture
def client(cache: Cache) -> sc.ServiceClient:
    return sc.ServiceClient(base_url="https://api.example.com", bearer_token="tok", cache=cache)


def test_verify_returns_kitchen_report_on_success(client: sc.ServiceClient) -> None:
    insights = [
        {
            "id": "x-1",
            "domain": "people",
            "headline": "Stripe headcount around 8000",
            "evidence": "Per LinkedIn",
            "sources": [{"title": "LinkedIn", "url": "https://linkedin.com/company/stripe"}],
            "confidence": "medium",
            "raw_facts": ["headcount ~8000"],
        }
    ]
    kitchen_report = {
        "verifications": [
            {"insight_id": "x-1", "suggested_confidence": "medium", "issues": []},
        ],
        "cross_domain_contradictions": [],
        "summary": {"insights_verified": 1, "issues_total": 0},
    }
    with patch("urllib.request.urlopen", return_value=_ok({"ok": True})):
        client.is_available()  # prime reachability
    with patch("urllib.request.urlopen", return_value=_ok(kitchen_report)):
        result = client.verify(insights, target_domain="stripe.com")
    assert result == kitchen_report


def test_verify_sends_correct_body(client: sc.ServiceClient) -> None:
    captured: dict = {}

    def fake_urlopen(req, timeout=None):
        captured["body"] = req.data
        captured["path"] = req.full_url
        return _ok({"verifications": [], "cross_domain_contradictions": [], "summary": {}})

    with patch("urllib.request.urlopen", return_value=_ok({"ok": True})):
        client.is_available()
    with patch("urllib.request.urlopen", side_effect=fake_urlopen):
        client.verify(
            [{"id": "a", "domain": "x", "headline": "y", "evidence": "z", "sources": []}],
            target_domain="example.com",
            skip_url_check=True,
        )
    body = json.loads(captured["body"].decode())
    assert body["target_domain"] == "example.com"
    assert body["skip_url_check"] is True
    assert isinstance(body["insights"], list)
    assert captured["path"].endswith("/verify")


def test_verify_returns_none_when_service_unreachable(client: sc.ServiceClient) -> None:
    with patch("urllib.request.urlopen", side_effect=urllib.error.URLError("connection refused")):
        assert client.verify([], target_domain=None) is None


def test_verify_is_never_cached(client: sc.ServiceClient, cache: Cache) -> None:
    """Two identical /verify calls should each hit the network — URL liveness changes."""
    with patch("urllib.request.urlopen", return_value=_ok({"ok": True})):
        client.is_available()
    call_count = 0

    def counting(req, timeout=None):
        nonlocal call_count
        call_count += 1
        return _ok({"verifications": [], "cross_domain_contradictions": [], "summary": {}})

    with patch("urllib.request.urlopen", side_effect=counting):
        client.verify([], target_domain=None)
        client.verify([], target_domain=None)
    assert call_count == 2  # both calls hit network
    assert cache.stats()["entries"] == 0  # nothing cached


def test_verify_handles_4xx_gracefully(client: sc.ServiceClient) -> None:
    """A 422 from the kitchen (bad payload) → None, not exception."""
    with patch("urllib.request.urlopen", return_value=_ok({"ok": True})):
        client.is_available()
    err = urllib.error.HTTPError("http://x/", 422, "unprocessable", {}, io.BytesIO(b""))
    with patch("urllib.request.urlopen", side_effect=err):
        assert client.verify([{}], target_domain=None) is None
