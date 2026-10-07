from pathlib import Path

from database import Database


DEFAULT_DB_PATH = Path(__file__).with_name("investigator.db")
SCALE_REPORT_IDS = tuple(
    f"report-scale-{number:02d}" for number in range(1, 7)
)


def seed_database(db_path: str | Path = DEFAULT_DB_PATH) -> None:
    database = Database(str(db_path))
    database.initialize()
    connection = database.get_connection()

    try:
        with connection:
            connection.executemany(
                """
                INSERT INTO jobs (job_id)
                VALUES (?)
                ON CONFLICT (job_id) DO NOTHING
                """,
                [("job-001",), ("job-002",), ("job-003",)],
            )

            connection.executemany(
                """
                INSERT INTO expected_reports (job_id, report_id)
                VALUES (?, ?)
                ON CONFLICT (job_id, report_id) DO NOTHING
                """,
                [
                    ("job-001", "report-A"),
                    ("job-001", "report-B"),
                    ("job-001", "report-C"),
                    ("job-002", "report-D"),
                    ("job-002", "report-E"),
                    *[
                        ("job-003", report_id)
                        for report_id in SCALE_REPORT_IDS
                    ],
                ],
            )

            connection.executemany(
                """
                INSERT INTO reports (
                    report_id,
                    job_id,
                    destination_id,
                    delivery_status
                )
                VALUES (?, ?, ?, ?)
                ON CONFLICT (report_id) DO UPDATE SET
                    job_id = excluded.job_id,
                    destination_id = excluded.destination_id,
                    delivery_status = excluded.delivery_status
                """,
                [
                    ("report-A", "job-001", "destination-A", "succeeded"),
                    ("report-B", "job-001", "destination-B", "timed_out"),
                    ("report-C", "job-001", "destination-C", "failed"),
                    ("report-D", "job-002", "destination-D", "failed"),
                    ("report-E", "job-002", "destination-E", "queued"),
                    *[
                        (
                            report_id,
                            "job-003",
                            "destination-scale",
                            "succeeded",
                        )
                        for report_id in SCALE_REPORT_IDS
                    ],
                ],
            )

            connection.executemany(
                """
                INSERT INTO delivery_attempts (
                    attempt_id,
                    report_id,
                    timestamp,
                    outcome,
                    error
                )
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT (attempt_id) DO UPDATE SET
                    report_id = excluded.report_id,
                    timestamp = excluded.timestamp,
                    outcome = excluded.outcome,
                    error = excluded.error
                """,
                [
                    (
                        "attempt-A-1",
                        "report-A",
                        "2026-09-28T09:00:00+00:00",
                        "succeeded",
                        None,
                    ),
                    (
                        "attempt-B-1",
                        "report-B",
                        "2026-09-28T09:01:00+00:00",
                        "timed_out",
                        "Recipient acknowledgement timed out",
                    ),
                    (
                        "attempt-C-1",
                        "report-C",
                        "2026-09-28T09:02:00+00:00",
                        "failed",
                        "Destination configuration not found",
                    ),
                    (
                        "attempt-D-1",
                        "report-D",
                        "2026-09-28T10:00:00+00:00",
                        "failed",
                        "HTTP 503 Service Unavailable",
                    ),
                    *[
                        (
                            f"attempt-{report_id.removeprefix('report-')}",
                            report_id,
                            f"2026-09-28T11:{number:02d}:00+00:00",
                            "succeeded",
                            None,
                        )
                        for number, report_id in enumerate(
                            SCALE_REPORT_IDS,
                            start=1,
                        )
                    ],
                ],
            )

            connection.executemany(
                """
                INSERT INTO recipient_receipts (
                    receipt_id,
                    report_id,
                    delivery_key,
                    receipt_timestamp
                )
                VALUES (?, ?, ?, ?)
                ON CONFLICT (receipt_id) DO UPDATE SET
                    report_id = excluded.report_id,
                    delivery_key = excluded.delivery_key,
                    receipt_timestamp = excluded.receipt_timestamp
                """,
                [
                    (
                        "receipt-A-1",
                        "report-A",
                        "delivery-job-001-report-A",
                        "2026-09-28T09:00:01+00:00",
                    ),
                    (
                        "receipt-B-1",
                        "report-B",
                        "delivery-job-001-report-B",
                        "2026-09-28T09:01:01+00:00",
                    ),
                    *[
                        (
                            f"receipt-{report_id.removeprefix('report-')}",
                            report_id,
                            f"delivery-job-003-{report_id}",
                            f"2026-09-28T11:{number:02d}:01+00:00",
                        )
                        for number, report_id in enumerate(
                            SCALE_REPORT_IDS,
                            start=1,
                        )
                    ],
                ],
            )

            connection.executemany(
                """
                INSERT INTO destination_configs (
                    destination_id,
                    endpoint_url,
                    enabled
                )
                VALUES (?, ?, ?)
                ON CONFLICT (destination_id) DO UPDATE SET
                    endpoint_url = excluded.endpoint_url,
                    enabled = excluded.enabled
                """,
                [
                    ("destination-A", "https://recipient.example/reports", 1),
                    ("destination-B", "https://recipient.example/reports", 1),
                    ("destination-D", "https://recipient.example/reports", 1),
                    ("destination-E", "https://recipient.example/reports", 1),
                    (
                        "destination-scale",
                        "https://recipient.example/reports",
                        1,
                    ),
                ],
            )
    finally:
        connection.close()


if __name__ == "__main__":
    seed_database()
    print(f"Seeded investigation data in {DEFAULT_DB_PATH}")
