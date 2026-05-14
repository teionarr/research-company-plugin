"""Tiny file-based cache with TTL.

Used by the plugin in standalone mode (no backend service) to avoid re-hitting
APIs for the same query within a freshness window. When the backend service
(`research-service` in the kitchen repo) is reachable, that service's Redis
cache supersedes this — both honor the same TTL conventions.

Keys are hashed (sha256) so a cache directory listing doesn't reveal the user's
target companies. Values are JSON-serializable.

Defaults:
    base_dir: ~/.cache/research-company/
    fact_ttl: 24 hours (news, headcount, hiring — things that change daily)
    static_ttl: 7 days (tech stack, funding history, founders — change rarely)

Usage:
    cache = Cache()
    if (cached := cache.get("perplexity", {"q": "Stripe overview"})) is not None:
        return cached
    result = expensive_call(...)
    cache.set("perplexity", {"q": "Stripe overview"}, result, ttl_kind="fact")
"""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
import time
from pathlib import Path
from typing import Any, Literal

DEFAULT_BASE = Path.home() / ".cache" / "research-company"
FACT_TTL_S = 24 * 60 * 60  # 1 day
STATIC_TTL_S = 7 * 24 * 60 * 60  # 7 days

TtlKind = Literal["fact", "static"]


def _hash_key(namespace: str, payload: dict[str, Any] | str) -> str:
    """Stable hash of (namespace, payload). Sorts dict keys so equivalent dicts collide."""
    if isinstance(payload, dict):
        encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    else:
        encoded = str(payload).encode()
    digest = hashlib.sha256(namespace.encode() + b"\x00" + encoded).hexdigest()
    return f"{namespace}-{digest[:32]}"


class Cache:
    """File-based cache with TTL. Thread-safe enough for single-process use; not for concurrent processes."""

    def __init__(
        self,
        base_dir: Path | None = None,
        fact_ttl_s: int = FACT_TTL_S,
        static_ttl_s: int = STATIC_TTL_S,
    ) -> None:
        self.base_dir = Path(base_dir) if base_dir else DEFAULT_BASE
        self.fact_ttl_s = fact_ttl_s
        self.static_ttl_s = static_ttl_s
        self.base_dir.mkdir(parents=True, exist_ok=True)

    def _path(self, key: str) -> Path:
        return self.base_dir / f"{key}.json"

    def get(self, namespace: str, payload: dict[str, Any] | str) -> Any | None:
        """Return the cached value if present and not expired, else None."""
        path = self._path(_hash_key(namespace, payload))
        if not path.exists():
            return None
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            # Corrupt cache entry — treat as miss; clean up.
            try:
                path.unlink()
            except OSError:
                pass
            return None
        expires_at = raw.get("expires_at", 0)
        if not isinstance(expires_at, int | float) or expires_at < time.time():
            try:
                path.unlink()
            except OSError:
                pass
            return None
        return raw.get("value")

    def set(
        self,
        namespace: str,
        payload: dict[str, Any] | str,
        value: Any,
        *,
        ttl_kind: TtlKind = "fact",
    ) -> None:
        """Store value. Atomic write via temp-file rename so a crash mid-write doesn't corrupt."""
        ttl = self.static_ttl_s if ttl_kind == "static" else self.fact_ttl_s
        path = self._path(_hash_key(namespace, payload))
        envelope = {
            "namespace": namespace,
            "expires_at": int(time.time()) + ttl,
            "ttl_kind": ttl_kind,
            "value": value,
        }
        tmp_fd, tmp_name = tempfile.mkstemp(dir=str(self.base_dir), suffix=".tmp")
        try:
            with os.fdopen(tmp_fd, "w", encoding="utf-8") as f:
                json.dump(envelope, f, separators=(",", ":"))
            os.replace(tmp_name, path)
        except Exception:
            # Best-effort cleanup of temp file on failure.
            try:
                os.unlink(tmp_name)
            except OSError:
                pass
            raise

    def delete(self, namespace: str, payload: dict[str, Any] | str) -> bool:
        """Delete a cache entry. Returns True if it existed."""
        path = self._path(_hash_key(namespace, payload))
        if path.exists():
            try:
                path.unlink()
                return True
            except OSError:
                return False
        return False

    def clear(self, namespace: str | None = None) -> int:
        """Delete entries. If namespace is given, only entries for that namespace.

        Returns the number of entries deleted.
        """
        prefix = f"{namespace}-" if namespace else ""
        deleted = 0
        for p in self.base_dir.glob(f"{prefix}*.json"):
            try:
                p.unlink()
                deleted += 1
            except OSError:
                pass
        return deleted

    def stats(self) -> dict[str, int]:
        """Quick health check — entry count, total size on disk, expired count."""
        now = time.time()
        entries = 0
        total_bytes = 0
        expired = 0
        for p in self.base_dir.glob("*.json"):
            try:
                stat = p.stat()
                entries += 1
                total_bytes += stat.st_size
                raw = json.loads(p.read_text(encoding="utf-8"))
                if raw.get("expires_at", 0) < now:
                    expired += 1
            except (OSError, json.JSONDecodeError):
                pass
        return {"entries": entries, "total_bytes": total_bytes, "expired": expired}
