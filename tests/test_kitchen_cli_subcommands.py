"""Tests for the kitchen_cli subcommands added in PR-1.11.

The verify subcommand has its own test file (test_kitchen_cli.py). This file
exercises the rest of the surface (search/scrape/funding/people/tech/traffic/available).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "lib"))

import kitchen_cli


def test_available_exits_0_when_reachable(capsys: pytest.CaptureFixture[str]) -> None:
    with patch.object(kitchen_cli, "ServiceClient") as mock_cls:
        mock_cls.return_value.is_available.return_value = True
        rc = kitchen_cli.main(["available"])
    assert rc == 0
    assert json.loads(capsys.readouterr().out)["available"] is True


def test_available_exits_1_when_unreachable(capsys: pytest.CaptureFixture[str]) -> None:
    with patch.object(kitchen_cli, "ServiceClient") as mock_cls:
        mock_cls.return_value.is_available.return_value = False
        rc = kitchen_cli.main(["available"])
    assert rc == 1
    assert json.loads(capsys.readouterr().out)["available"] is False


def test_search_invokes_client_search(capsys: pytest.CaptureFixture[str]) -> None:
    with patch.object(kitchen_cli, "ServiceClient") as mock_cls:
        mock_cls.return_value.is_available.return_value = True
        mock_cls.return_value.search.return_value = {"results": [{"title": "X"}]}
        rc = kitchen_cli.main(["search", "--query", "Stripe", "--limit", "3"])
    assert rc == 0
    assert json.loads(capsys.readouterr().out) == {"results": [{"title": "X"}]}
    mock_cls.return_value.search.assert_called_once_with("Stripe", limit=3)


def test_scrape_invokes_client_scrape(capsys: pytest.CaptureFixture[str]) -> None:
    with patch.object(kitchen_cli, "ServiceClient") as mock_cls:
        mock_cls.return_value.is_available.return_value = True
        mock_cls.return_value.scrape.return_value = {"text": "Page contents"}
        rc = kitchen_cli.main(["scrape", "--url", "https://stripe.com"])
    assert rc == 0
    mock_cls.return_value.scrape.assert_called_once_with("https://stripe.com")


def test_funding_invokes_client_funding(capsys: pytest.CaptureFixture[str]) -> None:
    with patch.object(kitchen_cli, "ServiceClient") as mock_cls:
        mock_cls.return_value.is_available.return_value = True
        mock_cls.return_value.funding.return_value = {"is_public": True}
        rc = kitchen_cli.main(["funding", "--company", "AAPL"])
    assert rc == 0
    mock_cls.return_value.funding.assert_called_once_with("AAPL")


def test_people_invokes_client_people(capsys: pytest.CaptureFixture[str]) -> None:
    with patch.object(kitchen_cli, "ServiceClient") as mock_cls:
        mock_cls.return_value.is_available.return_value = True
        mock_cls.return_value.people.return_value = {"headcount_estimate": 8500}
        rc = kitchen_cli.main(["people", "--company", "Stripe"])
    assert rc == 0
    mock_cls.return_value.people.assert_called_once_with("Stripe")


def test_tech_forwards_company_when_provided(capsys: pytest.CaptureFixture[str]) -> None:
    with patch.object(kitchen_cli, "ServiceClient") as mock_cls:
        mock_cls.return_value.is_available.return_value = True
        mock_cls.return_value.tech.return_value = {"technologies": []}
        rc = kitchen_cli.main(["tech", "--primary-url", "https://stripe.com", "--company", "Stripe"])
    assert rc == 0
    mock_cls.return_value.tech.assert_called_once_with("https://stripe.com", company="Stripe")


def test_tech_company_defaults_to_none(capsys: pytest.CaptureFixture[str]) -> None:
    with patch.object(kitchen_cli, "ServiceClient") as mock_cls:
        mock_cls.return_value.is_available.return_value = True
        mock_cls.return_value.tech.return_value = {"technologies": []}
        rc = kitchen_cli.main(["tech", "--primary-url", "https://stripe.com"])
    assert rc == 0
    mock_cls.return_value.tech.assert_called_once_with("https://stripe.com", company=None)


def test_traffic_invokes_client_traffic(capsys: pytest.CaptureFixture[str]) -> None:
    with patch.object(kitchen_cli, "ServiceClient") as mock_cls:
        mock_cls.return_value.is_available.return_value = True
        mock_cls.return_value.traffic.return_value = {"top_keywords": ["stripe payments"]}
        rc = kitchen_cli.main(["traffic", "--domain", "stripe.com"])
    assert rc == 0
    mock_cls.return_value.traffic.assert_called_once_with("stripe.com")


@pytest.mark.parametrize(
    "cmd_args",
    [
        ["search", "--query", "x"],
        ["scrape", "--url", "https://x.com"],
        ["funding", "--company", "X"],
        ["people", "--company", "X"],
        ["tech", "--primary-url", "https://x.com"],
        ["traffic", "--domain", "x.com"],
    ],
)
def test_all_subcommands_exit_1_when_unreachable(capsys: pytest.CaptureFixture[str], cmd_args: list[str]) -> None:
    with patch.object(kitchen_cli, "ServiceClient") as mock_cls:
        mock_cls.return_value.is_available.return_value = False
        rc = kitchen_cli.main(cmd_args)
    assert rc == 1
    assert "not reachable" in capsys.readouterr().err


@pytest.mark.parametrize(
    "cmd_args,method",
    [
        (["search", "--query", "x"], "search"),
        (["scrape", "--url", "https://x.com"], "scrape"),
        (["funding", "--company", "X"], "funding"),
        (["people", "--company", "X"], "people"),
        (["tech", "--primary-url", "https://x.com"], "tech"),
        (["traffic", "--domain", "x.com"], "traffic"),
    ],
)
def test_all_subcommands_exit_2_when_client_returns_none(
    capsys: pytest.CaptureFixture[str], cmd_args: list[str], method: str
) -> None:
    """If the kitchen returns None (5xx or unexpected), exit 2 with error JSON on stderr."""
    with patch.object(kitchen_cli, "ServiceClient") as mock_cls:
        mock_cls.return_value.is_available.return_value = True
        getattr(mock_cls.return_value, method).return_value = None
        rc = kitchen_cli.main(cmd_args)
    assert rc == 2
