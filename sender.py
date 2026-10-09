import httpx

from models import DeliveryAttempt, Report
from repository import Repository


class Sender:
    def __init__(
        self,
        repository: Repository,
        http_client: httpx.Client,
    ) -> None:
        self.repository = repository
        self.http_client = http_client

    def deliver(self, report: Report) -> DeliveryAttempt:
        destination = self.repository.get_destination_config(
            report.destination_id
        )
        if destination is None:
            raise ValueError(
                f"Destination {report.destination_id!r} is not configured."
            )

        delivery_key = f"delivery-{report.job_id}-{report.report_id}"
        try:
            response = self.http_client.post(
                destination.endpoint_url,
                json={
                    "report_id": report.report_id,
                    "delivery_key": delivery_key,
                },
            )
        except httpx.ReadTimeout:
            return self.repository.create_delivery_attempt(
                report_id=report.report_id,
                outcome="timed_out",
                error="Recipient acknowledgement timed out",
            )

        response.raise_for_status()

        return self.repository.create_delivery_attempt(
            report_id=report.report_id,
            outcome="succeeded",
        )
