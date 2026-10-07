from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from time import perf_counter
from typing import Literal

from pydantic import BaseModel

from evaluation import EvaluationCase, EvaluationReport, evaluate_result
from models import InvestigationResult


ExperimentMode = Literal["baseline", "agent"]


@dataclass(frozen=True)
class ExecutionResult:
    result: InvestigationResult
    llm_calls: int
    tool_calls: int
    stop_reason: str = "complete"
    input_tokens: int | None = None
    output_tokens: int | None = None
    total_tokens: int | None = None


class TrialResult(BaseModel):
    mode: ExperimentMode
    run_number: int
    passed: bool
    score: float
    latency_ms: float
    llm_calls: int | None = None
    tool_calls: int | None = None
    stop_reason: str | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None
    total_tokens: int | None = None
    result: InvestigationResult | None = None
    evaluation: EvaluationReport | None = None
    error: str | None = None


class ModeSummary(BaseModel):
    mode: ExperimentMode
    runs: int
    passed_runs: int
    pass_rate: float
    average_score: float
    average_latency_ms: float
    average_llm_calls: float | None
    average_tool_calls: float | None
    total_input_tokens: int | None
    total_output_tokens: int | None
    total_tokens: int | None


class ExperimentReport(BaseModel):
    job_id: str
    model: str
    repetitions: int
    trials: list[TrialResult]
    summaries: list[ModeSummary]


def run_experiment(
    case: EvaluationCase,
    model: str,
    repetitions: int,
    runners: Mapping[ExperimentMode, Callable[[], ExecutionResult]],
    modes: Sequence[ExperimentMode] = ("baseline", "agent"),
    clock: Callable[[], float] = perf_counter,
) -> ExperimentReport:
    if repetitions < 1:
        raise ValueError("repetitions must be at least 1")

    missing_runners = [mode for mode in modes if mode not in runners]
    if missing_runners:
        raise ValueError(f"missing runners for modes: {missing_runners}")

    trials: list[TrialResult] = []
    for run_number in range(1, repetitions + 1):
        for mode in modes:
            started = clock()
            try:
                execution = runners[mode]()
                evaluation = evaluate_result(execution.result, case)
                trial = TrialResult(
                    mode=mode,
                    run_number=run_number,
                    passed=evaluation.passed,
                    score=evaluation.score,
                    latency_ms=_milliseconds(clock() - started),
                    llm_calls=execution.llm_calls,
                    tool_calls=execution.tool_calls,
                    stop_reason=execution.stop_reason,
                    input_tokens=execution.input_tokens,
                    output_tokens=execution.output_tokens,
                    total_tokens=execution.total_tokens,
                    result=execution.result,
                    evaluation=evaluation,
                )
            except Exception as error:
                trial = TrialResult(
                    mode=mode,
                    run_number=run_number,
                    passed=False,
                    score=0.0,
                    latency_ms=_milliseconds(clock() - started),
                    error=f"{type(error).__name__}: {error}",
                )
            trials.append(trial)

    return ExperimentReport(
        job_id=case.job_id,
        model=model,
        repetitions=repetitions,
        trials=trials,
        summaries=[
            _summarize_mode(mode, trials)
            for mode in modes
        ],
    )


def _summarize_mode(
    mode: ExperimentMode,
    trials: list[TrialResult],
) -> ModeSummary:
    selected = [trial for trial in trials if trial.mode == mode]
    passed_runs = sum(trial.passed for trial in selected)
    return ModeSummary(
        mode=mode,
        runs=len(selected),
        passed_runs=passed_runs,
        pass_rate=_average([float(trial.passed) for trial in selected]),
        average_score=_average([trial.score for trial in selected]),
        average_latency_ms=_average(
            [trial.latency_ms for trial in selected]
        ),
        average_llm_calls=_optional_average(
            [trial.llm_calls for trial in selected]
        ),
        average_tool_calls=_optional_average(
            [trial.tool_calls for trial in selected]
        ),
        total_input_tokens=_optional_total(
            [trial.input_tokens for trial in selected]
        ),
        total_output_tokens=_optional_total(
            [trial.output_tokens for trial in selected]
        ),
        total_tokens=_optional_total(
            [trial.total_tokens for trial in selected]
        ),
    )


def _average(values: list[float]) -> float:
    if not values:
        return 0.0
    return round(sum(values) / len(values), 3)


def _optional_average(values: list[int | None]) -> float | None:
    if not values or any(value is None for value in values):
        return None
    return _average([float(value) for value in values if value is not None])


def _optional_total(values: list[int | None]) -> int | None:
    if not values or any(value is None for value in values):
        return None
    return sum(value for value in values if value is not None)


def _milliseconds(seconds: float) -> float:
    return round(seconds * 1000, 3)
