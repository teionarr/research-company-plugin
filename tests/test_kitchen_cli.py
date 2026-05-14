"""Tests for the kitchen_cli — agents call this via Bash."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "lib"))

import kitchen_cli


def test_verify_exits_1_when_service_unavailable(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    insights_file = tmp_path / "insights.json"
    insights_file.write_text(json.dumps([{"id": "a"}]))

    with patch.object(kitchen_cli, "ServiceClient") as mock_cls:
        mock_cls.return_value.is_available.return_value = False
        rc = kitchen_cli.main(["verify", "--insights-file", str(insights_file)])
    assert rc == 1
    captured = capsys.readouterr()
    assert "not reachable" in captured.err


def test_verify_emits_kitchen_response_on_success(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    insights_file = tmp_path / "insights.json"
    insights_file.write_text(
        json.dumps(
            [
                {
                    "id": "x",
                    "domain": "sales",
                    "headline": "Pricing hides per-seat above 50 users",
                    "evidence": "...",
                    "sources": [{"title": "p", "url": "https://stripe.com/pricing"}],
                    "confidence": "high",
                }
            ]
        )
    )

    kitchen_response = {
        "verifications": [{"insight_id": "x", "suggested_confidence": "medium", "issues": []}],
        "cross_domain_contradictions": [],
        "summary": {"insights_verified": 1},
    }
    with patch.object(kitchen_cli, "ServiceClient") as mock_cls:
        mock_cls.return_value.is_available.return_value = True
        mock_cls.return_value.verify.return_value = kitchen_response
        rc = kitchen_cli.main(["verify", "--insights-file", str(insights_file), "--target-domain", "stripe.com"])
    assert rc == 0
    out = json.loads(capsys.readouterr().out)
    assert out == kitchen_response
    # Verify the kitchen was called with the right args
    mock_cls.return_value.verify.assert_called_once()
    _, kwargs = mock_cls.return_value.verify.call_args
    assert kwargs["target_domain"] == "stripe.com"
    assert kwargs["skip_url_check"] is False


def test_verify_accepts_insights_envelope(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """Caller can pass `{"insights": [...]}` instead of a bare array — ergonomics."""
    insights_file = tmp_path / "insights.json"
    insights_file.write_text(
        json.dumps({"insights": [{"id": "x", "domain": "y", "headline": "h", "evidence": "e", "sources": []}]})
    )

    with patch.object(kitchen_cli, "ServiceClient") as mock_cls:
        mock_cls.return_value.is_available.return_value = True
        mock_cls.return_value.verify.return_value = {
            "verifications": [],
            "cross_domain_contradictions": [],
            "summary": {},
        }
        rc = kitchen_cli.main(["verify", "--insights-file", str(insights_file)])
    assert rc == 0
    # The wrapper unwrapped {"insights": [...]} → list
    args, _ = mock_cls.return_value.verify.call_args
    insights_passed = args[0]
    assert isinstance(insights_passed, list)
    assert insights_passed[0]["id"] == "x"


def test_verify_exits_2_on_malformed_json(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    insights_file = tmp_path / "insights.json"
    insights_file.write_text("not valid {{ json")

    with patch.object(kitchen_cli, "ServiceClient") as mock_cls:
        mock_cls.return_value.is_available.return_value = True
        rc = kitchen_cli.main(["verify", "--insights-file", str(insights_file)])
    assert rc == 2


def test_verify_exits_2_when_kitchen_returns_none(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    insights_file = tmp_path / "insights.json"
    insights_file.write_text(json.dumps([{"id": "x"}]))

    with patch.object(kitchen_cli, "ServiceClient") as mock_cls:
        mock_cls.return_value.is_available.return_value = True
        mock_cls.return_value.verify.return_value = None
        rc = kitchen_cli.main(["verify", "--insights-file", str(insights_file)])
    assert rc == 2
