"""Tests for service_client.

The HTTP transport is mocked at the urllib level — we don't run a real server.
Coverage focuses on the contract callers depend on:
- standalone mode (no URL / unreachable) returns None instead of raising
- bearer token is sent when present
- skill_id header is always sent
- cache is consulted before HTTP, and HTTP results are cached after
- 5xx retries once, 4xx does not
- TimeoutError / URLError → returns None and degrades reachability flag
- POST /briefs is never cached
"""

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

# ---- Helpers ----------------------------------------------------------------


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


def _http_err(code: int) -> urllib.error.HTTPError:
    return urllib.error.HTTPError("http://x/", code, f"err {code}", {}, io.BytesIO(b""))


@pytest.fixture
def cache(tmp_path: Path) -> Cache:
    return Cache(base_dir=tmp_path)


@pytest.fixture
def client(cache: Cache) -> sc.ServiceClient:
    return sc.ServiceClient(base_url="https://api.example.com", bearer_token="t-secret", cache=cache)


# ---- Standalone-mode behavior ----------------------------------------------


def test_no_url_means_unavailable(cache: Cache) -> None:
    c = sc.ServiceClient(base_url=None, bearer_token=None, cache=cache)
    assert c.is_available() is False
    assert c.funding("Stripe") is None


def test_url_set_but_unreachable_returns_none(client: sc.ServiceClient) -> None:
    with patch("urllib.request.urlopen", side_effect=urllib.error.URLError("connection refused")):
        assert client.is_available() is False
        assert client.funding("Stripe") is None


def test_reachability_is_memoized(client: sc.ServiceClient) -> None:
    with patch("urllib.request.urlopen", return_value=_ok({"ok": True})) as mock_open:
        assert client.is_available() is True
        assert client.is_available() is True
        # Health probe called only once
        assert mock_open.call_count == 1


def test_reset_reachability_re_probes(client: sc.ServiceClient) -> None:
    with patch("urllib.request.urlopen", return_value=_ok({"ok": True})) as mock_open:
        client.is_available()
        client.reset_reachability()
        client.is_available()
        assert mock_open.call_count == 2


# ---- Headers / auth ----------------------------------------------------------


def test_bearer_token_sent_when_present(client: sc.ServiceClient) -> None:
    captured = {}

    def fake_urlopen(req, timeout=None):
        captured["headers"] = dict(req.header_items())
        captured["url"] = req.full_url
        return _ok({"facts": {}})

    with patch("urllib.request.urlopen", side_effect=fake_urlopen):
        client.is_available()  # primes reachability
        client.funding("Stripe")
    # Header keys are normalized to title case by urllib
    assert captured["headers"].get("Authorization") == "Bearer t-secret"
    assert captured["headers"].get("X-skill-id") == "research-company"


def test_health_probe_skips_auth(client: sc.ServiceClient) -> None:
    captured = {}

    def fake_urlopen(req, timeout=None):
        captured.setdefault("calls", []).append(dict(req.header_items()))
        return _ok({"ok": True})

    with patch("urllib.request.urlopen", side_effect=fake_urlopen):
        client.is_available()
    assert "Authorization" not in captured["calls"][0]


# ---- Caching ----------------------------------------------------------------


def test_cache_hit_skips_http(client: sc.ServiceClient, cache: Cache) -> None:
    cache.set("service.funding", {"company": "Stripe"}, {"facts": "cached"}, ttl_kind="fact")
    with patch("urllib.request.urlopen") as mock_open:
        result = client.funding("Stripe")
    assert result == {"facts": "cached"}
    mock_open.assert_not_called()


def test_response_is_cached_after_success(client: sc.ServiceClient, cache: Cache) -> None:
    with patch("urllib.request.urlopen", return_value=_ok({"facts": "fresh"})):
        client.is_available()  # primes reachability separately
    with patch("urllib.request.urlopen", return_value=_ok({"facts": "fresh"})):
        client.funding("Stripe")
    assert cache.get("service.funding", {"company": "Stripe"}) == {"facts": "fresh"}


def test_verify_is_never_cached(client: sc.ServiceClient, cache: Cache) -> None:
    """/verify is intentionally uncached — URL liveness changes minute-to-minute."""
    with patch("urllib.request.urlopen", return_value=_ok({"ok": True})):
        client.is_available()
    with patch(
        "urllib.request.urlopen",
        return_value=_ok({"verifications": [], "cross_domain_contradictions": [], "summary": {}}),
    ):
        client.verify([{"id": "x"}], target_domain="example.com")
    assert cache.stats()["entries"] == 0


# ---- Retry semantics --------------------------------------------------------


def test_5xx_retries_once_then_succeeds(client: sc.ServiceClient) -> None:
    responses = [_http_err(503), _ok({"facts": "second-try"})]

    def fake_urlopen(req, timeout=None):
        r = responses.pop(0)
        if isinstance(r, urllib.error.HTTPError):
            raise r
        return r

    # Prime reachability with a separate mock so retries on /funding are clean
    with patch("urllib.request.urlopen", return_value=_ok({"ok": True})):
        client.is_available()
    with patch("urllib.request.urlopen", side_effect=fake_urlopen):
        result = client.funding("Stripe")
    assert result == {"facts": "second-try"}
    assert responses == []  # both consumed


def test_5xx_after_retry_returns_none(client: sc.ServiceClient) -> None:
    with patch("urllib.request.urlopen", return_value=_ok({"ok": True})):
        client.is_available()
    with patch("urllib.request.urlopen", side_effect=_http_err(502)):
        assert client.funding("Stripe") is None


def test_4xx_does_not_retry(client: sc.ServiceClient) -> None:
    with patch("urllib.request.urlopen", return_value=_ok({"ok": True})):
        client.is_available()
    call_count = 0

    def counting(req, timeout=None):
        nonlocal call_count
        call_count += 1
        raise _http_err(401)

    with patch("urllib.request.urlopen", side_effect=counting):
        assert client.funding("Stripe") is None
    assert call_count == 1  # no retry on 4xx


def test_timeout_returns_none_and_degrades_reachability(client: sc.ServiceClient) -> None:
    with patch("urllib.request.urlopen", return_value=_ok({"ok": True})):
        client.is_available()
    assert client._reachable is True
    with patch("urllib.request.urlopen", side_effect=TimeoutError("timed out")):
        assert client.funding("Stripe") is None
    # Connection-level failures mark service unreachable so subsequent calls don't waste time
    assert client._reachable is False


# ---- Env-var construction ---------------------------------------------------


def test_constructor_reads_env_vars(monkeypatch: pytest.MonkeyPatch, cache: Cache) -> None:
    monkeypatch.setenv("RESEARCH_SERVICE_URL", "https://kitchen.example.com/")
    monkeypatch.setenv("SERVICE_BEARER_TOKEN_RESEARCH_COMPANY", "env-token")
    c = sc.ServiceClient(cache=cache)
    assert c.base_url == "https://kitchen.example.com"  # trailing slash trimmed
    assert c.bearer_token == "env-token"


def test_typed_wrappers_use_correct_paths(client: sc.ServiceClient) -> None:
    captured_paths = []

    def fake_urlopen(req, timeout=None):
        captured_paths.append(urllib.parse.urlparse(req.full_url).path)
        return _ok({})

    with patch("urllib.request.urlopen", side_effect=fake_urlopen):
        client.is_available()
        client.search("query")
        client.scrape("https://x.com")
        client.traffic("x.com")
        client.funding("X")
        client.people("X")
        client.tech("https://x.com")
        client.verify([{"id": "y"}])

    # First call is /health, then the typed wrappers
    assert captured_paths == ["/health", "/search", "/scrape", "/traffic", "/funding", "/people", "/tech", "/verify"]


def test_search_passes_query_and_limit(client: sc.ServiceClient) -> None:
    captured: dict = {}

    def fake_urlopen(req, timeout=None):
        captured["body"] = req.data
        return _ok({"results": []})

    with patch("urllib.request.urlopen", return_value=_ok({"ok": True})):
        client.is_available()
    with patch("urllib.request.urlopen", side_effect=fake_urlopen):
        client.search("Stripe overview", limit=10)
    body = json.loads(captured["body"].decode())
    assert body["query"] == "Stripe overview"
    assert body["limit"] == 10


def test_traffic_sends_domain_not_company(client: sc.ServiceClient) -> None:
    captured: dict = {}

    def fake_urlopen(req, timeout=None):
        captured["body"] = req.data
        return _ok({"top_keywords": []})

    with patch("urllib.request.urlopen", return_value=_ok({"ok": True})):
        client.is_available()
    with patch("urllib.request.urlopen", side_effect=fake_urlopen):
        client.traffic("stripe.com")
    body = json.loads(captured["body"].decode())
    assert body == {"domain": "stripe.com"}
    assert "company" not in body  # the kitchen wants `domain`, not `company`
