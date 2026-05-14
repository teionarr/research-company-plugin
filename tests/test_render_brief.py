"""Tests for render_brief — focused on the security-relevant edges (escaping, URL validation,
schema strictness) plus core happy-path rendering."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

# Make lib importable regardless of where pytest is invoked from
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "lib"))

import render_brief as rb

# ---- URL safety --------------------------------------------------------------


@pytest.mark.parametrize(
    "url",
    [
        "https://example.com",
        "http://example.com/path?q=1",
        "https://example.com:8080/x",
    ],
)
def test_is_safe_url_accepts_http_https(url: str) -> None:
    assert rb.is_safe_url(url)


@pytest.mark.parametrize(
    "url",
    [
        "javascript:alert(1)",
        "data:text/html,<script>alert(1)</script>",
        "file:///etc/passwd",
        "ftp://example.com",
        "vbscript:msgbox()",
        "",
        "not a url",
        "//no-scheme.com",
    ],
)
def test_is_safe_url_rejects_dangerous_schemes(url: str) -> None:
    assert not rb.is_safe_url(url)


def test_is_safe_url_rejects_non_string() -> None:
    assert not rb.is_safe_url(None)  # type: ignore[arg-type]
    assert not rb.is_safe_url(123)  # type: ignore[arg-type]


# ---- HTML escaping -----------------------------------------------------------


def test_esc_escapes_html_entities() -> None:
    assert rb.esc("<script>alert(1)</script>") == "&lt;script&gt;alert(1)&lt;/script&gt;"


def test_esc_escapes_quotes_for_attributes() -> None:
    out = rb.esc('" onload="alert(1)')
    assert '"' not in out
    assert "&quot;" in out


def test_esc_handles_non_string() -> None:
    assert rb.esc(123) == "123"
    assert rb.esc(None) == "None"


def test_render_source_drops_unsafe_url() -> None:
    s = rb.Source(title="evil", url="javascript:alert(1)")
    assert rb.render_source(s) == ""


def test_render_source_escapes_title_and_url() -> None:
    s = rb.Source(title="<img src=x onerror=alert(1)>", url="https://example.com/?q=<script>")
    out = rb.render_source(s)
    assert "<script>" not in out
    assert "<img" not in out
    assert "&lt;script&gt;" in out
    assert "&lt;img" in out


def test_render_source_marks_dead_link() -> None:
    s = rb.Source(title="x", url="https://example.com", alive=False)
    assert "dead-link" in rb.render_source(s)


# ---- Insight parsing ---------------------------------------------------------


def _valid_insight_dict() -> dict:
    return {
        "id": "sales-1",
        "tag": "weak",
        "headline": "Pricing page hides per-seat costs above 50 seats",
        "evidence": "Pricing page renders 'Contact sales' for >50 users despite per-seat for smaller tiers.",
        "sources": [{"title": "Pricing page", "url": "https://example.com/pricing"}],
        "confidence": "high",
        "tools_used": ["WebFetch"],
    }


def test_parse_insight_happy_path() -> None:
    ins = rb.parse_insight(_valid_insight_dict(), "sales")
    assert ins is not None
    assert ins.tag == "weak"
    assert ins.confidence == "high"
    assert len(ins.sources) == 1


def test_parse_insight_drops_unknown_tag() -> None:
    raw = _valid_insight_dict() | {"tag": "amazing"}
    assert rb.parse_insight(raw, "sales") is None


def test_parse_insight_normalizes_unknown_confidence() -> None:
    raw = _valid_insight_dict() | {"confidence": "extreme"}
    ins = rb.parse_insight(raw, "sales")
    assert ins is not None
    assert ins.confidence == "medium"


def test_parse_insight_drops_unsafe_source_urls() -> None:
    raw = _valid_insight_dict() | {
        "sources": [
            {"title": "good", "url": "https://example.com"},
            {"title": "evil", "url": "javascript:alert(1)"},
        ]
    }
    ins = rb.parse_insight(raw, "sales")
    assert ins is not None
    assert len(ins.sources) == 1
    assert ins.sources[0].url == "https://example.com"


def test_parse_insight_requires_headline() -> None:
    raw = _valid_insight_dict() | {"headline": "  "}
    assert rb.parse_insight(raw, "sales") is None


# ---- Domain block parsing ----------------------------------------------------


def test_parse_domain_block_drops_unknown_domain() -> None:
    assert rb.parse_domain_block({"domain": "made-up", "insights": []}) is None


def test_parse_domain_block_keeps_valid_insights() -> None:
    block = rb.parse_domain_block(
        {
            "domain": "sales",
            "insights": [_valid_insight_dict(), {"tag": "garbage"}, _valid_insight_dict()],
            "raw_facts": ["fact one", 42, "fact two"],
            "gaps": ["could not verify ARR"],
        }
    )
    assert block is not None
    assert len(block.insights) == 2
    # 42 is not a string and should be filtered
    assert block.raw_facts == ["fact one", "fact two"]


# ---- Confidence downgrade ----------------------------------------------------


def test_downgrade_high_confidence_when_all_sources_same_domain() -> None:
    ins = rb.Insight(
        id="x-1",
        tag="strong",
        headline="h",
        evidence="e",
        sources=[
            rb.Source(title="a", url="https://example.com/a"),
            rb.Source(title="b", url="https://example.com/b"),
        ],
        confidence="high",
    )
    rb.apply_confidence_downgrades(ins)
    assert ins.confidence == "medium"


def test_keep_high_confidence_when_sources_diverse() -> None:
    ins = rb.Insight(
        id="x-1",
        tag="strong",
        headline="h",
        evidence="e",
        sources=[
            rb.Source(title="a", url="https://example.com/a"),
            rb.Source(title="b", url="https://other.com/b"),
        ],
        confidence="high",
    )
    rb.apply_confidence_downgrades(ins)
    assert ins.confidence == "high"


def test_downgrade_to_low_when_all_sources_dead() -> None:
    ins = rb.Insight(
        id="x-1",
        tag="strong",
        headline="h",
        evidence="e",
        sources=[
            rb.Source(title="a", url="https://example.com/a", alive=False),
            rb.Source(title="b", url="https://other.com/b", alive=False),
        ],
        confidence="high",
    )
    rb.apply_confidence_downgrades(ins)
    assert ins.confidence == "low"


# ---- End-to-end render -------------------------------------------------------


def _sample_domains() -> list[dict]:
    return [
        {
            "domain": "sales",
            "insights": [_valid_insight_dict()],
            "raw_facts": ["headcount ~120"],
            "gaps": [],
        },
        {
            "domain": "money",
            "insights": [
                _valid_insight_dict()
                | {"id": "money-1", "tag": "opening", "headline": "Series B 6 weeks ago for EU expansion"}
            ],
            "raw_facts": ["headcount ~200"],
            "gaps": [],
        },
    ]


def _sample_synthesis() -> dict:
    return {
        "top_5": [
            _valid_insight_dict() | {"selection_reason": "weak insight required by constraint"},
        ],
        "cross_domain_contradictions": [
            _valid_insight_dict()
            | {
                "id": "synthesis-contradiction-1",
                "tag": "contradiction",
                "headline": "Headcount ~120 (people) vs ~200 (money)",
                "evidence": "Two domains report different headcounts.",
            }
        ],
    }


def _sample_verifier() -> dict:
    return {
        "verifications": [
            {
                "insight_id": "sales-1",
                "verdict": "verified",
                "evidence_quote": "Above 50 users, contact sales for pricing.",
                "checked_url": "https://example.com/pricing",
                "page_was_reachable": True,
            }
        ],
        "summary": {"verified_count": 1, "inferred_count": 0, "not_supported_count": 0},
    }


def test_build_brief_happy_path() -> None:
    brief = rb.build_brief(
        company="Acme",
        focus="head of growth",
        domains_payload=_sample_domains(),
        synthesis_payload=_sample_synthesis(),
        verifier_payload=_sample_verifier(),
        skip_head_check=True,
    )
    assert brief.company == "Acme"
    assert len(brief.domains) == 2
    assert len(brief.top_5) == 1
    assert len(brief.cross_domain_contradictions) == 1
    assert brief.top_5[0].verdict == "verified"
    assert brief.verification_summary["verified_count"] == 1


def test_render_brief_produces_valid_html_no_inline_script(tmp_path: Path) -> None:
    brief = rb.build_brief(
        company="Acme <script>alert(1)</script>",  # the company name itself tries injection
        focus="",
        domains_payload=_sample_domains(),
        synthesis_payload=_sample_synthesis(),
        verifier_payload=_sample_verifier(),
        skip_head_check=True,
    )
    html_out = rb.render_brief(brief)
    # No raw script anywhere
    assert "<script>" not in html_out
    assert "alert(1)" not in html_out or "&lt;script&gt;alert(1)" in html_out
    # Doctype + html structure
    assert html_out.startswith("<!doctype html>")
    assert "<title>" in html_out
    # Top-5 section is open by default
    assert 'class="top-5"' in html_out
    assert "open" in html_out  # at least one <details open> for top-5 items
    # Verification summary present
    assert "Verification" in html_out


def test_main_writes_file(tmp_path: Path) -> None:
    domains_path = tmp_path / "domains.json"
    syn_path = tmp_path / "syn.json"
    ver_path = tmp_path / "ver.json"
    out_path = tmp_path / "out.html"
    domains_path.write_text(json.dumps(_sample_domains()))
    syn_path.write_text(json.dumps(_sample_synthesis()))
    ver_path.write_text(json.dumps(_sample_verifier()))
    rc = rb.main(
        [
            "--company",
            "Acme",
            "--focus",
            "growth",
            "--domains-json",
            str(domains_path),
            "--synthesis-json",
            str(syn_path),
            "--verifier-json",
            str(ver_path),
            "--output",
            str(out_path),
            "--skip-head-check",
        ]
    )
    assert rc == 0
    assert out_path.exists()
    content = out_path.read_text()
    assert "Acme" in content
    assert "Top 5" in content


def test_slugify() -> None:
    assert rb.slugify("Stripe Inc") == "stripe-inc"
    assert rb.slugify("  Foo & Bar!  ") == "foo-bar"
    assert rb.slugify("") == "company"
    assert rb.slugify("---") == "company"
