import sqlite3


class Database:
    def __init__(self, db_path: str) -> None:
        self.db_path = db_path

    def get_connection(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.db_path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        return connection

    def initialize(self) -> None:
        connection = self.get_connection()
        try:
            self._create_schema(connection)
        finally:
            connection.close()

    def _create_schema(self, connection: sqlite3.Connection) -> None:
        connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS jobs (
                job_id TEXT PRIMARY KEY
            );

            CREATE TABLE IF NOT EXISTS expected_reports (
                job_id TEXT NOT NULL,
                report_id TEXT NOT NULL,
                PRIMARY KEY (job_id, report_id),
                FOREIGN KEY (job_id) REFERENCES jobs(job_id)
            );

            CREATE TABLE IF NOT EXISTS reports (
                report_id TEXT PRIMARY KEY,
                job_id TEXT NOT NULL,
                destination_id TEXT NOT NULL,
                delivery_status TEXT NOT NULL,
                FOREIGN KEY (job_id) REFERENCES jobs(job_id)
            );

            CREATE TABLE IF NOT EXISTS delivery_attempts (
                attempt_id TEXT PRIMARY KEY,
                report_id TEXT NOT NULL,
                timestamp TEXT NOT NULL,
                outcome TEXT NOT NULL,
                error TEXT,
                FOREIGN KEY (report_id) REFERENCES reports(report_id)
            );

            CREATE TABLE IF NOT EXISTS recipient_receipts (
                receipt_id TEXT PRIMARY KEY,
                report_id TEXT NOT NULL,
                delivery_key TEXT NOT NULL UNIQUE,
                receipt_timestamp TEXT NOT NULL,
                FOREIGN KEY (report_id) REFERENCES reports(report_id)
            );

            CREATE TABLE IF NOT EXISTS destination_configs (
                destination_id TEXT PRIMARY KEY,
                endpoint_url TEXT NOT NULL,
                enabled INTEGER NOT NULL DEFAULT 1
                    CHECK (enabled IN (0, 1))
            );

            CREATE INDEX IF NOT EXISTS idx_reports_job_id
                ON reports(job_id);

            CREATE INDEX IF NOT EXISTS idx_delivery_attempts_report_id
                ON delivery_attempts(report_id);

            CREATE INDEX IF NOT EXISTS idx_recipient_receipts_report_id
                ON recipient_receipts(report_id);
            """
        )
        connection.commit()
