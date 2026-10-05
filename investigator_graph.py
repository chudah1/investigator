from typing import Any, Callable, Literal, NotRequired

from langchain.messages import AIMessage, HumanMessage, SystemMessage
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.tools import BaseTool
from langgraph.graph import END, START, MessagesState, StateGraph
from langgraph.prebuilt import ToolNode
from langgraph.runtime import Runtime

from investigation_tools import build_tools
from models import InvestigationResult
from repository import Repository


StopReason = Literal["complete", "tool_limit", "time_limit"]
ToolRoute = Literal["tools", "finalize", "tool_limit"]
MAX_TOOL_CALLS = 12


class InvestigationState(MessagesState):
    job_id: str
    llm_calls: NotRequired[int]
    tool_calls_used: NotRequired[int]
    result: NotRequired[InvestigationResult]
    stop_reason: NotRequired[StopReason]


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

FINALIZER_PROMPT = """
Produce the final investigation result using only evidence returned by tools.

Return exactly one finding for every expected report.
Distinguish sender status from confirmed recipient delivery.
A recipient receipt proves that the report was accepted.
Do not cite evidence IDs that do not appear in tool results.
Do not recommend retrying a report when a receipt proves delivery.
Explicitly identify uncertainty when evidence is missing or incomplete.
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

        return {
            "result": result,
            "stop_reason": stop_reason,
            "llm_calls": state.get("llm_calls", 0) + 1,
        }

    return finalize


def mark_tool_limit(
    _state: InvestigationState,
) -> dict[str, Any]:
    return {"stop_reason": "tool_limit"}


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
