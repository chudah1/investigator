from collections.abc import Iterator
from contextlib import contextmanager
import socket
from threading import Event, Thread
from time import monotonic, sleep

from fastapi import FastAPI
from fastapi.testclient import TestClient
import httpx
import uvicorn

from database import Database
from evidence import collect_job_evidence
from recipient import create_recipient_app
from repository import Repository
from seed import seed_database
from sender import Sender


class BlockingAcknowledgement:
    def __init__(self) -> None:
        self.started = Event()
        self.release = Event()

    def wait(self) -> None:
        self.started.set()
        self.release.wait(timeout=2)


@contextmanager
def run_http_server(app: FastAPI) -> Iterator[str]:
    server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server_socket.bind(("127.0.0.1", 0))
    host, port = server_socket.getsockname()
    server = uvicorn.Server(
        uvicorn.Config(app, log_level="critical", lifespan="off")
    )
    thread = Thread(
        target=server.run,
        kwargs={"sockets": [server_socket]},
        daemon=True,
    )
    thread.start()

    deadline = monotonic() + 2
    while not server.started and monotonic() < deadline:
        sleep(0.01)
    if not server.started:
        server.should_exit = True
        thread.join(timeout=2)
        server_socket.close()
        raise RuntimeError("Recipient HTTP server did not start.")

    try:
        yield f"http://{host}:{port}"
    finally:
        server.should_exit = True
        thread.join(timeout=2)
        server_socket.close()

    if thread.is_alive():
        raise RuntimeError("Recipient HTTP server did not stop.")


def test_successful_delivery_uses_stable_key_and_records_attempt(
    tmp_path,
) -> None:
    db_path = tmp_path / "investigator.db"
    seed_database(db_path)
    repository = Repository(Database(str(db_path)))
    recipient = TestClient(create_recipient_app(repository))
    report = next(
        report
        for report in repository.list_reports("job-002")
        if report.report_id == "report-E"
    )
    sender = Sender(repository, recipient)

    attempt = sender.deliver(report)

    assert attempt.outcome == "succeeded"
    assert attempt.error is None

    receipts = repository.get_recipient_receipts("report-E")
    assert len(receipts) == 1
    assert receipts[0].delivery_key == "delivery-job-002-report-E"

    attempts = repository.get_delivery_attempts("report-E")
    assert [stored.model_dump() for stored in attempts] == [
        attempt.model_dump()
    ]


def test_sender_times_out_after_recipient_accepts_delivery(tmp_path) -> None:
    db_path = tmp_path / "investigator.db"
    seed_database(db_path)
    database = Database(str(db_path))
    repository = Repository(database)
    acknowledgement = BlockingAcknowledgement()
    app = create_recipient_app(
        repository,
        acknowledgement=acknowledgement,
    )
    report = next(
        report
        for report in repository.list_reports("job-002")
        if report.report_id == "report-E"
    )

    with run_http_server(app) as base_url:
        connection = database.get_connection()
        try:
            with connection:
                connection.execute(
                    """
                    UPDATE destination_configs
                    SET endpoint_url = ?
                    WHERE destination_id = ?
                    """,
                    (f"{base_url}/deliveries", report.destination_id),
                )
        finally:
            connection.close()

        with httpx.Client(timeout=0.2) as client:
            sender = Sender(repository, client)
            try:
                attempt = sender.deliver(report)
            finally:
                acknowledgement.release.set()

    assert acknowledgement.started.is_set()
    assert attempt.outcome == "timed_out"
    assert attempt.error == "Recipient acknowledgement timed out"

    receipts = repository.get_recipient_receipts("report-E")
    assert len(receipts) == 1
    assert receipts[0].delivery_key == "delivery-job-002-report-E"

    attempts = repository.get_delivery_attempts("report-E")
    assert [stored.model_dump() for stored in attempts] == [
        attempt.model_dump()
    ]

    evidence = collect_job_evidence(repository, "job-002")
    assert evidence is not None
    report_evidence = next(
        item
        for item in evidence.reports
        if item.report.report_id == "report-E"
    )
    assert [item.attempt_id for item in report_evidence.delivery_attempts] == [
        attempt.attempt_id
    ]
    assert [
        item.delivery_key for item in report_evidence.recipient_receipts
    ] == ["delivery-job-002-report-E"]
