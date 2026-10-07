import argparse
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from langchain_core.callbacks import get_usage_metadata_callback

from baseline import DEFAULT_MODEL, create_openai_client, investigate_with_openai
from cli import DEFAULT_DB_PATH, invoke_agent_graph
from database import Database
from environment import load_environment
from eval_cases import CASES_BY_JOB_ID
from evidence import collect_job_evidence
from experiment import (
    ExecutionResult,
    ExperimentMode,
    run_experiment,
)
from models import InvestigationResult
from repository import Repository


class TrackedResponses:
    def __init__(self, responses: Any) -> None:
        self.responses = responses
        self.last_response: Any = None

    def parse(self, **kwargs: Any) -> Any:
        self.last_response = self.responses.parse(**kwargs)
        return self.last_response


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Compare baseline and agent investigation quality and cost."
    )
    parser.add_argument(
        "job_id",
        nargs="?",
        default="job-001",
        help="Evaluation job (default: job-001).",
    )
    parser.add_argument(
        "--db",
        type=Path,
        default=DEFAULT_DB_PATH,
        help=f"SQLite database path (default: {DEFAULT_DB_PATH}).",
    )
    parser.add_argument(
        "--model",
        default=DEFAULT_MODEL,
        help=f"OpenAI model name (default: {DEFAULT_MODEL}).",
    )
    parser.add_argument(
        "--runs",
        type=_positive_integer,
        default=1,
        help=(
            "Repetitions per mode (default: 1). Each repetition makes paid "
            "model calls."
        ),
    )
    parser.add_argument(
        "--modes",
        nargs="+",
        choices=("baseline", "agent"),
        default=("baseline", "agent"),
        help="Modes to compare (default: baseline agent).",
    )
    parser.add_argument(
        "--output",
        type=Path,
        help="Optional path for the JSON experiment report.",
    )
    return parser.parse_args(argv)


def build_runners(
    repository: Repository,
    job_id: str,
    model: str,
    modes: Sequence[ExperimentMode],
) -> dict[ExperimentMode, Callable[[], ExecutionResult]]:
    runners: dict[ExperimentMode, Callable[[], ExecutionResult]] = {}
    if "baseline" in modes:
        runners["baseline"] = _baseline_runner(
            repository,
            job_id,
            model,
        )
    if "agent" in modes:
        runners["agent"] = _agent_runner(
            repository,
            job_id,
            model,
        )
    return runners


def _baseline_runner(
    repository: Repository,
    job_id: str,
    model: str,
) -> Callable[[], ExecutionResult]:
    def run() -> ExecutionResult:
        evidence = collect_job_evidence(repository, job_id)
        if evidence is None:
            raise RuntimeError(f"Job not found: {job_id}")

        client = create_openai_client()
        tracked_responses = TrackedResponses(client.responses)
        tracked_client = SimpleNamespace(responses=tracked_responses)
        result = investigate_with_openai(
            tracked_client,
            evidence,
            model=model,
        )
        input_tokens, output_tokens, total_tokens = _openai_usage(
            tracked_responses.last_response
        )
        return ExecutionResult(
            result=result,
            llm_calls=1,
            tool_calls=0,
            stop_reason="complete",
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            total_tokens=total_tokens,
        )

    return run


def _agent_runner(
    repository: Repository,
    job_id: str,
    model: str,
) -> Callable[[], ExecutionResult]:
    def run() -> ExecutionResult:
        with get_usage_metadata_callback() as usage_callback:
            state = invoke_agent_graph(repository, job_id, model)

        result = state.get("result")
        if not isinstance(result, InvestigationResult):
            raise RuntimeError(
                "The investigation graph did not return an "
                "InvestigationResult."
            )

        input_tokens, output_tokens, total_tokens = _langchain_usage(
            usage_callback.usage_metadata
        )
        return ExecutionResult(
            result=result,
            llm_calls=int(state.get("llm_calls", 0)),
            tool_calls=int(state.get("tool_calls_used", 0)),
            stop_reason=str(state.get("stop_reason", "complete")),
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            total_tokens=total_tokens,
        )

    return run


def _openai_usage(response: Any) -> tuple[int | None, int | None, int | None]:
    usage = getattr(response, "usage", None)
    if usage is None:
        return None, None, None
    return (
        _usage_value(usage, "input_tokens"),
        _usage_value(usage, "output_tokens"),
        _usage_value(usage, "total_tokens"),
    )


def _langchain_usage(
    usage_by_model: Mapping[str, Mapping[str, Any]],
) -> tuple[int | None, int | None, int | None]:
    if not usage_by_model:
        return None, None, None
    return (
        sum(int(usage.get("input_tokens", 0)) for usage in usage_by_model.values()),
        sum(int(usage.get("output_tokens", 0)) for usage in usage_by_model.values()),
        sum(int(usage.get("total_tokens", 0)) for usage in usage_by_model.values()),
    )


def _usage_value(usage: Any, name: str) -> int | None:
    if isinstance(usage, Mapping):
        value = usage.get(name)
    else:
        value = getattr(usage, name, None)
    return int(value) if value is not None else None


def _positive_integer(value: str) -> int:
    parsed = int(value)
    if parsed < 1:
        raise argparse.ArgumentTypeError("must be at least 1")
    return parsed


def main(argv: Sequence[str] | None = None) -> int:
    load_environment()
    args = parse_args(argv)
    case = CASES_BY_JOB_ID.get(args.job_id)
    if case is None:
        print(f"No evaluation case for job: {args.job_id}")
        return 2

    database = Database(str(args.db))
    database.initialize()
    repository = Repository(database)
    if repository.get_job(args.job_id) is None:
        print(f"Job not found: {args.job_id}")
        return 2

    modes = tuple(dict.fromkeys(args.modes))
    runners = build_runners(
        repository,
        args.job_id,
        args.model,
        modes,
    )
    report = run_experiment(
        case=case,
        model=args.model,
        repetitions=args.runs,
        runners=runners,
        modes=modes,
    )
    output = report.model_dump_json(indent=2)
    if args.output is None:
        print(output)
    else:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(f"{output}\n", encoding="utf-8")
        print(f"Experiment report written to {args.output}")

    return 0 if all(trial.passed for trial in report.trials) else 1


if __name__ == "__main__":
    raise SystemExit(main())
