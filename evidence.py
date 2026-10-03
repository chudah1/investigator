from models import JobEvidence, ReportEvidence
from repository import Repository


def collect_job_evidence(
    repository: Repository,
    job_id: str,
) -> JobEvidence | None:
    job = repository.get_job(job_id)
    if job is None:
        return None

    report_evidence: list[ReportEvidence] = []

    for report in repository.list_reports(job_id):
        report_evidence.append(
            ReportEvidence(
                report=report,
                delivery_attempts=repository.get_delivery_attempts(
                    report.report_id
                ),
                recipient_receipts=repository.get_recipient_receipts(
                    report.report_id
                ),
                destination_config=repository.get_destination_config(
                    report.destination_id
                ),
            )
        )

    return JobEvidence(job=job, reports=report_evidence)
