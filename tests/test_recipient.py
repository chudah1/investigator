from concurrent.futures import ThreadPoolExecutor
from threading import Event

from fastapi.testclient import TestClient

from database import Database
from recipient import create_recipient_app
from repository import Repository
from seed import seed_database


class BlockingAcknowledgement:
    def __init__(self) -> None:
        self.started = Event()
        self.release = Event()

    def wait(self) -> None:
        self.started.set()
        self.release.wait()


def test_accepting_delivery_stores_receipt_before_responding(
    tmp_path,
) -> None:
    db_path = tmp_path / "investigator.db"
    seed_database(db_path)
    repository = Repository(Database(str(db_path)))
    client = TestClient(create_recipient_app(repository))

    response = client.post(
        "/deliveries",
        json={
            "report_id": "report-D",
            "delivery_key": "delivery-test-report-D",
        },
    )

    assert response.status_code == 202

    receipts = repository.get_recipient_receipts("report-D")
    assert len(receipts) == 1
    assert receipts[0].delivery_key == "delivery-test-report-D"
    assert response.json() == {
        "status": "accepted",
        "receipt_id": receipts[0].receipt_id,
    }


def test_delayed_acknowledgement_happens_after_receipt_is_stored(
    tmp_path,
) -> None:
    db_path = tmp_path / "investigator.db"
    seed_database(db_path)
    repository = Repository(Database(str(db_path)))
    acknowledgement = BlockingAcknowledgement()
    client = TestClient(
        create_recipient_app(
            repository,
            acknowledgement=acknowledgement,
        )
    )

    with ThreadPoolExecutor(max_workers=1) as executor:
        response_future = executor.submit(
            client.post,
            "/deliveries",
            json={
                "report_id": "report-D",
                "delivery_key": "delivery-delayed-report-D",
            },
        )
        try:
            assert acknowledgement.started.wait(timeout=1)
            assert not response_future.done()

            receipts = repository.get_recipient_receipts("report-D")
            assert len(receipts) == 1
            assert (
                receipts[0].delivery_key == "delivery-delayed-report-D"
            )
        finally:
            acknowledgement.release.set()

        assert response_future.result(timeout=1).status_code == 202


def test_replaying_delivery_key_returns_original_receipt(tmp_path) -> None:
    db_path = tmp_path / "investigator.db"
    seed_database(db_path)
    repository = Repository(Database(str(db_path)))
    client = TestClient(create_recipient_app(repository))
    delivery = {
        "report_id": "report-D",
        "delivery_key": "delivery-job-002-report-D",
    }

    first_response = client.post("/deliveries", json=delivery)
    replay_response = client.post("/deliveries", json=delivery)

    assert first_response.status_code == 202
    assert replay_response.status_code == 202
    assert replay_response.json() == first_response.json()

    receipts = repository.get_recipient_receipts("report-D")
    assert len(receipts) == 1
    assert receipts[0].receipt_id == first_response.json()["receipt_id"]
