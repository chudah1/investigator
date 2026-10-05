from langchain.tools import tool
from typing import Any

from repository import Repository


def build_tools(repository: Repository) -> list[Any]:
    @tool
    def get_job(job_id: str) -> dict[str, Any] | None:
        """Get a job and the report IDs expected for it."""
        job = repository.get_job(job_id)
        return job.model_dump(mode="json") if job else None

    @tool
    def list_reports(job_id: str) -> list[dict[str, Any]]:
        """List the sender's report records for a job."""
        return [
            report.model_dump(mode="json")
            for report in repository.list_reports(job_id)
        ]

    @tool
    def get_delivery_attempts(
        report_id: str,
    ) -> list[dict[str, Any]]:
        """Get all sender delivery attempts recorded for a report."""
        return [
            attempt.model_dump(mode="json")
            for attempt in repository.get_delivery_attempts(report_id)
        ]

    @tool
    def get_recipient_receipts(
        report_id: str,
    ) -> list[dict[str, Any]]:
        """Get receipts proving that the recipient accepted a report."""
        return [
            receipt.model_dump(mode="json")
            for receipt in repository.get_recipient_receipts(report_id)
        ]

    @tool
    def get_destination_config(
        destination_id: str,
    ) -> dict[str, Any] | None:
        """Get the current delivery configuration for a destination."""
        config = repository.get_destination_config(destination_id)
        return config.model_dump(mode="json") if config else None

    return [
        get_job,
        list_reports,
        get_delivery_attempts,
        get_recipient_receipts,
        get_destination_config,
    ]
