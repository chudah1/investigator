from typing import Any

import pytest

from database import Database
from investigation_tools import build_tools
from repository import Repository
from seed import seed_database


@pytest.fixture
def repository(tmp_path) -> Repository:
    db_path = tmp_path / "investigator.db"
    seed_database(db_path)
    return Repository(Database(str(db_path)))


@pytest.fixture
def tools(repository: Repository) -> dict[str, Any]:
    return {tool.name: tool for tool in build_tools(repository)}


def test_build_tools_exposes_expected_tools(tools: dict[str, Any]) -> None:
    assert set(tools) == {
        "get_job",
        "list_reports",
        "get_delivery_attempts",
        "get_recipient_receipts",
        "get_destination_config",
    }


def test_get_job_tool_returns_structured_job(
    tools: dict[str, Any],
) -> None:
    result = tools["get_job"].invoke({"job_id": "job-001"})

    assert result == {
        "job_id": "job-001",
        "expected_reports": ["report-A", "report-B", "report-C"],
    }


def test_get_job_tool_returns_none_for_unknown_job(
    tools: dict[str, Any],
) -> None:
    result = tools["get_job"].invoke({"job_id": "missing-job"})

    assert result is None


def test_list_reports_tool_returns_structured_reports(
    tools: dict[str, Any],
) -> None:
    result = tools["list_reports"].invoke({"job_id": "job-001"})

    assert [report["report_id"] for report in result] == [
        "report-A",
        "report-B",
        "report-C",
    ]
    assert result[1]["delivery_status"] == "timed_out"


def test_delivery_attempt_tool_returns_json_compatible_timestamp(
    tools: dict[str, Any],
) -> None:
    result = tools["get_delivery_attempts"].invoke(
        {"report_id": "report-B"}
    )

    assert result[0]["attempt_id"] == "attempt-B-1"
    assert result[0]["outcome"] == "timed_out"
    assert result[0]["timestamp"] == "2026-09-28T09:01:00Z"


def test_receipt_tool_exposes_delivery_despite_sender_timeout(
    tools: dict[str, Any],
) -> None:
    result = tools["get_recipient_receipts"].invoke(
        {"report_id": "report-B"}
    )

    assert result[0]["receipt_id"] == "receipt-B-1"
    assert result[0]["delivery_key"] == "delivery-job-001-report-B"


def test_destination_config_tool_preserves_missing_evidence(
    tools: dict[str, Any],
) -> None:
    result = tools["get_destination_config"].invoke(
        {"destination_id": "destination-C"}
    )

    assert result is None
