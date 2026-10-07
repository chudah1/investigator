import argparse
from pathlib import Path
from typing import Any, Sequence

from langchain.messages import HumanMessage
from langchain_core.language_models.chat_models import BaseChatModel

from baseline import DEFAULT_MODEL, create_openai_client, investigate_with_openai
from database import Database
from evidence import collect_job_evidence
from investigator_graph import MAX_TOOL_CALLS, build_investigation_graph
from models import InvestigationResult
from repository import Repository


DEFAULT_DB_PATH = Path(__file__).with_name("investigator.db")


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Investigate a report-delivery job using collected evidence."
    )
    parser.add_argument(
        "job_id",
        nargs="?",
        default="job-001",
        help="Job to investigate (default: job-001).",
    )
    parser.add_argument(
        "--db",
        type=Path,
        default=DEFAULT_DB_PATH,
        help=f"SQLite database path (default: {DEFAULT_DB_PATH}).",
    )
    parser.add_argument(
        "--mode",
        choices=("baseline", "agent"),
        default="baseline",
        help="Investigation mode (default: baseline).",
    )
    parser.add_argument(
        "--model",
        default=DEFAULT_MODEL,
        help=f"OpenAI model name (default: {DEFAULT_MODEL}).",
    )
    return parser.parse_args(argv)


def create_agent_model(model_name: str) -> BaseChatModel:
    try:
        from langchain_openai import ChatOpenAI
    except ImportError as error:
        raise RuntimeError(
            "The LangChain OpenAI integration is not installed. "
            "Run: pip install -r requirements.txt"
        ) from error

    return ChatOpenAI(model=model_name, temperature=0)


def investigate_with_agent(
    repository: Repository,
    job_id: str,
    model_name: str,
) -> InvestigationResult:
    state = invoke_agent_graph(repository, job_id, model_name)

    result = state.get("result")
    if not isinstance(result, InvestigationResult):
        raise RuntimeError(
            "The investigation graph did not return an InvestigationResult."
        )
    return result


def invoke_agent_graph(
    repository: Repository,
    job_id: str,
    model_name: str,
) -> dict[str, Any]:
    model = create_agent_model(model_name)
    graph = build_investigation_graph(model, repository)
    state = graph.invoke(
        {
            "job_id": job_id,
            "messages": [
                HumanMessage(
                    content=f"Investigate report delivery job {job_id}."
                )
            ],
        },
        config={"recursion_limit": MAX_TOOL_CALLS * 2 + 5},
    )
    return dict(state)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)

    database = Database(str(args.db))
    database.initialize()
    repository = Repository(database)

    if repository.get_job(args.job_id) is None:
        print(f"Job not found: {args.job_id}")
        return 1

    if args.mode == "agent":
        result = investigate_with_agent(
            repository,
            args.job_id,
            args.model,
        )
    else:
        evidence = collect_job_evidence(repository, args.job_id)
        if evidence is None:
            print(f"Job not found: {args.job_id}")
            return 1

        client = create_openai_client()
        result = investigate_with_openai(
            client,
            evidence,
            model=args.model,
        )

    print(result.model_dump_json(indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
