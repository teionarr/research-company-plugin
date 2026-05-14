"""Render a research-company brief from collected JSON inputs to a single self-contained HTML file.

Inputs are JSON files produced by:
- 9 domain-expert agents (one JSON object each)
- synthesis-agent (one JSON object with top_5 + cross_domain_contradictions)
- verifier (one JSON object with verifications + numerical_contradictions)

Output is a single .html file: vanilla CSS, native <details>/<summary> collapsibles,
no JavaScript dependencies. Safe to email, host as a static file, or print to PDF.

Security posture:
- All text is escaped via html.escape(s, quote=True) before insertion.
- URLs are validated to http/https schemes only; javascript:/data:/file: are rejected.
- URLs are HEAD-checked in parallel; dead links get a visual marker, never crash render.
- The template has no inline scripts and the renderer never injects raw HTML from inputs.
"""

from __future__ import annotations

import argparse
import concurrent.futures
import datetime
import html
import json
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

VALID_URL_SCHEMES = frozenset({"http", "https"})
HEAD_CHECK_TIMEOUT_S = 10
HEAD_CHECK_WORKERS = 16

DOMAIN_LABELS = {
    "market": "Market",
    "sales": "Sales",
    "product": "Product",
    "rd": "R&D / Tech",
    "traffic": "Traffic & Demand",
    "people": "People",
    "hiring": "Hiring",
    "customers": "Customers & Feedback",
    "money": "Money",
}

TAG_EMOJI = {
    "strong": "💪",
    "weak": "🔧",
    "fun": "✨",
    "opening": "🎯",
    "contradiction": "🔀",
}

VERDICT_BADGE = {
    "verified": ("✅", "verified"),
    "inferred": ("✓", "inferred"),
    "not-supported": ("⚠", "unsupported"),
}

CONFIDENCE_LABEL = {
    "high": "high confidence",
    "medium": "medium confidence",
    "low": "low confidence — unverified",
}


# ---- Validation ---------------------------------------------------------------------------------


def is_safe_url(url: str) -> bool:
    """A URL is safe to render as href if its scheme is http or https."""
    if not isinstance(url, str) or not url:
        return False
    try:
        parsed = urllib.parse.urlparse(url)
    except ValueError:
        return False
    return parsed.scheme in VALID_URL_SCHEMES and bool(parsed.netloc)


def head_check(url: str, timeout: float = HEAD_CHECK_TIMEOUT_S) -> bool:
    """Return True if the URL responds with a 2xx/3xx status to a HEAD request within timeout."""
    if not is_safe_url(url):
        return False
    # S310 (audit URL open for permitted schemes) is the exact thing we just did
    # in is_safe_url() above — the scheme is already constrained to http/https.
    req = urllib.request.Request(  # noqa: S310 — scheme validated by is_safe_url
        url, method="HEAD", headers={"User-Agent": "research-company-brief/0.1"}
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310 — scheme validated by is_safe_url
            return 200 <= resp.status < 400
    except (urllib.error.URLError, TimeoutError, ConnectionError, ValueError):
        return False


def head_check_many(urls: list[str]) -> dict[str, bool]:
    """Concurrent HEAD checks. Returns {url: alive}."""
    if not urls:
        return {}
    results: dict[str, bool] = {}
    with concurrent.futures.ThreadPoolExecutor(max_workers=HEAD_CHECK_WORKERS) as pool:
        futures = {pool.submit(head_check, u): u for u in urls}
        for fut in concurrent.futures.as_completed(futures):
            results[futures[fut]] = fut.result()
    return results


# ---- Data classes -------------------------------------------------------------------------------


@dataclass
class Source:
    title: str
    url: str
    alive: bool = True


@dataclass
class Insight:
    id: str
    tag: str
    headline: str
    evidence: str
    sources: list[Source] = field(default_factory=list)
    confidence: str = "medium"
    tools_used: list[str] = field(default_factory=list)
    domain: str = ""
    verdict: str | None = None
    verdict_quote: str | None = None
    selection_reason: str | None = None


@dataclass
class DomainBlock:
    domain: str
    insights: list[Insight] = field(default_factory=list)
    raw_facts: list[str] = field(default_factory=list)
    gaps: list[str] = field(default_factory=list)


@dataclass
class Brief:
    company: str
    focus: str
    generated_at: str
    domains: list[DomainBlock] = field(default_factory=list)
    top_5: list[Insight] = field(default_factory=list)
    cross_domain_contradictions: list[Insight] = field(default_factory=list)
    verification_summary: dict[str, int] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)


# ---- Parsing ------------------------------------------------------------------------------------


def parse_insight(raw: dict[str, Any], domain: str) -> Insight | None:
    """Build an Insight from a JSON dict. Return None if required fields are missing or malformed."""
    try:
        sources_in = raw.get("sources") or []
        if not isinstance(sources_in, list):
            return None
        sources = [
            Source(title=str(s.get("title", "source")), url=str(s.get("url", "")))
            for s in sources_in
            if isinstance(s, dict) and is_safe_url(s.get("url", ""))
        ]
        tag = str(raw.get("tag", "")).lower()
        if tag not in TAG_EMOJI:
            return None
        confidence = str(raw.get("confidence", "medium")).lower()
        if confidence not in CONFIDENCE_LABEL:
            confidence = "medium"
        headline = str(raw.get("headline", "")).strip()
        evidence = str(raw.get("evidence", "")).strip()
        if not headline:
            return None
        return Insight(
            id=str(raw.get("id", "")) or f"{domain}-?",
            tag=tag,
            headline=headline,
            evidence=evidence,
            sources=sources,
            confidence=confidence,
            tools_used=[str(t) for t in raw.get("tools_used", []) if isinstance(t, str)],
            domain=domain,
        )
    except (TypeError, ValueError, AttributeError):
        return None


def parse_domain_block(raw: dict[str, Any]) -> DomainBlock | None:
    """Parse one domain expert's JSON output."""
    if not isinstance(raw, dict):
        return None
    domain = str(raw.get("domain", "")).lower()
    if domain not in DOMAIN_LABELS:
        return None
    insights = [ins for ins in (parse_insight(i, domain) for i in raw.get("insights", []) or []) if ins is not None]
    return DomainBlock(
        domain=domain,
        insights=insights,
        raw_facts=[str(f) for f in (raw.get("raw_facts") or []) if isinstance(f, str)],
        gaps=[str(g) for g in (raw.get("gaps") or []) if isinstance(g, str)],
    )


def apply_confidence_downgrades(insight: Insight) -> Insight:
    """Deterministic confidence downgrades:
    - If all sources are from the same domain → max medium.
    - If there are zero live sources → low.
    """
    if insight.confidence == "high" and insight.sources:
        netlocs = {urllib.parse.urlparse(s.url).netloc for s in insight.sources}
        if len(netlocs) <= 1:
            insight.confidence = "medium"
    if insight.sources and not any(s.alive for s in insight.sources):
        insight.confidence = "low"
    return insight


# ---- Rendering ----------------------------------------------------------------------------------


def esc(s: Any) -> str:
    return html.escape(str(s), quote=True)


def render_source(s: Source) -> str:
    if not is_safe_url(s.url):
        return ""
    marker = "" if s.alive else ' <span class="dead-link" title="link not reachable at render time">⚠</span>'
    return f'<li><a href="{esc(s.url)}" rel="noopener noreferrer" target="_blank">{esc(s.title)}</a>{marker}</li>'


def render_insight(insight: Insight, *, open_by_default: bool = False) -> str:
    badge_html = ""
    if insight.verdict and insight.verdict in VERDICT_BADGE:
        emoji, label = VERDICT_BADGE[insight.verdict]
        badge_html = (
            f'<span class="verdict verdict-{esc(insight.verdict)}" title="{esc(label)}">'
            f"{esc(emoji)} {esc(label)}</span>"
        )
    confidence_html = (
        f'<span class="confidence confidence-{esc(insight.confidence)}">'
        f"{esc(CONFIDENCE_LABEL.get(insight.confidence, insight.confidence))}</span>"
    )
    tag_html = f'<span class="tag tag-{esc(insight.tag)}">{esc(TAG_EMOJI.get(insight.tag, ""))}</span>'
    sources_html = ""
    if insight.sources:
        items = "".join(render_source(s) for s in insight.sources)
        sources_html = f'<ul class="sources">{items}</ul>'
    quote_html = ""
    if insight.verdict_quote:
        quote_html = f'<blockquote class="quote">{esc(insight.verdict_quote)}</blockquote>'
    open_attr = " open" if open_by_default else ""
    return (
        f'<details class="insight insight-{esc(insight.tag)} confidence-{esc(insight.confidence)}"{open_attr}>'
        f'<summary><span class="headline">{tag_html} {esc(insight.headline)}</span> '
        f"{badge_html} {confidence_html}</summary>"
        f'<div class="insight-body">'
        f'<p class="evidence">{esc(insight.evidence)}</p>'
        f"{quote_html}"
        f"{sources_html}"
        f"</div>"
        f"</details>"
    )


def render_domain_block(block: DomainBlock) -> str:
    if not block.insights and not block.gaps:
        return ""
    label = DOMAIN_LABELS.get(block.domain, block.domain.title())
    insight_count = len(block.insights)
    insights_html = "".join(render_insight(i) for i in block.insights)
    gaps_html = ""
    if block.gaps:
        items = "".join(f"<li>{esc(g)}</li>" for g in block.gaps)
        gaps_html = f'<details class="gaps"><summary>Gaps ({len(block.gaps)})</summary><ul>{items}</ul></details>'
    return (
        f'<section class="domain domain-{esc(block.domain)}">'
        f'<h2>{esc(label)} <span class="count">({insight_count})</span></h2>'
        f"{insights_html}"
        f"{gaps_html}"
        f"</section>"
    )


def render_top_5_section(top_5: list[Insight]) -> str:
    if not top_5:
        return '<section class="top-5 empty"><h2>Top 5</h2><p>No insights selected.</p></section>'
    items = "".join(render_insight(i, open_by_default=True) for i in top_5)
    return f'<section class="top-5">' f"<h2>Top 5 to use in your interview</h2>" f"{items}" f"</section>"


def render_verification_summary(summary: dict[str, int]) -> str:
    if not summary:
        return ""
    parts = []
    for k in ("verified_count", "inferred_count", "not_supported_count", "dead_source_count"):
        v = summary.get(k, 0)
        if v:
            label = k.replace("_count", "").replace("_", " ")
            parts.append(f"{v} {esc(label)}")
    if not parts:
        return ""
    return f'<p class="verification-summary"><strong>Verification:</strong> {", ".join(parts)}</p>'


def render_contradictions_footer(items: list[Insight]) -> str:
    if not items:
        return ""
    body = "".join(render_insight(i) for i in items)
    return f'<footer class="contradictions">' f"<h2>🔀 Cross-domain contradictions</h2>" f"{body}" f"</footer>"


CSS = """
* { box-sizing: border-box; }
body {
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", system-ui, sans-serif;
  max-width: 880px; margin: 0 auto; padding: 2rem 1.25rem;
  color: #1d1d1f; background: #fafafa; line-height: 1.55;
}
h1 { font-size: 1.75rem; margin: 0 0 .25rem; }
h2 { font-size: 1.15rem; margin: 1.5rem 0 .75rem; padding-bottom: .35rem; border-bottom: 1px solid #e5e5e7; }
.meta { color: #6e6e73; font-size: .9rem; margin-bottom: 1rem; }
.verification-summary { background: #f0f7ee; border-left: 3px solid #34a853; padding: .5rem .75rem; border-radius: 4px; }
.top-5 { background: white; padding: 1rem 1.25rem; border-radius: 8px; box-shadow: 0 1px 2px rgba(0,0,0,.04); }
.top-5 h2 { margin-top: 0; border-color: #d1d1d6; }
section.domain { margin-top: 1rem; }
details.insight {
  background: white; padding: .75rem 1rem; border-radius: 6px;
  border: 1px solid #e5e5e7; margin: .5rem 0;
}
details.insight[open] { border-color: #cdcdd1; }
details.insight summary { cursor: pointer; list-style: none; }
details.insight summary::-webkit-details-marker { display: none; }
.insight-body { margin-top: .5rem; padding-top: .5rem; border-top: 1px dashed #e5e5e7; }
.evidence { margin: 0 0 .5rem; color: #3a3a3c; }
.quote { margin: .5rem 0; padding: .5rem .75rem; border-left: 3px solid #d1d1d6; color: #515154; font-style: italic; font-size: .92rem; }
.tag { font-size: 1rem; margin-right: .25rem; }
.headline { font-weight: 600; }
.confidence, .verdict { display: inline-block; font-size: .75rem; padding: .1rem .4rem; border-radius: 10px; margin-left: .25rem; }
.confidence-high { background: #e7f4ec; color: #1e7d3a; }
.confidence-medium { background: #fff3e0; color: #8a5a00; }
.confidence-low { background: #fde7e9; color: #a52a2a; }
.confidence-low ~ * .evidence, details.confidence-low .evidence { color: #6e6e73; }
.verdict-verified { background: #e7f4ec; color: #1e7d3a; }
.verdict-inferred { background: #eef0fa; color: #2a4cb0; }
.verdict-not-supported { background: #fde7e9; color: #a52a2a; }
.dead-link { color: #a52a2a; }
ul.sources { margin: .25rem 0; padding-left: 1.25rem; font-size: .88rem; }
ul.sources a { color: #0070c9; text-decoration: none; }
ul.sources a:hover { text-decoration: underline; }
details.gaps { margin-top: .5rem; font-size: .85rem; color: #6e6e73; }
details.gaps summary { cursor: pointer; }
.contradictions { margin-top: 2rem; padding: 1rem 1.25rem; background: #fff7ed; border-radius: 8px; }
.contradictions h2 { border-color: #fed7aa; margin-top: 0; }
@media print {
  body { background: white; max-width: none; padding: .5rem; font-size: 11pt; }
  details { break-inside: avoid; }
  details:not([open]) > *:not(summary) { display: revert !important; }
  details > summary { list-style: none; }
}
"""


def render_brief(brief: Brief) -> str:
    """Build the full HTML document."""
    focus_line = f'<p class="meta">Focus: {esc(brief.focus)}</p>' if brief.focus else ""
    domains_html = "".join(render_domain_block(b) for b in brief.domains)
    warnings_html = ""
    if brief.warnings:
        items = "".join(f"<li>{esc(w)}</li>" for w in brief.warnings)
        warnings_html = (
            f'<details class="warnings"><summary>Warnings ({len(brief.warnings)})</summary><ul>{items}</ul></details>'
        )
    return (
        "<!doctype html>\n"
        '<html lang="en">\n'
        "<head>\n"
        '<meta charset="utf-8">\n'
        '<meta name="viewport" content="width=device-width, initial-scale=1">\n'
        f"<title>{esc(brief.company)} — research brief</title>\n"
        f"<style>{CSS}</style>\n"
        "</head>\n"
        "<body>\n"
        "<header>\n"
        f"<h1>{esc(brief.company)}</h1>\n"
        f'<p class="meta">Generated {esc(brief.generated_at)}</p>\n'
        f"{focus_line}\n"
        f"{render_verification_summary(brief.verification_summary)}\n"
        "</header>\n"
        f"{render_top_5_section(brief.top_5)}\n"
        f"{domains_html}\n"
        f"{render_contradictions_footer(brief.cross_domain_contradictions)}\n"
        f"{warnings_html}\n"
        "</body>\n"
        "</html>\n"
    )


# ---- Top-5 + verification merge -----------------------------------------------------------------


def attach_verifications(insights: list[Insight], verifications: list[dict[str, Any]]) -> None:
    """Apply verifier verdicts onto matching insights (by id)."""
    by_id = {str(v.get("insight_id", "")): v for v in verifications if isinstance(v, dict)}
    for ins in insights:
        v = by_id.get(ins.id)
        if not v:
            continue
        verdict = str(v.get("verdict", "")).lower()
        if verdict in VERDICT_BADGE:
            ins.verdict = verdict
        quote = v.get("evidence_quote")
        if isinstance(quote, str) and quote:
            ins.verdict_quote = quote


def slugify(s: str) -> str:
    s = s.lower().strip()
    s = re.sub(r"[^a-z0-9]+", "-", s).strip("-")
    return s or "company"


# ---- CLI ---------------------------------------------------------------------------------------


def load_json(path: Path | None) -> Any:
    if not path:
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e:
        print(f"render_brief: failed to load {path}: {e}", file=sys.stderr)
        return None


def build_brief(
    *,
    company: str,
    focus: str,
    domains_payload: list[dict[str, Any]] | None,
    synthesis_payload: dict[str, Any] | None,
    verifier_payload: dict[str, Any] | None,
    skip_head_check: bool = False,
) -> Brief:
    brief = Brief(
        company=company,
        focus=focus,
        generated_at=datetime.datetime.now(datetime.UTC).strftime("%Y-%m-%d %H:%M UTC"),
    )

    if domains_payload:
        for raw in domains_payload:
            block = parse_domain_block(raw)
            if block is None:
                brief.warnings.append("dropped a malformed domain JSON block")
                continue
            brief.domains.append(block)
    if not brief.domains:
        brief.warnings.append("no valid domain blocks supplied")

    all_insights: list[Insight] = []
    for b in brief.domains:
        all_insights.extend(b.insights)

    if synthesis_payload:
        for ins_raw in synthesis_payload.get("top_5") or []:
            ins = parse_insight(ins_raw, str(ins_raw.get("domain", "")))
            if ins is None:
                brief.warnings.append("synthesis returned a malformed Top-5 entry")
                continue
            ins.selection_reason = ins_raw.get("selection_reason")
            brief.top_5.append(ins)
        for c_raw in synthesis_payload.get("cross_domain_contradictions") or []:
            c = parse_insight(c_raw, "synthesis")
            if c is not None:
                c.tag = "contradiction"
                brief.cross_domain_contradictions.append(c)

    all_urls: list[str] = []
    for collection in (all_insights, brief.top_5, brief.cross_domain_contradictions):
        for ins in collection:
            for s in ins.sources:
                if is_safe_url(s.url):
                    all_urls.append(s.url)
    if all_urls and not skip_head_check:
        liveness = head_check_many(list(set(all_urls)))
        for collection in (all_insights, brief.top_5, brief.cross_domain_contradictions):
            for ins in collection:
                for s in ins.sources:
                    s.alive = liveness.get(s.url, True)

    if verifier_payload:
        verifications = verifier_payload.get("verifications") or []
        attach_verifications(brief.top_5, verifications)
        attach_verifications(all_insights, verifications)
        summary = verifier_payload.get("summary")
        if isinstance(summary, dict):
            brief.verification_summary = {k: int(v) for k, v in summary.items() if isinstance(v, int)}

    for ins in all_insights:
        apply_confidence_downgrades(ins)
    for ins in brief.top_5:
        apply_confidence_downgrades(ins)

    return brief


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Render a research-company brief to HTML.")
    parser.add_argument("--company", required=True, help="Target company name (will appear as the brief title).")
    parser.add_argument("--focus", default="", help="Optional role/angle the candidate is interviewing for.")
    parser.add_argument(
        "--domains-json", type=Path, help="Path to JSON file containing a list of 9 domain JSON objects."
    )
    parser.add_argument("--synthesis-json", type=Path, help="Path to JSON file from synthesis-agent.")
    parser.add_argument("--verifier-json", type=Path, help="Path to JSON file from verifier.")
    parser.add_argument("--output", type=Path, required=True, help="Output HTML path.")
    parser.add_argument("--skip-head-check", action="store_true", help="Skip URL liveness checks (fast for dev).")
    args = parser.parse_args(argv)

    domains_payload = load_json(args.domains_json)
    if domains_payload is not None and not isinstance(domains_payload, list):
        print(
            f"render_brief: --domains-json must contain a JSON array, got {type(domains_payload).__name__}",
            file=sys.stderr,
        )
        return 2
    synthesis_payload = load_json(args.synthesis_json)
    verifier_payload = load_json(args.verifier_json)

    brief = build_brief(
        company=args.company,
        focus=args.focus,
        domains_payload=domains_payload,
        synthesis_payload=synthesis_payload,
        verifier_payload=verifier_payload,
        skip_head_check=args.skip_head_check,
    )

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(render_brief(brief), encoding="utf-8")

    print(
        json.dumps(
            {
                "ok": True,
                "output": str(args.output),
                "domains_rendered": len(brief.domains),
                "top_5_count": len(brief.top_5),
                "warnings": brief.warnings,
            }
        )
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
