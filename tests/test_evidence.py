import pytest

from database import Database
from evidence import collect_job_evidence
from models import JobEvidence, ReportEvidence
from repository import Repository
from seed import seed_database


@pytest.fixture
def repository(tmp_path) -> Repository:
    db_path = tmp_path / "investigator.db"
    seed_database(db_path)
    return Repository(Database(str(db_path)))


def test_collect_job_evidence_returns_none_for_unknown_job(
    repository: Repository,
) -> None:
    assert collect_job_evidence(repository, "missing-job") is None


def test_collect_job_evidence_assembles_all_report_evidence(
    repository: Repository,
) -> None:
    evidence = collect_job_evidence(repository, "job-001")

    assert isinstance(evidence, JobEvidence)
    assert evidence.job.expected_reports == ["report-A", "report-B", "report-C"]
    assert [item.report.report_id for item in evidence.reports] == [
        "report-A",
        "report-B",
        "report-C",
    ]


def test_collected_evidence_preserves_the_three_distinct_cases(
    repository: Repository,
) -> None:
    evidence = collect_job_evidence(repository, "job-001")
    assert evidence is not None

    reports: dict[str, ReportEvidence] = {
        item.report.report_id: item for item in evidence.reports
    }

    report_a = reports["report-A"]
    assert report_a.report.delivery_status == "succeeded"
    assert len(report_a.recipient_receipts) == 1
    assert report_a.destination_config is not None

    report_b = reports["report-B"]
    assert report_b.report.delivery_status == "timed_out"
    assert len(report_b.recipient_receipts) == 1
    assert report_b.destination_config is not None

    report_c = reports["report-C"]
    assert report_c.report.delivery_status == "failed"
    assert report_c.recipient_receipts == []
    assert report_c.destination_config is None
