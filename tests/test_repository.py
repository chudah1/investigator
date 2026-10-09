from datetime import datetime

import pytest

from database import Database
from repository import Repository
from seed import seed_database


@pytest.fixture
def repository(tmp_path) -> Repository:
    db_path = tmp_path / "investigator.db"
    seed_database(db_path)
    return Repository(Database(str(db_path)))


def test_get_job_returns_expected_report_ids(repository: Repository) -> None:
    job = repository.get_job("job-001")

    assert job is not None
    assert job.job_id == "job-001"
    assert job.expected_reports == ["report-A", "report-B", "report-C"]


def test_get_job_returns_none_when_job_does_not_exist(
    repository: Repository,
) -> None:
    assert repository.get_job("missing-job") is None


def test_get_job_supports_a_job_with_no_expected_reports(tmp_path) -> None:
    db_path = tmp_path / "investigator.db"
    database = Database(str(db_path))
    database.initialize()

    connection = database.get_connection()
    try:
        with connection:
            connection.execute(
                "INSERT INTO jobs (job_id) VALUES (?)",
                ("empty-job",),
            )
    finally:
        connection.close()

    job = Repository(database).get_job("empty-job")

    assert job is not None
    assert job.expected_reports == []


def test_list_reports_returns_all_reports_in_stable_order(
    repository: Repository,
) -> None:
    reports = repository.list_reports("job-001")

    assert [report.report_id for report in reports] == [
        "report-A",
        "report-B",
        "report-C",
    ]
    assert reports[0].destination_id == "destination-A"
    assert reports[0].delivery_status == "succeeded"
    assert reports[1].delivery_status == "timed_out"
    assert reports[2].delivery_status == "failed"


def test_list_reports_returns_empty_list_for_unknown_job(
    repository: Repository,
) -> None:
    assert repository.list_reports("missing-job") == []


def test_get_delivery_attempts_returns_typed_evidence(
    repository: Repository,
) -> None:
    attempts = repository.get_delivery_attempts("report-B")

    assert len(attempts) == 1
    assert attempts[0].attempt_id == "attempt-B-1"
    assert attempts[0].outcome == "timed_out"
    assert attempts[0].error == "Recipient acknowledgement timed out"
    assert isinstance(attempts[0].timestamp, datetime)
    assert attempts[0].timestamp.tzinfo is not None


def test_get_delivery_attempts_returns_empty_list_when_none_exist(
    repository: Repository,
) -> None:
    assert repository.get_delivery_attempts("missing-report") == []


def test_get_recipient_receipts_distinguishes_receipt_from_no_receipt(
    repository: Repository,
) -> None:
    report_b_receipts = repository.get_recipient_receipts("report-B")

    assert len(report_b_receipts) == 1
    assert report_b_receipts[0].receipt_id == "receipt-B-1"
    assert report_b_receipts[0].delivery_key == "delivery-job-001-report-B"
    assert isinstance(report_b_receipts[0].receipt_timestamp, datetime)
    assert repository.get_recipient_receipts("report-C") == []


def test_get_destination_config_distinguishes_present_from_missing(
    repository: Repository,
) -> None:
    configured = repository.get_destination_config("destination-A")

    assert configured is not None
    assert configured.destination_id == "destination-A"
    assert configured.endpoint_url == "https://recipient.example/deliveries"
    assert configured.enabled is True
    assert repository.get_destination_config("destination-C") is None
