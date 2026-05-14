"""CLI shim around service_client — gives agents a Bash-callable interface.

Agents invoke kitchen endpoints via:
    python lib/kitchen_cli.py verify < insights.json
    python lib/kitchen_cli.py verify --insights-file /tmp/insights.json [--target-domain stripe.com]

The CLI prints the kitchen's JSON response on stdout. Exit codes:
    0 — success (response printed)
    1 — kitchen unreachable (no service URL, or /health failed)
    2 — kitchen returned an error / unexpected shape

This is the bridge between agent prompts (which can only invoke shells via Bash)
and the kitchen's HTTP API.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# Importable when run as script via `python lib/kitchen_cli.py ...`
sys.path.insert(0, str(Path(__file__).resolve().parent))

from service_client import ServiceClient


def _err(msg: str, code: int = 2) -> int:
    print(json.dumps({"ok": False, "error": msg}), file=sys.stderr)
    return code


def _read_insights(path: str | None) -> list[dict] | None:
    """Read insights from a file or stdin. Returns None on parse failure."""
    if path:
        try:
            raw = Path(path).read_text(encoding="utf-8")
        except OSError as e:
            print(f"could not read {path}: {e}", file=sys.stderr)
            return None
    else:
        raw = sys.stdin.read()
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as e:
        print(f"invalid JSON: {e}", file=sys.stderr)
        return None
    # Accept either a bare list or {"insights": [...]} for ergonomics
    if isinstance(data, dict) and "insights" in data:
        data = data["insights"]
    if not isinstance(data, list):
        print("expected a JSON array of insights (or {insights: [...]})", file=sys.stderr)
        return None
    return data


def cmd_verify(args: argparse.Namespace) -> int:
    client = ServiceClient()
    if not client.is_available():
        return _err("kitchen service not reachable (RESEARCH_SERVICE_URL unset or unreachable)", code=1)

    insights = _read_insights(args.insights_file)
    if insights is None:
        return 2

    result = client.verify(
        insights,
        target_domain=args.target_domain,
        skip_url_check=args.skip_url_check,
    )
    if result is None:
        return _err("kitchen /verify returned no response (network or 5xx)", code=2)

    print(json.dumps(result, indent=2 if args.pretty else None))
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="kitchen_cli",
        description="Agent-friendly CLI for the ai-native-kitchen HTTP API.",
    )
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_verify = sub.add_parser("verify", help="Run deterministic checks over a list of insights")
    p_verify.add_argument(
        "--insights-file",
        type=str,
        default=None,
        help="Path to a JSON file containing insights. If omitted, reads from stdin.",
    )
    p_verify.add_argument(
        "--target-domain",
        type=str,
        default=None,
        help="Target company's primary domain (e.g. stripe.com). Triggers the self-citation rule for high-confidence insights.",
    )
    p_verify.add_argument(
        "--skip-url-check",
        action="store_true",
        help="Skip URL liveness HEAD checks (faster, no network I/O).",
    )
    p_verify.add_argument("--pretty", action="store_true", help="Pretty-print JSON output.")
    p_verify.set_defaults(func=cmd_verify)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
