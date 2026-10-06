from typing import Any, cast

import pytest
from langchain.messages import (
    AIMessage,
    HumanMessage,
    SystemMessage,
    ToolMessage,
)
from langchain.tools import tool
from langchain_core.language_models.chat_models import BaseChatModel
from langgraph.runtime import Runtime

from database import Database
from investigator_graph import (
    FINALIZER_PROMPT,
    INVESTIGATOR_PROMPT,
    MAX_TOOL_CALLS,
    build_finalizer_node,
    build_investigation_graph,
    build_model_node,
    build_tool_node,
    extract_observed_evidence,
    mark_tool_limit,
    route_after_model,
)
from models import Finding, InvestigationResult, RecommendedAction
from repository import Repository
from seed import seed_database
from validation import InvestigationValidationError


@tool
def echo_tool(value: str) -> dict[str, str]:
    """Return a value so tool execution can be tested."""
    return {"value": value}


class FakeChatModel:
    def __init__(
        self,
        responses: list[AIMessage] | None = None,
        structured_result: InvestigationResult | None = None,
    ) -> None:
        self.bound_tools: list[Any] | None = None
        self.received_messages: list[Any] | None = None
        self.responses = list(responses or [])
        self.structured_result = structured_result
        self.structured_schema: Any = None
        self.structured_kwargs: dict[str, Any] = {}
        self.finalizer_messages: list[Any] | None = None

    def bind_tools(self, tools: list[Any]) -> "FakeChatModel":
        self.bound_tools = tools
        return self

    def invoke(self, messages: list[Any]) -> AIMessage:
        self.received_messages = messages
        if self.responses:
            return self.responses.pop(0)
        return AIMessage(content="The investigation is ready to be finalized.")

    def with_structured_output(
        self,
        schema: Any,
        **kwargs: Any,
    ) -> "FakeStructuredModel":
        self.structured_schema = schema
        self.structured_kwargs = kwargs
        return FakeStructuredModel(self)


class FakeStructuredModel:
    def __init__(self, model: FakeChatModel) -> None:
        self.model = model

    def invoke(self, messages: list[Any]) -> InvestigationResult | None:
        self.model.finalizer_messages = messages
        return self.model.structured_result


def investigation_result() -> InvestigationResult:
    return InvestigationResult(
        job_id="job-001",
        findings=[
            Finding(
                report_id=report_id,
                conclusion="Investigated",
                summary="Based on retrieved evidence.",
                evidence_ids=[report_id],
            )
            for report_id in ["report-A", "report-B", "report-C"]
        ],
        unresolved_questions=[],
        recommended_actions=[
            RecommendedAction(
                report_id="report-C",
                action="Repair destination configuration.",
                rationale="The destination configuration is missing.",
            )
        ],
    )


def observed_job_and_reports() -> list[ToolMessage]:
    return [
        ToolMessage(
            content=(
                '{"job_id":"job-001","expected_reports":'
                '["report-A","report-B","report-C"]}'
            ),
            tool_call_id="call-get-job",
            name="get_job",
        ),
        ToolMessage(
            content=(
                '[{"report_id":"report-A","destination_id":"destination-A"},'
                '{"report_id":"report-B","destination_id":"destination-B"},'
                '{"report_id":"report-C","destination_id":"destination-C"}]'
            ),
            tool_call_id="call-list-reports",
            name="list_reports",
        ),
    ]


def test_build_model_node_binds_tools_and_calls_model_with_history() -> None:
    model = FakeChatModel()
    tools: list[Any] = [object()]
    call_model = build_model_node(
        cast(BaseChatModel, model),
        tools,
    )
    human_message = HumanMessage(content="Investigate job-001")

    update = call_model(
        {
            "job_id": "job-001",
            "messages": [human_message],
            "llm_calls": 2,
        }
    )

    assert model.bound_tools is tools
    assert model.received_messages is not None
    assert model.received_messages[0] == SystemMessage(
        content=INVESTIGATOR_PROMPT
    )
    assert model.received_messages[1] is human_message
    assert update["llm_calls"] == 3
    assert update["messages"] == [
        AIMessage(content="The investigation is ready to be finalized.")
    ]


def test_model_node_starts_llm_counter_at_one() -> None:
    model = FakeChatModel()
    call_model = build_model_node(cast(BaseChatModel, model), [])

    update = call_model(
        {
            "job_id": "job-001",
            "messages": [HumanMessage(content="Investigate job-001")],
        }
    )

    assert update["llm_calls"] == 1


def test_tool_node_executes_calls_and_increments_counter() -> None:
    call_tools = build_tool_node([echo_tool])
    request = AIMessage(
        content="",
        tool_calls=[
            {
                "name": "echo_tool",
                "args": {"value": "report-B"},
                "id": "call-1",
                "type": "tool_call",
            }
        ],
    )

    update = call_tools(
        {
            "job_id": "job-001",
            "messages": [request],
            "tool_calls_used": 2,
        },
        Runtime(),
    )

    assert update["tool_calls_used"] == 3
    assert len(update["messages"]) == 1
    assert isinstance(update["messages"][0], ToolMessage)
    assert update["messages"][0].tool_call_id == "call-1"
    assert update["messages"][0].name == "echo_tool"


def _model_response_with_tool_calls(count: int) -> AIMessage:
    return AIMessage(
        content="",
        tool_calls=[
            {
                "name": "echo_tool",
                "args": {"value": str(index)},
                "id": f"call-{index}",
                "type": "tool_call",
            }
            for index in range(count)
        ],
    )


@pytest.mark.parametrize(
    ("tool_call_count", "calls_used", "expected_route"),
    [
        (0, 0, "finalize"),
        (1, 0, "tools"),
        (1, MAX_TOOL_CALLS - 1, "tools"),
        (1, MAX_TOOL_CALLS, "tool_limit"),
        (2, MAX_TOOL_CALLS - 1, "tool_limit"),
    ],
)
def test_route_after_model_respects_tool_budget(
    tool_call_count: int,
    calls_used: int,
    expected_route: str,
) -> None:
    state = {
        "job_id": "job-001",
        "messages": [_model_response_with_tool_calls(tool_call_count)],
        "tool_calls_used": calls_used,
    }

    assert route_after_model(state) == expected_route


def test_finalizer_returns_structured_result() -> None:
    expected = investigation_result()
    model = FakeChatModel(structured_result=expected)
    finalize = build_finalizer_node(cast(BaseChatModel, model))

    update = finalize(
        {
            "job_id": "job-001",
            "messages": [
                *observed_job_and_reports(),
                AIMessage(content="Ready to finalize"),
            ],
            "llm_calls": 2,
        }
    )

    assert model.structured_schema is InvestigationResult
    assert model.structured_kwargs == {"method": "json_schema"}
    assert model.finalizer_messages is not None
    assert model.finalizer_messages[0] == SystemMessage(
        content=FINALIZER_PROMPT
    )
    assert update == {
        "result": expected,
        "stop_reason": "complete",
        "llm_calls": 3,
    }


def test_mark_tool_limit_records_stop_reason() -> None:
    update = mark_tool_limit(
        {
            "job_id": "job-001",
            "messages": [],
        }
    )

    assert update == {"stop_reason": "tool_limit"}


def test_extract_observed_evidence_uses_tool_specific_ids() -> None:
    messages = [
        *observed_job_and_reports(),
        ToolMessage(
            content='[{"attempt_id":"attempt-C-1"}]',
            tool_call_id="call-attempts",
            name="get_delivery_attempts",
        ),
        ToolMessage(
            content='[{"receipt_id":"receipt-B-1"}]',
            tool_call_id="call-receipts",
            name="get_recipient_receipts",
        ),
        ToolMessage(
            content=(
                '{"destination_id":"destination-A",'
                '"endpoint_url":"https://example.test","enabled":true}'
            ),
            tool_call_id="call-config-a",
            name="get_destination_config",
        ),
        ToolMessage(
            content="null",
            tool_call_id="call-config-c",
            name="get_destination_config",
        ),
    ]

    observed = extract_observed_evidence(messages)

    assert observed.job_observed is True
    assert observed.expected_report_ids == frozenset(
        {"report-A", "report-B", "report-C"}
    )
    assert observed.valid_evidence_ids == frozenset(
        {
            "report-A",
            "report-B",
            "report-C",
            "attempt-C-1",
            "receipt-B-1",
            "destination-A",
        }
    )
    assert "destination-C" not in observed.valid_evidence_ids


def test_finalizer_rejects_evidence_not_observed_in_tool_results() -> None:
    invalid = investigation_result()
    invalid.findings[0].evidence_ids.append("invented-evidence")
    model = FakeChatModel(structured_result=invalid)
    finalize = build_finalizer_node(cast(BaseChatModel, model))

    with pytest.raises(
        InvestigationValidationError,
        match="unknown evidence IDs cited",
    ):
        finalize(
            {
                "job_id": "job-001",
                "messages": observed_job_and_reports(),
            }
        )


def test_tool_limit_allows_partial_findings_with_unresolved_questions() -> None:
    partial = InvestigationResult(
        job_id="job-001",
        findings=[
            Finding(
                report_id="report-A",
                conclusion="Investigated",
                summary="Based on retrieved evidence.",
                evidence_ids=["report-A"],
            )
        ],
        unresolved_questions=["Reports B and C were not fully inspected."],
        recommended_actions=[],
    )
    model = FakeChatModel(structured_result=partial)
    finalize = build_finalizer_node(cast(BaseChatModel, model))

    update = finalize(
        {
            "job_id": "job-001",
            "messages": observed_job_and_reports(),
            "stop_reason": "tool_limit",
        }
    )

    assert update["result"] == partial
    assert update["stop_reason"] == "tool_limit"


def test_complete_graph_runs_model_tool_loop_and_finalizer(
    tmp_path,
) -> None:
    db_path = tmp_path / "investigator.db"
    seed_database(db_path)
    repository = Repository(Database(str(db_path)))
    expected = investigation_result()
    model = FakeChatModel(
        responses=[
            AIMessage(
                content="",
                tool_calls=[
                    {
                        "name": "get_job",
                        "args": {"job_id": "job-001"},
                        "id": "call-get-job",
                        "type": "tool_call",
                    },
                    {
                        "name": "list_reports",
                        "args": {"job_id": "job-001"},
                        "id": "call-list-reports",
                        "type": "tool_call",
                    }
                ],
            ),
            AIMessage(content="Ready to finalize"),
        ],
        structured_result=expected,
    )
    graph = build_investigation_graph(
        cast(BaseChatModel, model),
        repository,
    )

    state = graph.invoke(
        {
            "job_id": "job-001",
            "messages": [HumanMessage(content="Investigate job-001")],
        }
    )

    assert state["result"] == expected
    assert state["stop_reason"] == "complete"
    assert state["llm_calls"] == 3
    assert state["tool_calls_used"] == 2
    assert any(
        isinstance(message, ToolMessage)
        and message.name == "get_job"
        for message in state["messages"]
    )
