from database import Database
from models import (
    DeliveryAttempt,
    DestinationConfig,
    Job,
    RecipientReceipt,
    Report,
)


class Repository:
    def __init__(self, database: Database) -> None:
        self.database = database

    def get_job(self, job_id: str) -> Job | None:
        connection = self.database.get_connection()

        try:
            job_row = connection.execute(
                "SELECT job_id FROM jobs WHERE job_id = ?",
                (job_id,),
            ).fetchone()

            if job_row is None:
                return None

            report_rows = connection.execute(
                """
                SELECT report_id
                FROM expected_reports
                WHERE job_id = ?
                ORDER BY report_id
                """,
                (job_id,),
            ).fetchall()

            return Job(
                job_id=job_row["job_id"],
                expected_reports=[row["report_id"] for row in report_rows],
            )
        finally:
            connection.close()

    def list_reports(self, job_id: str) -> list[Report]:
        connection = self.database.get_connection()
        reports: list[Report] = []

        try:
            result = connection.execute(
                """
                SELECT report_id, job_id, destination_id, delivery_status
                FROM reports
                WHERE job_id = ?
                ORDER BY report_id
                """,
                (job_id,),
            ).fetchall()

            for row in result:
                report = Report(
                    report_id=row["report_id"],
                    job_id=row["job_id"],
                    destination_id=row["destination_id"],
                    delivery_status=row["delivery_status"],
                )

                reports.append(report)
        finally:
            connection.close()
        return reports

    def get_delivery_attempts(self, report_id: str) -> list[DeliveryAttempt]:
        connection = self.database.get_connection()

        try:
            rows = connection.execute(
                """
                SELECT attempt_id, report_id, timestamp, outcome, error
                FROM delivery_attempts
                WHERE report_id = ?
                ORDER BY timestamp, attempt_id
                """,
                (report_id,),
            ).fetchall()

            return [DeliveryAttempt.model_validate(dict(row)) for row in rows]
        finally:
            connection.close()

    def get_recipient_receipts(self, report_id: str) -> list[RecipientReceipt]:
        connection = self.database.get_connection()

        try:
            rows = connection.execute(
                """
                SELECT receipt_id, report_id, delivery_key, receipt_timestamp
                FROM recipient_receipts
                WHERE report_id = ?
                ORDER BY receipt_timestamp, receipt_id
                """,
                (report_id,),
            ).fetchall()

            return [RecipientReceipt.model_validate(dict(row)) for row in rows]
        finally:
            connection.close()

    def get_destination_config(
        self, destination_id: str
    ) -> DestinationConfig | None:
        connection = self.database.get_connection()

        try:
            row = connection.execute(
                """
                SELECT destination_id, endpoint_url, enabled
                FROM destination_configs
                WHERE destination_id = ?
                """,
                (destination_id,),
            ).fetchone()

            if row is None:
                return None

            return DestinationConfig.model_validate(dict(row))
        finally:
            connection.close()
