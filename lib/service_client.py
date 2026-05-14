"""HTTP client for the kitchen's research-service.

In standalone mode (no service URL configured, or service unreachable), every method
returns None so callers fall back to direct MCP / API calls. The plugin must always
work without the service.

In service mode, calls go through the kitchen's FastAPI service which handles:
- Shared Redis cache (faster than per-machine local cache, hits across all skills)
- Cost telemetry (tokens + upstream USD per skill / endpoint)
- Premium-API access (Perplexity, Crunchbase, Semrush, Apollo, Wappalyzer paid)
- Rate-limit budgets enforced server-side

Auth: bearer token in `SERVICE_BEARER_TOKEN_RESEARCH_COMPANY` env var.
Timeouts: 5s default, 30s for /domain (deep research call). 1 retry on 5xx, no retry on 4xx.

Local cache (lib/_cache.py) is consulted before HTTP. Cache writes happen on every
successful response so a kitchen outage doesn't lose recent results.
"""

from __future__ import annotations

import json
import logging
import os
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

from _cache import Cache

log = logging.getLogger(__name__)

DEFAULT_TIMEOUT_S = 5
DOMAIN_TIMEOUT_S = 30
HEALTH_TIMEOUT_S = 2

ENV_SERVICE_URL = "RESEARCH_SERVICE_URL"
ENV_BEARER = "SERVICE_BEARER_TOKEN_RESEARCH_COMPANY"
USER_AGENT = "research-company-plugin/0.1"


class ServiceClient:
    """Auto-fallback HTTP client. If the service is reachable, use it. Otherwise return None.

    Construction is cheap; reachability is checked lazily on first call (and cached for
    the lifetime of the instance).
    """

    def __init__(
        self,
        base_url: str | None = None,
        bearer_token: str | None = None,
        cache: Cache | None = None,
        skill_id: str = "research-company",
    ) -> None:
        self.base_url = (base_url or os.environ.get(ENV_SERVICE_URL, "")).rstrip("/") or None
        self.bearer_token = bearer_token or os.environ.get(ENV_BEARER)
        self.cache = cache or Cache()
        self.skill_id = skill_id
        self._reachable: bool | None = None

    def is_available(self) -> bool:
        """True if the service URL is configured AND /health responds within HEALTH_TIMEOUT_S.

        Memoized — first call probes, subsequent calls return the cached result. Use
        reset_reachability() to re-probe.
        """
        if self._reachable is not None:
            return self._reachable
        if not self.base_url:
            self._reachable = False
            return False
        try:
            self._request("GET", "/health", timeout=HEALTH_TIMEOUT_S, _skip_auth=True)
            self._reachable = True
        except _ServiceUnreachable:
            self._reachable = False
        except _ServiceError as e:
            log.warning("service /health returned non-success: %s", e)
            self._reachable = False
        return self._reachable

    def reset_reachability(self) -> None:
        """Clear the memoized reachability flag — next call will re-probe."""
        self._reachable = None

    # ---- Public typed wrappers ----

    def discover(self, company: str, *, focus: str = "") -> dict[str, Any] | None:
        """Run the discovery pass server-side. Returns SHARED_FACTS dict, or None if unavailable."""
        return self._post(
            "/discover",
            payload={"company": company, "focus": focus},
            cache_namespace="service.discover",
            cache_ttl_kind="fact",
        )

    def domain(
        self,
        slug: str,
        company: str,
        focus: str,
        shared_facts: dict[str, Any],
    ) -> dict[str, Any] | None:
        """Run a single domain expert server-side. Slow path (uses domain timeout)."""
        return self._post(
            f"/domain/{slug}",
            payload={"company": company, "focus": focus, "shared_facts": shared_facts},
            cache_namespace=f"service.domain.{slug}",
            cache_ttl_kind="fact",
            timeout=DOMAIN_TIMEOUT_S,
        )

    def traffic(self, company: str, *, primary_url: str | None = None) -> dict[str, Any] | None:
        return self._post(
            "/traffic",
            payload={"company": company, "primary_url": primary_url},
            cache_namespace="service.traffic",
            cache_ttl_kind="fact",
        )

    def funding(self, company: str) -> dict[str, Any] | None:
        return self._post(
            "/funding",
            payload={"company": company},
            cache_namespace="service.funding",
            cache_ttl_kind="static",
        )

    def people(self, company: str) -> dict[str, Any] | None:
        return self._post(
            "/people",
            payload={"company": company},
            cache_namespace="service.people",
            cache_ttl_kind="fact",
        )

    def tech(self, primary_url: str) -> dict[str, Any] | None:
        return self._post(
            "/tech",
            payload={"primary_url": primary_url},
            cache_namespace="service.tech",
            cache_ttl_kind="static",
        )

    def upload_brief(self, html: str, slug: str) -> str | None:
        """Upload an HTML brief; returns the public URL (briefs.<your-domain>/<slug>.html) or None."""
        result = self._post(
            "/briefs",
            payload={"slug": slug, "html": html},
            cache_namespace=None,  # never cache brief uploads
            cache_ttl_kind="fact",
        )
        if result and isinstance(result, dict):
            url = result.get("url")
            return url if isinstance(url, str) else None
        return None

    def verify(
        self,
        insights: list[dict[str, Any]],
        *,
        target_domain: str | None = None,
        skip_url_check: bool = False,
    ) -> dict[str, Any] | None:
        """Run the kitchen's deterministic checks against a list of insights.

        Returns the VerificationReport dict (verifications + cross_domain_contradictions
        + summary) or None if the kitchen is unreachable. Never raises to the caller.

        Not cached — verification results depend on the exact insight payload AND on
        URL liveness, which can change minute-to-minute.
        """
        return self._post(
            "/verify",
            payload={
                "insights": insights,
                "target_domain": target_domain,
                "skip_url_check": skip_url_check,
            },
            cache_namespace=None,  # never cache; depends on URL liveness which changes
            cache_ttl_kind="fact",
        )

    # ---- Internals ----

    def _post(
        self,
        path: str,
        *,
        payload: dict[str, Any],
        cache_namespace: str | None,
        cache_ttl_kind: str,
        timeout: int = DEFAULT_TIMEOUT_S,
    ) -> dict[str, Any] | None:
        """POST helper with cache-before-request and retry-on-5xx semantics."""
        if cache_namespace:
            cached = self.cache.get(cache_namespace, payload)
            if cached is not None:
                log.debug("service cache HIT: %s", cache_namespace)
                return cached
        if not self.is_available():
            return None
        try:
            result = self._request("POST", path, body=payload, timeout=timeout)
        except _ServiceUnreachable:
            self._reachable = False
            return None
        except _ServiceError as e:
            log.warning("service %s returned %s: %s", path, e.status, e.detail)
            # Network OK, server said no — don't degrade reachability flag, just fail this call
            return None
        if cache_namespace and isinstance(result, dict):
            try:
                self.cache.set(cache_namespace, payload, result, ttl_kind=cache_ttl_kind)  # type: ignore[arg-type]
            except OSError as e:
                log.warning("cache write failed for %s: %s", cache_namespace, e)
        return result if isinstance(result, dict) else None

    def _request(
        self,
        method: str,
        path: str,
        *,
        body: dict[str, Any] | None = None,
        timeout: int = DEFAULT_TIMEOUT_S,
        _skip_auth: bool = False,
        _retry: bool = True,
    ) -> dict[str, Any] | None:
        """Send a single HTTP request. Raises _ServiceUnreachable on connection errors,
        _ServiceError on non-2xx responses. Retries once on 5xx if _retry is True.
        """
        if not self.base_url:
            raise _ServiceUnreachable("base_url not configured")
        url = f"{self.base_url}{path}"
        headers = {
            "User-Agent": USER_AGENT,
            "X-Skill-Id": self.skill_id,
        }
        if not _skip_auth and self.bearer_token:
            headers["Authorization"] = f"Bearer {self.bearer_token}"
        data = None
        if body is not None:
            data = json.dumps(body).encode("utf-8")
            headers["Content-Type"] = "application/json"
        req = urllib.request.Request(url, data=data, headers=headers, method=method)  # noqa: S310 — base_url validated by caller / env
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310 — same
                status = resp.status
                if 200 <= status < 300:
                    raw = resp.read().decode("utf-8")
                    if not raw:
                        return None
                    try:
                        return json.loads(raw)
                    except json.JSONDecodeError as e:
                        raise _ServiceError(status, f"invalid JSON in 2xx response: {e}") from e
                raise _ServiceError(status, f"{method} {path} returned {status}")
        except urllib.error.HTTPError as e:
            if 500 <= e.code < 600 and _retry:
                log.info("service 5xx (%s); retrying once", e.code)
                return self._request(method, path, body=body, timeout=timeout, _skip_auth=_skip_auth, _retry=False)
            raise _ServiceError(e.code, str(e)) from e
        except (urllib.error.URLError, TimeoutError, ConnectionError) as e:
            raise _ServiceUnreachable(str(e)) from e


class _ServiceUnreachable(Exception):
    """Raised when the service URL is unset or the network can't reach it."""


class _ServiceError(Exception):
    """Raised when the service responded but with a non-2xx status."""

    def __init__(self, status: int, detail: str) -> None:
        super().__init__(f"HTTP {status}: {detail}")
        self.status = status
        self.detail = detail
