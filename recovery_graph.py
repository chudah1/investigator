from typing import Any, Callable, Literal, NotRequired, TypedDict

from langgraph.graph import END, START, StateGraph
from langgraph.types import interrupt

from models import ActionType
from repository import Repository
from sender import Sender


RecoveryStatus = Literal[
    "approved",
    "rejected",
    "already_delivered",
    "ready_to_execute",
    "executed",
]
ApprovalRoute = Literal["recheck", "end"]
ExecutionRoute = Literal["execute", "end"]


class RecoveryState(TypedDict):
    report_id: str
    action_type: ActionType
    approved: NotRequired[bool]
    status: NotRequired[RecoveryStatus]
    receipt_id: NotRequired[str]
    attempt_id: NotRequired[str]
    attempt_outcome: NotRequired[str]


def request_recovery_approval(state: RecoveryState) -> dict[str, Any]:
    report_id = state["report_id"]
    action_type = ActionType(state["action_type"])
    decision = interrupt(
        {
            "kind": "recovery_approval",
            "report_id": report_id,
            "action_type": action_type.value,
            "message": f"Approve recovery action for {report_id}?",
        }
    )
    approved = (
        isinstance(decision, dict) and decision.get("approved") is True
    )
    return {
        "approved": approved,
        "status": "approved" if approved else "rejected",
    }


def route_after_approval(state: RecoveryState) -> ApprovalRoute:
    return "recheck" if state.get("approved") is True else "end"


def build_recheck_delivery_node(
    repository: Repository,
) -> Callable[[RecoveryState], dict[str, Any]]:
    def recheck_delivery(state: RecoveryState) -> dict[str, Any]:
        receipts = repository.get_recipient_receipts(state["report_id"])
        if receipts:
            return {
                "status": "already_delivered",
                "receipt_id": receipts[-1].receipt_id,
            }
        return {"status": "ready_to_execute"}

    return recheck_delivery


def route_after_recheck(state: RecoveryState) -> ExecutionRoute:
    return "execute" if state.get("status") == "ready_to_execute" else "end"


def build_execute_recovery_node(
    repository: Repository,
    sender: Sender,
) -> Callable[[RecoveryState], dict[str, Any]]:
    def execute_recovery(state: RecoveryState) -> dict[str, Any]:
        action_type = ActionType(state["action_type"])
        if action_type is not ActionType.RETRY_DELIVERY:
            raise ValueError(
                f"Recovery action {action_type.value!r} is not executable."
            )

        report = repository.get_report(state["report_id"])
        if report is None:
            raise ValueError(f"Report {state['report_id']!r} was not found.")

        attempt = sender.deliver(report)
        return {
            "status": "executed",
            "attempt_id": attempt.attempt_id,
            "attempt_outcome": attempt.outcome,
        }

    return execute_recovery


def build_recovery_graph(
    repository: Repository,
    sender: Sender,
    *,
    checkpointer: Any,
):
    builder = StateGraph(RecoveryState)
    builder.add_node("request_approval", request_recovery_approval)
    builder.add_node(
        "recheck_delivery",
        build_recheck_delivery_node(repository),
    )
    builder.add_node(
        "execute_recovery",
        build_execute_recovery_node(repository, sender),
    )
    builder.add_edge(START, "request_approval")
    builder.add_conditional_edges(
        "request_approval",
        route_after_approval,
        {
            "recheck": "recheck_delivery",
            "end": END,
        },
    )
    builder.add_conditional_edges(
        "recheck_delivery",
        route_after_recheck,
        {
            "execute": "execute_recovery",
            "end": END,
        },
    )
    builder.add_edge("execute_recovery", END)
    return builder.compile(checkpointer=checkpointer)
