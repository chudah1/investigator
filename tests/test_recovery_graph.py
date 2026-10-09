import pytest
from fastapi.testclient import TestClient
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.types import Command

from database import Database
from models import ActionType
from recipient import create_recipient_app
from recovery_graph import build_recovery_graph
from repository import Repository
from seed import seed_database
from sender import Sender


@pytest.fixture
def repository(tmp_path) -> Repository:
    db_path = tmp_path / "investigator.db"
    seed_database(db_path)
    return Repository(Database(str(db_path)))


@pytest.fixture
def sender(repository: Repository) -> Sender:
    recipient = TestClient(create_recipient_app(repository))
    return Sender(repository, recipient)


def test_recovery_pauses_and_requests_approval_before_action(
    repository: Repository,
    sender: Sender,
) -> None:
    graph = build_recovery_graph(
        repository,
        sender,
        checkpointer=InMemorySaver(),
    )
    config = {"configurable": {"thread_id": "recovery-report-D"}}

    state = graph.invoke(
        {
            "report_id": "report-D",
            "action_type": ActionType.RETRY_DELIVERY,
        },
        config=config,
    )

    assert state["__interrupt__"][0].value == {
        "kind": "recovery_approval",
        "report_id": "report-D",
        "action_type": "retry_delivery",
        "message": "Approve recovery action for report-D?",
    }
    assert "approved" not in state
    assert "status" not in state


def test_approved_recovery_rechecks_and_stops_if_receipt_appeared(
    repository: Repository,
    sender: Sender,
) -> None:
    graph = build_recovery_graph(
        repository,
        sender,
        checkpointer=InMemorySaver(),
    )
    config = {"configurable": {"thread_id": "recovery-report-D"}}
    attempts_before = repository.get_delivery_attempts("report-D")

    graph.invoke(
        {
            "report_id": "report-D",
            "action_type": ActionType.RETRY_DELIVERY,
        },
        config=config,
    )
    receipt = repository.create_recipient_receipt(
        report_id="report-D",
        delivery_key="delivery-job-002-report-D",
    )

    state = graph.invoke(
        Command(resume={"approved": True}),
        config=config,
    )

    assert state["approved"] is True
    assert state["status"] == "already_delivered"
    assert state["receipt_id"] == receipt.receipt_id
    assert repository.get_delivery_attempts("report-D") == attempts_before


def test_approved_recovery_executes_retry_when_recheck_has_no_receipt(
    repository: Repository,
    sender: Sender,
) -> None:
    graph = build_recovery_graph(
        repository,
        sender,
        checkpointer=InMemorySaver(),
    )
    config = {"configurable": {"thread_id": "recovery-report-D"}}
    attempt_ids_before = {
        attempt.attempt_id
        for attempt in repository.get_delivery_attempts("report-D")
    }

    graph.invoke(
        {
            "report_id": "report-D",
            "action_type": ActionType.RETRY_DELIVERY,
        },
        config=config,
    )
    state = graph.invoke(
        Command(resume={"approved": True}),
        config=config,
    )

    assert state["status"] == "executed"
    assert state["attempt_outcome"] == "succeeded"

    receipts = repository.get_recipient_receipts("report-D")
    assert len(receipts) == 1
    assert receipts[0].delivery_key == "delivery-job-002-report-D"

    new_attempts = [
        attempt
        for attempt in repository.get_delivery_attempts("report-D")
        if attempt.attempt_id not in attempt_ids_before
    ]
    assert len(new_attempts) == 1
    assert new_attempts[0].attempt_id == state["attempt_id"]
