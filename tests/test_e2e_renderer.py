"""End-to-end smoke test for the renderer pipeline.

Drives `lib/render_brief.py` as a subprocess against realistic 9-domain fixtures
(`tests/fixtures/*.stripe.json`) and validates the output HTML has every piece
the orchestrator promises in SKILL.md's exit contract.

This is the closest we can get to "the whole skill works" without spawning real
Claude Code agents (which need MCP servers and API keys CI doesn't have).
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
RENDERER = REPO_ROOT / "lib" / "render_brief.py"
FIXTURES = REPO_ROOT / "tests" / "fixtures"


@pytest.fixture
def brief_path(tmp_path: Path) -> Path:
    return tmp_path / "stripe_brief.html"


def _run(brief_path: Path) -> tuple[subprocess.CompletedProcess[str], str]:
    proc = subprocess.run(
        [
            sys.executable,
            str(RENDERER),
            "--company",
            "Stripe",
            "--focus",
            "applying for senior product manager",
            "--domains-json",
            str(FIXTURES / "domains.stripe.json"),
            "--synthesis-json",
            str(FIXTURES / "synthesis.stripe.json"),
            "--verifier-json",
            str(FIXTURES / "verifier.stripe.json"),
            "--output",
            str(brief_path),
            "--skip-head-check",
        ],
        capture_output=True,
        text=True,
        check=False,
        timeout=30,
    )
    html = brief_path.read_text(encoding="utf-8") if brief_path.exists() else ""
    return proc, html


def test_renderer_exits_zero_with_valid_inputs(brief_path: Path) -> None:
    proc, _ = _run(brief_path)
    assert proc.returncode == 0, f"stderr: {proc.stderr}"


def test_renderer_emits_summary_json_on_stdout(brief_path: Path) -> None:
    proc, _ = _run(brief_path)
    summary = json.loads(proc.stdout)
    assert summary["ok"] is True
    assert summary["domains_rendered"] == 9
    assert summary["top_5_count"] == 5


def test_html_has_doctype_and_title(brief_path: Path) -> None:
    _run(brief_path)
    html = brief_path.read_text()
    assert html.startswith("<!doctype html>")
    assert "<title>Stripe — research brief</title>" in html


def test_html_has_all_9_domain_sections(brief_path: Path) -> None:
    _run(brief_path)
    html = brief_path.read_text()
    expected_labels = [
        ">Market <",
        ">Sales <",
        ">Product <",
        ">R&amp;D / Tech <",  # & is escaped
        ">Traffic &amp; Demand <",
        ">People <",
        ">Hiring <",
        ">Customers &amp; Feedback <",
        ">Money <",
    ]
    missing = [label for label in expected_labels if label not in html]
    assert not missing, f"missing domain headings: {missing}"


def test_html_has_top_5_section_with_5_items(brief_path: Path) -> None:
    _run(brief_path)
    html = brief_path.read_text()
    assert 'class="top-5"' in html
    # The Top 5 section's <details> elements all have `open`; count them.
    top5_section = re.search(r'<section class="top-5">(.*?)</section>', html, re.DOTALL)
    assert top5_section is not None
    open_details = re.findall(r"<details[^>]*\bopen\b", top5_section.group(1))
    assert len(open_details) == 5


def test_html_has_verification_badges(brief_path: Path) -> None:
    _run(brief_path)
    html = brief_path.read_text()
    assert "verdict-verified" in html
    assert "verdict-inferred" in html
    # No insight in our fixture is "not-supported", but the CSS class should be available
    assert "verification-summary" in html


def test_html_has_cross_domain_contradictions_footer(brief_path: Path) -> None:
    _run(brief_path)
    html = brief_path.read_text()
    assert "Cross-domain contradictions" in html
    assert "synthesis-contradiction-1" not in html  # ID stays internal; headline is what shows
    assert "Headcount" in html  # part of the contradiction headline


def test_html_does_not_contain_raw_script_tags(brief_path: Path) -> None:
    """Double-check there's no XSS surface even when fixture content has <,>,&."""
    _run(brief_path)
    html = brief_path.read_text()
    # The only <script> in the file should be... none. We have inline CSS, no JS.
    assert "<script" not in html.lower()


def test_html_has_no_inline_javascript_event_handlers(brief_path: Path) -> None:
    _run(brief_path)
    html = brief_path.read_text()
    # Any onload= / onclick= / onerror= would be a sign of XSS leak
    assert not re.search(r"\bon(load|click|error|mouseover|focus)\s*=", html, re.IGNORECASE)


def test_renderer_handles_partial_inputs_gracefully(tmp_path: Path) -> None:
    """If verifier didn't run (e.g. --debug mode aborted early), renderer should still produce output."""
    out = tmp_path / "partial.html"
    proc = subprocess.run(
        [
            sys.executable,
            str(RENDERER),
            "--company",
            "PartialCo",
            "--domains-json",
            str(FIXTURES / "domains.stripe.json"),
            "--output",
            str(out),
            "--skip-head-check",
        ],
        capture_output=True,
        text=True,
        check=False,
        timeout=15,
    )
    assert proc.returncode == 0
    assert out.exists()
    html = out.read_text()
    assert "PartialCo" in html
    # No verifier ran — no verification summary
    # (The summary section is empty when verifier didn't run, which is fine)
