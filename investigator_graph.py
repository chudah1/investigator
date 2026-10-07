import json
from dataclasses import dataclass
from typing import Any, Callable, Literal, NotRequired

from langchain.messages import (
    AIMessage,
    AnyMessage,
    HumanMessage,
    SystemMessage,
    ToolMessage,
)
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.tools import BaseTool
from langgraph.graph import END, START, MessagesState, StateGraph
from langgraph.prebuilt import ToolNode
from langgraph.runtime import Runtime

from investigation_policy import DECISION_POLICY
from investigation_tools import build_tools
from models import InvestigationResult
from repository import Repository
from validation import InvestigationValidationError, validate_result


StopReason = Literal["complete", "tool_limit", "time_limit"]
ToolRoute = Literal["tools", "finalize", "tool_limit"]
MAX_TOOL_CALLS = 12


class InvestigationState(MessagesState):
    job_id: str
    llm_calls: NotRequired[int]
    tool_calls_used: NotRequired[int]
    result: NotRequired[InvestigationResult]
    stop_reason: NotRequired[StopReason]


@dataclass(frozen=True)
class ObservedEvidence:
    job_observed: bool
    expected_report_ids: frozenset[str]
    valid_evidence_ids: frozenset[str]


INVESTIGATOR_PROMPT = """
You investigate report delivery jobs by gathering evidence through tools.

Begin by retrieving the job and its expected reports.
Inspect every expected report. For each report, compare the sender's status,
delivery attempts, recipient receipts, and destination configuration.

A sender timeout does not prove delivery failure.
A recipient receipt proves that the recipient accepted the report.
Use only evidence returned by tools and do not invent facts.

When you have enough evidence to diagnose every expected report, stop calling
tools and briefly state that the investigation is ready to be finalized.
""".strip()

FINALIZER_PROMPT = f"""
Produce the final investigation result using only evidence returned by tools.

Return exactly one finding for every expected report.
Distinguish sender status from confirmed recipient delivery.
A recipient receipt proves that the report was accepted.
Do not cite evidence IDs that do not appear in tool results.
Do not recommend retrying a report when a receipt proves delivery.
Explicitly identify uncertainty when evidence is missing or incomplete.
Use the most specific diagnosis_code and action_type allowed by the schema.

{DECISION_POLICY}
""".strip()


def build_model_node(
    model: BaseChatModel,
    tools: list[BaseTool],
) -> Callable[[InvestigationState], dict[str, Any]]:
    model_with_tools = model.bind_tools(tools)

    def call_model(state: InvestigationState) -> dict[str, Any]:
        response = model_with_tools.invoke(
            [
                SystemMessage(content=INVESTIGATOR_PROMPT),
                *state["messages"],
            ]
        )

        return {
            "messages": [response],
            "llm_calls": state.get("llm_calls", 0) + 1,
        }

    return call_model


def build_tool_node(
    tools: list[BaseTool],
) -> Callable[[InvestigationState, Runtime], dict[str, Any]]:
    tool_node = ToolNode(tools)

    def call_tools(
        state: InvestigationState,
        runtime: Runtime,
    ) -> dict[str, Any]:
        last_message = state["messages"][-1]

        if not isinstance(last_message, AIMessage):
            raise TypeError("Tool execution requires an AIMessage.")

        tool_call_count = len(last_message.tool_calls)
        update = tool_node.invoke(state, runtime=runtime)

        return {
            "messages": update["messages"],
            "tool_calls_used": (
                state.get("tool_calls_used", 0) + tool_call_count
            ),
        }

    return call_tools


def route_after_model(state: InvestigationState) -> ToolRoute:
    last_message = state["messages"][-1]

    if not isinstance(last_message, AIMessage):
        raise TypeError("Model node must produce an AIMessage.")

    if not last_message.tool_calls:
        return "finalize"

    requested_calls = len(last_message.tool_calls)
    calls_after_execution = (
        state.get("tool_calls_used", 0) + requested_calls
    )

    if calls_after_execution > MAX_TOOL_CALLS:
        return "tool_limit"

    return "tools"


def build_finalizer_node(
    model: BaseChatModel,
) -> Callable[[InvestigationState], dict[str, Any]]:
    structured_model = model.with_structured_output(
        InvestigationResult,
        method="json_schema",
    )

    def finalize(state: InvestigationState) -> dict[str, Any]:
        stop_reason = state.get("stop_reason", "complete")
        result = structured_model.invoke(
            [
                SystemMessage(content=FINALIZER_PROMPT),
                *state["messages"],
                HumanMessage(
                    content=(
                        f"Produce the final result for {state['job_id']}. "
                        "The investigation stopped because: "
                        f"{stop_reason}."
                    )
                ),
            ]
        )

        if not isinstance(result, InvestigationResult):
            raise RuntimeError(
                "The finalizer did not return an InvestigationResult."
            )

        observed = extract_observed_evidence(state["messages"])
        if stop_reason == "complete" and not observed.job_observed:
            raise InvestigationValidationError(
                ["job evidence was not retrieved"]
            )

        validate_result(
            result=result,
            job_id=state["job_id"],
            expected_report_ids=set(observed.expected_report_ids),
            valid_evidence_ids=set(observed.valid_evidence_ids),
            require_all_findings=stop_reason == "complete",
        )

        if stop_reason != "complete" and not result.unresolved_questions:
            raise InvestigationValidationError(
                [
                    "an incomplete investigation must identify unresolved "
                    "questions"
                ]
            )

        return {
            "result": result,
            "stop_reason": stop_reason,
            "llm_calls": state.get("llm_calls", 0) + 1,
        }

    return finalize


def extract_observed_evidence(
    messages: list[AnyMessage],
) -> ObservedEvidence:
    job_observed = False
    expected_report_ids: set[str] = set()
    valid_evidence_ids: set[str] = set()

    for message in messages:
        if not isinstance(message, ToolMessage):
            continue
        if message.status == "error":
            continue

        payload = _parse_tool_message(message)

        if message.name == "get_job":
            if payload is None:
                continue
            job = _require_mapping(payload, message.name)
            job_observed = True
            expected_report_ids.update(
                value
                for value in job.get("expected_reports", [])
                if isinstance(value, str)
            )
        elif message.name == "list_reports":
            valid_evidence_ids.update(
                _ids_from_records(payload, "report_id", message.name)
            )
        elif message.name == "get_delivery_attempts":
            valid_evidence_ids.update(
                _ids_from_records(payload, "attempt_id", message.name)
            )
        elif message.name == "get_recipient_receipts":
            valid_evidence_ids.update(
                _ids_from_records(payload, "receipt_id", message.name)
            )
        elif message.name == "get_destination_config":
            if payload is None:
                continue
            config = _require_mapping(payload, message.name)
            destination_id = config.get("destination_id")
            if isinstance(destination_id, str):
                valid_evidence_ids.add(destination_id)

    return ObservedEvidence(
        job_observed=job_observed,
        expected_report_ids=frozenset(expected_report_ids),
        valid_evidence_ids=frozenset(valid_evidence_ids),
    )


def _parse_tool_message(message: ToolMessage) -> Any:
    content = message.text
    if content:
        try:
            return json.loads(content)
        except json.JSONDecodeError as error:
            raise RuntimeError(
                f"Tool {message.name!r} returned invalid JSON."
            ) from error

    raw_content = message.content
    if isinstance(raw_content, list):
        if all(
            isinstance(item, dict) and "type" not in item
            for item in raw_content
        ):
            values = raw_content
        elif all(
            isinstance(item, dict)
            and item.get("type") == "non_standard"
            and "value" in item
            for item in raw_content
        ):
            values = [item["value"] for item in raw_content]
            if len(values) == 1 and isinstance(values[0], list):
                return values[0]
        else:
            values = None

        if values is not None:
            if message.name in {"get_job", "get_destination_config"}:
                if len(values) == 1:
                    return values[0]
            return values

    raise RuntimeError(
        f"Tool {message.name!r} returned unsupported content."
    )


def _require_mapping(
    payload: Any,
    tool_name: str | None,
) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise RuntimeError(
            f"Tool {tool_name!r} returned an unexpected result shape."
        )
    return payload


def _ids_from_records(
    payload: Any,
    id_field: str,
    tool_name: str | None,
) -> set[str]:
    if not isinstance(payload, list):
        raise RuntimeError(
            f"Tool {tool_name!r} returned an unexpected result shape."
        )

    return {
        record[id_field]
        for record in payload
        if isinstance(record, dict)
        and isinstance(record.get(id_field), str)
    }


def mark_tool_limit(
    state: InvestigationState,
) -> dict[str, Any]:
    last_message = state["messages"][-1] if state["messages"] else None
    if not isinstance(last_message, AIMessage):
        return {"stop_reason": "tool_limit"}

    skipped_calls = [
        ToolMessage(
            content=json.dumps(
                {
                    "error": (
                        "Tool call was not executed because the investigation "
                        "tool-call limit was reached."
                    )
                }
            ),
            tool_call_id=tool_call["id"],
            name=tool_call["name"],
            status="error",
        )
        for tool_call in last_message.tool_calls
    ]
    return {
        "messages": skipped_calls,
        "stop_reason": "tool_limit",
    }


def build_investigation_graph(
    model: BaseChatModel,
    repository: Repository,
):
    tools = build_tools(repository)
    builder = StateGraph(InvestigationState)

    builder.add_node("model", build_model_node(model, tools))
    builder.add_node("tools", build_tool_node(tools))
    builder.add_node("tool_limit", mark_tool_limit)
    builder.add_node("finalize", build_finalizer_node(model))

    builder.add_edge(START, "model")
    builder.add_conditional_edges(
        "model",
        route_after_model,
        {
            "tools": "tools",
            "finalize": "finalize",
            "tool_limit": "tool_limit",
        },
    )
    builder.add_edge("tools", "model")
    builder.add_edge("tool_limit", "finalize")
    builder.add_edge("finalize", END)

    return builder.compile()
