"""CLI shim around service_client — gives agents a Bash-callable interface.

Agents invoke kitchen endpoints via:
    python lib/kitchen_cli.py search   --query "Stripe overview" [--limit 5]
    python lib/kitchen_cli.py scrape   --url "https://stripe.com"
    python lib/kitchen_cli.py funding  --company "Stripe"
    python lib/kitchen_cli.py people   --company "Stripe"
    python lib/kitchen_cli.py tech     --primary-url "https://stripe.com" [--company "Stripe"]
    python lib/kitchen_cli.py traffic  --domain "stripe.com"
    python lib/kitchen_cli.py verify   --insights-file /tmp/insights.json [--target-domain stripe.com]

The CLI prints the kitchen's JSON response on stdout. Exit codes:
    0 — success (response printed)
    1 — kitchen unreachable (RESEARCH_SERVICE_URL unset, /health failed, or method 404'd)
    2 — kitchen returned an error / unexpected shape / bad input

This is the bridge between agent prompts (which can only invoke shells via Bash)
and the kitchen's HTTP API. Each subcommand maps 1:1 to a ServiceClient method.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))

from service_client import ServiceClient


def _err(msg: str, code: int = 2) -> int:
    print(json.dumps({"ok": False, "error": msg}), file=sys.stderr)
    return code


def _read_insights(path: str | None) -> list[dict] | None:
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
    if isinstance(data, dict) and "insights" in data:
        data = data["insights"]
    if not isinstance(data, list):
        print("expected a JSON array of insights (or {insights: [...]})", file=sys.stderr)
        return None
    return data


def _emit(result: Any, pretty: bool) -> int:
    if result is None:
        return _err("kitchen returned no response (network or 5xx)", code=2)
    print(json.dumps(result, indent=2 if pretty else None))
    return 0


def _require_kitchen(client: ServiceClient) -> int | None:
    """Return None if kitchen is reachable; otherwise a non-zero exit code (to be returned)."""
    if not client.is_available():
        return _err("kitchen service not reachable (RESEARCH_SERVICE_URL unset or unreachable)", code=1)
    return None


# ---- Subcommands -------------------------------------------------------------------------------


def cmd_search(args: argparse.Namespace) -> int:
    client = ServiceClient()
    if (rc := _require_kitchen(client)) is not None:
        return rc
    return _emit(client.search(args.query, limit=args.limit), args.pretty)


def cmd_scrape(args: argparse.Namespace) -> int:
    client = ServiceClient()
    if (rc := _require_kitchen(client)) is not None:
        return rc
    return _emit(client.scrape(args.url), args.pretty)


def cmd_funding(args: argparse.Namespace) -> int:
    client = ServiceClient()
    if (rc := _require_kitchen(client)) is not None:
        return rc
    return _emit(client.funding(args.company), args.pretty)


def cmd_people(args: argparse.Namespace) -> int:
    client = ServiceClient()
    if (rc := _require_kitchen(client)) is not None:
        return rc
    return _emit(client.people(args.company), args.pretty)


def cmd_tech(args: argparse.Namespace) -> int:
    client = ServiceClient()
    if (rc := _require_kitchen(client)) is not None:
        return rc
    return _emit(client.tech(args.primary_url, company=args.company), args.pretty)


def cmd_traffic(args: argparse.Namespace) -> int:
    client = ServiceClient()
    if (rc := _require_kitchen(client)) is not None:
        return rc
    return _emit(client.traffic(args.domain), args.pretty)


def cmd_verify(args: argparse.Namespace) -> int:
    client = ServiceClient()
    if (rc := _require_kitchen(client)) is not None:
        return rc
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


def cmd_available(args: argparse.Namespace) -> int:
    """Quick reachability check — used by SKILL.md's pre-flight."""
    client = ServiceClient()
    available = client.is_available()
    print(json.dumps({"available": available}))
    return 0 if available else 1


# ---- Wire it up --------------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="kitchen_cli",
        description="Agent-friendly CLI for the ai-native-kitchen HTTP API.",
    )
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_avail = sub.add_parser("available", help="Probe kitchen reachability; exit 0 if up, 1 if down")
    p_avail.add_argument("--pretty", action="store_true")
    p_avail.set_defaults(func=cmd_available)

    p_search = sub.add_parser("search", help="POST /search — semantic web search")
    p_search.add_argument("--query", required=True)
    p_search.add_argument("--limit", type=int, default=5)
    p_search.add_argument("--pretty", action="store_true")
    p_search.set_defaults(func=cmd_search)

    p_scrape = sub.add_parser("scrape", help="POST /scrape — fetch URL → markdown")
    p_scrape.add_argument("--url", required=True)
    p_scrape.add_argument("--pretty", action="store_true")
    p_scrape.set_defaults(func=cmd_scrape)

    p_funding = sub.add_parser("funding", help="POST /funding — SEC filings + funding history")
    p_funding.add_argument("--company", required=True)
    p_funding.add_argument("--pretty", action="store_true")
    p_funding.set_defaults(func=cmd_funding)

    p_people = sub.add_parser("people", help="POST /people — headcount + org facts")
    p_people.add_argument("--company", required=True)
    p_people.add_argument("--pretty", action="store_true")
    p_people.set_defaults(func=cmd_people)

    p_tech = sub.add_parser("tech", help="POST /tech — frontend/infra fingerprinting")
    p_tech.add_argument("--primary-url", required=True)
    p_tech.add_argument("--company", default=None)
    p_tech.add_argument("--pretty", action="store_true")
    p_tech.set_defaults(func=cmd_tech)

    p_traffic = sub.add_parser("traffic", help="POST /traffic — google trends top_keywords + growth")
    p_traffic.add_argument("--domain", required=True)
    p_traffic.add_argument("--pretty", action="store_true")
    p_traffic.set_defaults(func=cmd_traffic)

    p_verify = sub.add_parser("verify", help="POST /verify — deterministic checks over insights")
    p_verify.add_argument("--insights-file", type=str, default=None)
    p_verify.add_argument("--target-domain", type=str, default=None)
    p_verify.add_argument("--skip-url-check", action="store_true")
    p_verify.add_argument("--pretty", action="store_true")
    p_verify.set_defaults(func=cmd_verify)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
